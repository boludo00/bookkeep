from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import schemas
from app.models import AppSettings
import os

router = APIRouter()

def get_hardcover_token(db: Session) -> tuple[str, str]:
    """Get Hardcover API token from env var or database. Returns (token, source)"""
    # Check environment variable first (takes precedence)
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        return (env_token, "env")
    
    # Check database
    setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
    if setting and setting.value:
        return (setting.value, "ui")
    
    return ("", "none")

@router.get("/hardcover-token", response_model=schemas.SettingsResponse)
async def get_hardcover_token_status(db: Session = Depends(get_db)):
    """Get Hardcover API token status"""
    token, source = get_hardcover_token(db)
    
    return schemas.SettingsResponse(
        hardcover_api_token=token if token else None,
        hardcover_api_token_source=source,
        has_hardcover_token=bool(token)
    )

@router.put("/hardcover-token")
async def set_hardcover_token(
    update: schemas.SettingsUpdate,
    db: Session = Depends(get_db)
):
    """Set Hardcover API token (only if not set via env var)"""
    # Check if token is set via env var
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        raise HTTPException(
            status_code=400,
            detail="Hardcover API token is set via environment variable and cannot be changed via UI"
        )
    
    # Update or create setting
    setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
    if setting:
        setting.value = update.hardcover_api_token or ""
        setting.source = "ui"
    else:
        setting = AppSettings(
            key="hardcover_api_token",
            value=update.hardcover_api_token or "",
            source="ui"
        )
        db.add(setting)
    
    db.commit()
    db.refresh(setting)
    
    return {"message": "Token updated successfully"}

