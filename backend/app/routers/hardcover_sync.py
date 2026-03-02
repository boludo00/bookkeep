"""
Router for per-user Hardcover sync configuration.

Each user can link their own Hardcover API token and choose which
to-read status / lists to watch. A background job periodically
auto-requests any new books it finds.
"""
import json
from datetime import datetime, timezone
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog

from app import database, models
from app.auth import get_current_user
from app.encryption import encrypt_value, decrypt_value

logger = structlog.get_logger(__name__)

router = APIRouter()

HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"

# --------------------------------------------------------------------------- #
# Pydantic schemas                                                             #
# --------------------------------------------------------------------------- #

class HardcoverSyncConfig(BaseModel):
    is_enabled: bool = False
    sync_to_read: bool = True
    sync_list_ids: List[int] = []
    default_format: str = "ebook"  # ebook | audiobook | both
    last_synced_at: Optional[str] = None
    has_token: bool = False


class HardcoverSyncUpdate(BaseModel):
    hardcover_api_token: Optional[str] = None  # None = keep existing
    clear_token: bool = False
    is_enabled: Optional[bool] = None
    sync_to_read: Optional[bool] = None
    sync_list_ids: Optional[List[int]] = None
    default_format: Optional[str] = None  # ebook | audiobook | both


class HardcoverList(BaseModel):
    id: int
    name: str


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

async def _execute_with_token(query: str, variables: dict, token: str) -> dict:
    """Execute a Hardcover GraphQL query using a caller-supplied token."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            HARDCOVER_API_URL,
            headers=headers,
            json={"query": query, "variables": variables or {}},
        )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Hardcover API token")
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Hardcover API returned {response.status_code}",
        )
    data = response.json()
    if "errors" in data:
        raise HTTPException(status_code=502, detail=str(data["errors"]))
    return data.get("data", {})


def _get_or_create_config(user: models.User, db: Session) -> models.UserHardcoverSync:
    config = db.query(models.UserHardcoverSync).filter(
        models.UserHardcoverSync.user_id == user.id
    ).first()
    if not config:
        config = models.UserHardcoverSync(user_id=user.id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #

@router.get("/config", response_model=HardcoverSyncConfig)
async def get_sync_config(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Return the current user's Hardcover sync configuration."""
    config = _get_or_create_config(current_user, db)
    return HardcoverSyncConfig(
        is_enabled=config.is_enabled,
        sync_to_read=config.sync_to_read,
        sync_list_ids=json.loads(config.sync_list_ids or "[]"),
        default_format=config.default_format or "ebook",
        last_synced_at=config.last_synced_at.isoformat() if config.last_synced_at else None,
        has_token=bool(config.hardcover_api_token),
    )


@router.put("/config", response_model=HardcoverSyncConfig)
async def update_sync_config(
    update: HardcoverSyncUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Update the current user's Hardcover sync configuration."""
    config = _get_or_create_config(current_user, db)

    if update.clear_token:
        config.hardcover_api_token = None
    elif update.hardcover_api_token is not None and update.hardcover_api_token.strip():
        config.hardcover_api_token = encrypt_value(update.hardcover_api_token.strip())

    if update.is_enabled is not None:
        if update.is_enabled and not config.hardcover_api_token:
            raise HTTPException(
                status_code=400,
                detail="A Hardcover API token is required before enabling sync",
            )
        config.is_enabled = update.is_enabled

    if update.sync_to_read is not None:
        config.sync_to_read = update.sync_to_read

    if update.sync_list_ids is not None:
        config.sync_list_ids = json.dumps(update.sync_list_ids)

    if update.default_format is not None:
        if update.default_format not in ("ebook", "audiobook", "both"):
            raise HTTPException(status_code=400, detail="default_format must be ebook, audiobook, or both")
        config.default_format = update.default_format

    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)

    logger.info("hardcover_sync_config_updated", user_id=current_user.id, is_enabled=config.is_enabled)

    return HardcoverSyncConfig(
        is_enabled=config.is_enabled,
        sync_to_read=config.sync_to_read,
        sync_list_ids=json.loads(config.sync_list_ids or "[]"),
        default_format=config.default_format or "ebook",
        last_synced_at=config.last_synced_at.isoformat() if config.last_synced_at else None,
        has_token=bool(config.hardcover_api_token),
    )


@router.get("/lists", response_model=List[HardcoverList])
async def get_hardcover_lists(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Fetch the current user's Hardcover lists using their personal token."""
    config = _get_or_create_config(current_user, db)
    if not config.hardcover_api_token:
        raise HTTPException(status_code=400, detail="No Hardcover API token configured")

    token = decrypt_value(config.hardcover_api_token)
    query = """
    {
      me {
        lists(order_by: {created_at: desc}) {
          id
          name
        }
      }
    }
    """
    data = await _execute_with_token(query, {}, token)
    lists = data.get("me", {}).get("lists", [])
    return [HardcoverList(id=l["id"], name=l["name"]) for l in lists]


@router.post("/run")
async def run_sync_now(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """Manually trigger a Hardcover sync for the current user."""
    config = _get_or_create_config(current_user, db)
    if not config.is_enabled:
        raise HTTPException(status_code=400, detail="Hardcover sync is not enabled")
    if not config.hardcover_api_token:
        raise HTTPException(status_code=400, detail="No Hardcover API token configured")

    from app.tasks import sync_hardcover_lists_for_user
    background_tasks.add_task(sync_hardcover_lists_for_user, config.user_id)

    return {"message": "Sync started in the background"}
