"""
API router for direct download settings.

Manages configuration for direct download providers (Anna's Archive, Z-Library, etc.)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import structlog

from ..database import get_db
from ..models import DirectDownloadSettings
from ..auth import require_admin
from .. import models

router = APIRouter()
logger = structlog.get_logger()


# Pydantic schemas
class DirectDownloadSettingsUpdate(BaseModel):
    """Request schema for updating direct download settings."""
    enabled: bool = False
    annas_archive_enabled: bool = True
    annas_archive_mirror: Optional[str] = None
    annas_archive_language: Optional[str] = None
    zlibrary_enabled: bool = False
    zlibrary_email: Optional[str] = None
    zlibrary_password: Optional[str] = None  # Only set if changing
    zlibrary_domain: Optional[str] = None
    requests_per_minute: int = 10
    flaresolverr_url: Optional[str] = None


class DirectDownloadSettingsResponse(BaseModel):
    """Response schema for direct download settings."""
    id: int
    enabled: bool
    annas_archive_enabled: bool
    annas_archive_mirror: Optional[str]
    annas_archive_language: Optional[str]
    zlibrary_enabled: bool
    zlibrary_email: Optional[str]
    zlibrary_password_set: bool  # True if password is configured (don't expose actual password)
    zlibrary_domain: Optional[str]
    requests_per_minute: int
    flaresolverr_url: Optional[str]

    class Config:
        from_attributes = True


class DirectDownloadTestResponse(BaseModel):
    """Response schema for connection test."""
    success: bool
    providers_count: int
    providers_status: dict  # {provider_name: bool}
    message: Optional[str] = None


def _settings_to_response(settings: DirectDownloadSettings) -> DirectDownloadSettingsResponse:
    """Convert database model to response schema."""
    return DirectDownloadSettingsResponse(
        id=settings.id,
        enabled=settings.enabled,
        annas_archive_enabled=settings.annas_archive_enabled,
        annas_archive_mirror=settings.annas_archive_mirror,
        annas_archive_language=settings.annas_archive_language,
        zlibrary_enabled=settings.zlibrary_enabled,
        zlibrary_email=settings.zlibrary_email,
        zlibrary_password_set=bool(settings.zlibrary_password),  # Don't expose password
        zlibrary_domain=settings.zlibrary_domain,
        requests_per_minute=settings.requests_per_minute,
        flaresolverr_url=settings.flaresolverr_url,
    )


@router.get("/settings", response_model=DirectDownloadSettingsResponse)
async def get_settings(current_user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Get direct download settings.

    Returns current configuration for direct download providers.
    """
    settings = db.query(DirectDownloadSettings).first()

    if not settings:
        # Return defaults if no settings exist
        return DirectDownloadSettingsResponse(
            id=0,
            enabled=False,
            annas_archive_enabled=True,
            annas_archive_mirror=None,
            annas_archive_language=None,
            zlibrary_enabled=False,
            zlibrary_email=None,
            zlibrary_password_set=False,
            zlibrary_domain=None,
            requests_per_minute=10,
            flaresolverr_url=None,
        )

    return _settings_to_response(settings)


