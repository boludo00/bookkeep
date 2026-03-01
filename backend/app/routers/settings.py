from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.database import get_db
from app import schemas, models, cache
from app.models import AppSettings
from app.auth import require_admin
from app.oidc import get_oidc_settings, is_oidc_enabled, fetch_openid_configuration, _get_oidc_value, OIDC_SETTING_KEYS
from app.encryption import encrypt_value, decrypt_value, SENSITIVE_KEYS
import os
import structlog

router = APIRouter()

def get_hardcover_token(db: Session) -> tuple[str, str]:
    """Get Hardcover API token from env var or database. Returns (token, source)"""
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        return (env_token, "env")
    
    setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
    if setting and setting.value:
        return (decrypt_value(setting.value), "ui")
    
    return ("", "none")

@router.get("/hardcover-token", response_model=schemas.SettingsResponse)
async def get_hardcover_token_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get Hardcover API token status (admin only)"""
    token, source = get_hardcover_token(db)
    masked = ""
    if token:
        masked = token[:4] + "****" + token[-4:] if len(token) > 8 else "****"

    return schemas.SettingsResponse(
        hardcover_api_token=masked if token else None,
        hardcover_api_token_source=source,
        has_hardcover_token=bool(token)
    )

@router.put("/hardcover-token")
async def set_hardcover_token(
    update: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Set Hardcover API token (only if not set via env var)"""
    # Check if token is set via env var
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        raise HTTPException(
            status_code=400,
            detail="Hardcover API token is set via environment variable and cannot be changed via UI"
        )
    
    raw_value = update.hardcover_api_token or ""
    stored_value = encrypt_value(raw_value) if raw_value else ""
    setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
    if setting:
        setting.value = stored_value
        setting.source = "ui"
    else:
        setting = AppSettings(
            key="hardcover_api_token",
            value=stored_value,
            source="ui"
        )
        db.add(setting)
    
    db.commit()
    db.refresh(setting)

    return {"message": "Token updated successfully"}


# Download Paths
class DownloadPathsResponse(BaseModel):
    ebook_download_path: Optional[str] = None
    audiobook_download_path: Optional[str] = None
    use_hardlinks: bool = True

class DownloadPathsUpdate(BaseModel):
    ebook_download_path: Optional[str] = None
    audiobook_download_path: Optional[str] = None
    use_hardlinks: Optional[bool] = None

def get_setting_value(db: Session, key: str) -> Optional[str]:
    """Get a setting value from database or env var. Decrypts sensitive values."""
    env_key = key.upper()
    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting and setting.value:
        if key in SENSITIVE_KEYS:
            return decrypt_value(setting.value)
        return setting.value

    return None

def set_setting_value(db: Session, key: str, value: Optional[str]):
    """Set a setting value in database. Encrypts sensitive values."""
    stored_value = value or ""
    if key in SENSITIVE_KEYS and stored_value:
        stored_value = encrypt_value(stored_value)

    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting:
        setting.value = stored_value
        setting.source = "ui"
    else:
        setting = AppSettings(
            key=key,
            value=stored_value,
            source="ui"
        )
        db.add(setting)
    db.commit()

