from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.database import get_db
from app import schemas, models, cache
from app.models import AppSettings
from app.auth import require_admin
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
    """Get a setting value from database or env var"""
    # Check environment variable first
    env_key = key.upper()
    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    # Check database
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting and setting.value:
        return setting.value

    return None

def set_setting_value(db: Session, key: str, value: Optional[str]):
    """Set a setting value in database"""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting:
        setting.value = value or ""
        setting.source = "ui"
    else:
        setting = AppSettings(
            key=key,
            value=value or "",
            source="ui"
        )
        db.add(setting)
    db.commit()

@router.get("/download-paths", response_model=DownloadPathsResponse)
async def get_download_paths(db: Session = Depends(get_db)):
    """Get download paths configuration"""
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
    db: Session = Depends(get_db)
):
    """Update download paths configuration"""
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