@router.put("/settings", response_model=DirectDownloadSettingsResponse)
async def update_settings(
    data: DirectDownloadSettingsUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update direct download settings.

    Creates settings if they don't exist, otherwise updates existing.
    """
    settings = db.query(DirectDownloadSettings).first()

    if not settings:
        # Create new settings
        settings = DirectDownloadSettings(
            enabled=data.enabled,
            annas_archive_enabled=data.annas_archive_enabled,
            annas_archive_mirror=data.annas_archive_mirror,
            annas_archive_language=data.annas_archive_language,
            zlibrary_enabled=data.zlibrary_enabled,
            zlibrary_email=data.zlibrary_email,
            zlibrary_password=data.zlibrary_password,
            zlibrary_domain=data.zlibrary_domain,
            requests_per_minute=data.requests_per_minute,
            flaresolverr_url=data.flaresolverr_url,
        )
        db.add(settings)
        logger.info("direct_download_settings_created")
    else:
        # Update existing settings
        settings.enabled = data.enabled
        settings.annas_archive_enabled = data.annas_archive_enabled
        settings.annas_archive_mirror = data.annas_archive_mirror
        settings.annas_archive_language = data.annas_archive_language
        settings.zlibrary_enabled = data.zlibrary_enabled
        settings.zlibrary_email = data.zlibrary_email
        settings.zlibrary_domain = data.zlibrary_domain
        settings.requests_per_minute = data.requests_per_minute
        settings.flaresolverr_url = data.flaresolverr_url

        # Only update password if provided (non-empty)
        if data.zlibrary_password:
            settings.zlibrary_password = data.zlibrary_password

        logger.info("direct_download_settings_updated")

    db.commit()
    db.refresh(settings)

    return _settings_to_response(settings)


@router.post("/test", response_model=DirectDownloadTestResponse)
async def test_connection(current_user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Test direct download provider connections.

    Tests connectivity to all enabled providers and returns status.
    """
    settings = db.query(DirectDownloadSettings).first()

    if not settings or not settings.enabled:
        return DirectDownloadTestResponse(
            success=False,
            providers_count=0,
            providers_status={},
            message="Direct downloads are not enabled"
        )

    # Import source here to avoid circular imports
    from ..downloads.direct.source import DirectDownloadSource

    try:
        source = DirectDownloadSource(db_session=db)
        providers_count = source.get_provider_count()

        if providers_count == 0:
            return DirectDownloadTestResponse(
                success=False,
                providers_count=0,
                providers_status={},
                message="No providers are enabled"
            )

        # Test each provider individually
        providers_status = source.test_providers()

        # Count successful providers
        working_count = sum(1 for v in providers_status.values() if v)
        success = working_count > 0

        if success:
            message = f"{working_count} of {providers_count} provider(s) connected"
        else:
            message = "No providers could connect - sites may be blocked or require Cloudflare bypass"

        return DirectDownloadTestResponse(
            success=success,
            providers_count=providers_count,
            providers_status=providers_status,
            message=message
        )

    except Exception as e:
        logger.error("direct_download_test_error", error=str(e))
        return DirectDownloadTestResponse(
            success=False,
            providers_count=0,
            providers_status={},
            message=f"Test failed: {str(e)}"
        )


@router.delete("/settings")
async def reset_settings(current_user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Reset direct download settings to defaults.

    Deletes all settings, effectively disabling direct downloads.
    """
    settings = db.query(DirectDownloadSettings).first()

    if settings:
        db.delete(settings)
        db.commit()
        logger.info("direct_download_settings_reset")

    return {"success": True, "message": "Settings reset to defaults"}


class FlareSolverrTestRequest(BaseModel):
    """Request schema for testing FlareSolverr connection."""
    url: str


class FlareSolverrTestResponse(BaseModel):
    """Response schema for FlareSolverr connection test."""
    success: bool
    message: str


@router.post("/test-flaresolverr", response_model=FlareSolverrTestResponse)
async def test_flaresolverr(data: FlareSolverrTestRequest, current_user: models.User = Depends(require_admin)):
    """
    Test connectivity to a FlareSolverr instance.

    Sends a sessions.list command to verify FlareSolverr is reachable.
    """
    from ..downloads.flaresolverr import FlareSolverrClient

    if not data.url:
        return FlareSolverrTestResponse(
            success=False,
            message="FlareSolverr URL is required"
        )

    try:
        client = FlareSolverrClient(data.url)
        success = await client.test_connection()
        await client.close()

        if success:
            return FlareSolverrTestResponse(
                success=True,
                message="FlareSolverr is reachable and responding"
            )
        else:
            return FlareSolverrTestResponse(
                success=False,
                message="FlareSolverr returned an unexpected response"
            )
    except Exception as e:
        logger.error("flaresolverr_test_error", error=str(e))
        return FlareSolverrTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )


@router.post("/debug-search")
async def debug_search(
    title: str,
    author: Optional[str] = None,
    format_type: str = "ebook",
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Debug endpoint to test direct download search.

    Returns detailed information about the search process.
    """
    settings = db.query(DirectDownloadSettings).first()

    debug_info = {
        "settings_exists": settings is not None,
        "enabled": settings.enabled if settings else False,
        "annas_archive_enabled": settings.annas_archive_enabled if settings else False,
        "zlibrary_enabled": settings.zlibrary_enabled if settings else False,
        "zlibrary_has_email": bool(settings.zlibrary_email) if settings else False,
        "providers_loaded": 0,
        "provider_names": [],
        "search_results": [],
        "errors": [],
    }

    if not settings or not settings.enabled:
        debug_info["errors"].append("Direct downloads not enabled")
        return debug_info

    try:
        from ..downloads.direct.source import DirectDownloadSource
        source = DirectDownloadSource(db_session=db)

        debug_info["providers_loaded"] = source.get_provider_count()
        debug_info["provider_names"] = source.get_provider_names()

        if source.get_provider_count() == 0:
            debug_info["errors"].append("No providers loaded - check settings")
            return debug_info

        # Perform search
        releases = source.search(
            title=title,
            author=author,
            format_type=format_type
        )

        debug_info["search_results"] = [
            {
                "title": r.title,
                "protocol": r.protocol,
                "format": r.format,
                "size_bytes": r.size_bytes,
                "indexer": r.indexer,
                "download_url": r.download_url[:50] + "..." if len(r.download_url) > 50 else r.download_url,
            }
            for r in releases[:10]  # Limit to first 10
        ]
        debug_info["total_results"] = len(releases)

    except Exception as e:
        import traceback
        debug_info["errors"].append(str(e))
        debug_info["traceback"] = traceback.format_exc()
        logger.error("direct_debug_search_error", error=str(e))

    return debug_info