@router.get("/download-paths", response_model=DownloadPathsResponse)
async def get_download_paths(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get download paths configuration (admin only)"""
    use_hardlinks_val = get_setting_value(db, "use_hardlinks")
    use_hardlinks = use_hardlinks_val != "false"  # Default to True

    return DownloadPathsResponse(
        ebook_download_path=get_setting_value(db, "ebook_download_path"),
        audiobook_download_path=get_setting_value(db, "audiobook_download_path"),
        use_hardlinks=use_hardlinks,
    )

@router.put("/download-paths")
async def update_download_paths(
    update: DownloadPathsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Update download paths configuration (admin only)"""
    if update.ebook_download_path is not None:
        set_setting_value(db, "ebook_download_path", update.ebook_download_path)

    if update.audiobook_download_path is not None:
        set_setting_value(db, "audiobook_download_path", update.audiobook_download_path)

    if update.use_hardlinks is not None:
        set_setting_value(db, "use_hardlinks", "true" if update.use_hardlinks else "false")

    return {"message": "Download paths updated successfully"}


# Browse Directories (Admin only)

class DirectoryEntry(BaseModel):
    name: str
    path: str

class BrowseDirectoriesResponse(BaseModel):
    current_path: str
    parent_path: Optional[str] = None
    directories: List[DirectoryEntry] = []
    error: Optional[str] = None

@router.get("/browse-directories", response_model=BrowseDirectoriesResponse)
async def browse_directories(
    path: str = "/",
    current_user: models.User = Depends(require_admin)
):
    """Browse directories on the filesystem (admin only)"""
    resolved = os.path.abspath(path)

    if not os.path.isdir(resolved):
        return BrowseDirectoriesResponse(
            current_path=resolved,
            parent_path=os.path.dirname(resolved),
            error=f"Directory not found: {resolved}"
        )

    parent = os.path.dirname(resolved) if resolved != "/" else None

    directories: List[DirectoryEntry] = []
    try:
        with os.scandir(resolved) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(DirectoryEntry(
                            name=entry.name,
                            path=os.path.join(resolved, entry.name)
                        ))
                except PermissionError:
                    continue
    except PermissionError:
        return BrowseDirectoriesResponse(
            current_path=resolved,
            parent_path=parent,
            error=f"Permission denied: {resolved}"
        )

    directories.sort(key=lambda d: d.name.lower())

    return BrowseDirectoriesResponse(
        current_path=resolved,
        parent_path=parent,
        directories=directories
    )


# OIDC Settings (Admin only)

class OidcSettingField(BaseModel):
    value: Optional[str] = None
    source: str = "none"

class OidcSettingsResponse(BaseModel):
    enabled: bool
    oidc_issuer_url: OidcSettingField
    oidc_client_id: OidcSettingField
    oidc_client_secret: OidcSettingField
    oidc_redirect_uri: OidcSettingField
    oidc_auto_register: OidcSettingField
    oidc_button_text: OidcSettingField

class OidcSettingsUpdate(BaseModel):
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None
    oidc_auto_register: Optional[str] = None
    oidc_button_text: Optional[str] = None

@router.get("/oidc", response_model=OidcSettingsResponse)
async def get_oidc_settings_endpoint(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Get OIDC settings with sources (admin only)."""
    raw = get_oidc_settings(db)
    fields = {}
    for key in OIDC_SETTING_KEYS:
        value = raw[key]["value"]
        source = raw[key]["source"]
        if key == "oidc_client_secret" and value:
            value = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
        fields[key] = OidcSettingField(value=value, source=source)
    return OidcSettingsResponse(enabled=raw["enabled"], **fields)

@router.put("/oidc")
async def update_oidc_settings_endpoint(
    update: OidcSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Update OIDC settings (admin only). Fields locked by env vars are rejected."""
    update_data = update.model_dump(exclude_none=True)
    for key, value in update_data.items():
        env_key = key.upper()
        if os.getenv(env_key):
            raise HTTPException(
                status_code=400,
                detail=f"{key} is set via environment variable and cannot be changed via UI",
            )
        set_setting_value(db, key, value)

    return {"message": "OIDC settings updated successfully"}

@router.post("/oidc/test")
async def test_oidc_connection(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Test OIDC issuer connectivity by fetching its discovery document."""
    issuer_url = _get_oidc_value(db, "oidc_issuer_url")
    if not issuer_url:
        raise HTTPException(status_code=400, detail="OIDC issuer URL is not configured")

    try:
        discovery = await fetch_openid_configuration(issuer_url)
        return {
            "status": "ok",
            "issuer": discovery.get("issuer"),
            "authorization_endpoint": discovery.get("authorization_endpoint"),
            "token_endpoint": discovery.get("token_endpoint"),
            "userinfo_endpoint": discovery.get("userinfo_endpoint"),
        }
    except Exception as exc:
        logger = structlog.get_logger(__name__)
        logger.error("oidc_test_connection_failed", error=str(exc))
        raise HTTPException(
            status_code=400,
            detail="Failed to connect to OIDC issuer. Check the issuer URL and network connectivity.",
        )


# Cache Management (Admin only)

class CacheResourceInfo(BaseModel):
    key: str
    name: str
    description: str

class CacheResourcesResponse(BaseModel):
    resources: List[CacheResourceInfo]

class CacheClearResponse(BaseModel):
    message: str
    deleted_count: int

class CacheClearAllResponse(BaseModel):
    message: str
    total_deleted: int
    by_resource: dict

@router.get("/cache/resources", response_model=CacheResourcesResponse)
async def get_cache_resources(
    current_user: models.User = Depends(require_admin)
):
    """Get list of cache resources that can be cleared (admin only)"""
    resources = [
        CacheResourceInfo(
            key=key,
            name=info["name"],
            description=info["description"]
        )
        for key, info in cache.CACHE_RESOURCES.items()
    ]
    return CacheResourcesResponse(resources=resources)

@router.post("/cache/clear/{resource}", response_model=CacheClearResponse)
async def clear_cache_resource(
    resource: str,
    current_user: models.User = Depends(require_admin)
):
    """Clear cache for a specific resource (admin only)"""
    try:
        result = await cache.clear_cache_by_resource(resource)
        return CacheClearResponse(
            message=f"Cleared {result['name']} cache",
            deleted_count=result["deleted_count"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cache/clear-all", response_model=CacheClearAllResponse)
async def clear_all_cache(
    current_user: models.User = Depends(require_admin)
):
    """Clear all cache entries (admin only)"""
    result = await cache.clear_all_cache()
    return CacheClearAllResponse(
        message="All cache cleared",
        total_deleted=result["total_deleted"],
        by_resource=result["by_resource"]
    )


class CacheDebugResponse(BaseModel):
    total_keys: int
    sample_keys: List[str]
    namespace: str


@router.get("/cache/debug", response_model=CacheDebugResponse)
async def debug_cache_keys(
    current_user: models.User = Depends(require_admin)
):
    """Debug endpoint to list cache keys (admin only)"""
    import os
    redis_url = os.getenv("REDIS_URL", "")

    if not redis_url:
        return CacheDebugResponse(total_keys=0, sample_keys=[], namespace="no_redis")

    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(redis_url, decode_responses=True)

        # Scan all keys
        all_keys = []
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="*", count=100)
            all_keys.extend(keys)
            if cursor == 0:
                break

        await redis_client.aclose()

        return CacheDebugResponse(
            total_keys=len(all_keys),
            sample_keys=all_keys[:50],  # Return first 50 keys
            namespace="bookkeep"
        )
    except Exception as e:
        return CacheDebugResponse(
            total_keys=0,
            sample_keys=[f"error: {str(e)}"],
            namespace="error"
        )

