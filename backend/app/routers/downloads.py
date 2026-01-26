"""
API router for book downloads (search and download operations).

Handles searching via Prowlarr and downloading via download clients.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import structlog
import hashlib
import json

from ..database import get_db
from ..models import Book, ProwlarrServer, DownloadClient, DownloadTask, AppSettings
from ..downloads.prowlarr import ProwlarrSource
from ..downloads import DownloadOrchestrator

router = APIRouter()
logger = structlog.get_logger()


def compute_release_hash(download_url: str) -> str:
    """Compute a hash for a release based on download URL."""
    return hashlib.sha256(download_url.encode()).hexdigest()[:16]


def add_release_hash_to_book(db: Session, book_id: int, release_hash: str):
    """Add a release hash to the book's downloaded_release_hashes field."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        return

    # Get existing hashes
    try:
        hashes = json.loads(book.downloaded_release_hashes) if book.downloaded_release_hashes else []
    except (json.JSONDecodeError, TypeError):
        hashes = []

    # Add new hash if not already present
    if release_hash not in hashes:
        hashes.append(release_hash)
        book.downloaded_release_hashes = json.dumps(hashes)
        db.commit()


def check_if_already_downloaded(db: Session, book_id: int, release_hash: str) -> bool:
    """
    Check if a release has already been downloaded for this book.

    Checks both:
    1. Completed downloads stored in book.downloaded_release_hashes
    2. Active/queued downloads in download_tasks table
    """
    # Check completed downloads stored in book
    book = db.query(Book).filter(Book.id == book_id).first()
    if book and book.downloaded_release_hashes:
        try:
            hashes = json.loads(book.downloaded_release_hashes)
            if release_hash in hashes:
                return True
        except (json.JSONDecodeError, TypeError):
            pass

    # Also check if there's an active or completed download task with this hash
    existing_task = db.query(DownloadTask).filter(
        DownloadTask.book_id == book_id,
        DownloadTask.info_hash == release_hash,
        DownloadTask.state.in_(['queued', 'downloading', 'checking', 'complete', 'seeding'])
    ).first()

    return existing_task is not None


def get_download_path(db: Session, format_type: str) -> Optional[str]:
    """Get download path for a format type"""
    key = "ebook_download_path" if format_type == "ebook" else "audiobook_download_path"
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting and setting.value:
        return setting.value
    # Check environment variable
    import os
    env_key = key.upper()
    return os.getenv(env_key)


# Pydantic models
class ReleaseInfo(BaseModel):
    """Information about a search result release"""
    title: str
    download_url: str
    protocol: str  # "torrent" or "usenet"
    indexer: str
    size_bytes: int
    seeders: Optional[int] = None
    format: Optional[str] = None
    language: Optional[str] = None
    quality_score: float
    published_date: Optional[str] = None
    already_downloaded: bool = False  # Flag if this release was already downloaded
    info_url: Optional[str] = None  # Link to indexer page with more info


class SearchResponse(BaseModel):
    """Response from searching for a book"""
    book_id: int
    releases: List[ReleaseInfo]
    total: int


class DownloadRequest(BaseModel):
    """Request to download a specific release"""
    book_id: int
    format_type: str  # "ebook" or "audiobook"
    download_url: str
    protocol: str  # "torrent" or "usenet"
    release_title: str
    indexer: str
    size_bytes: int


class DownloadResponse(BaseModel):
    """Response from starting a download"""
    task_id: int
    status: str
    message: str


@router.post("/search/{book_id}", response_model=SearchResponse)
async def search_releases(
    book_id: int,
    format_type: str,  # "ebook" or "audiobook"
    db: Session = Depends(get_db)
):
    """
    Search for releases of a book via Prowlarr.

    Returns a list of available releases with quality scores and details.
    """
    # Get the book
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Get default Prowlarr server
    prowlarr_server = db.query(ProwlarrServer).filter(
        ProwlarrServer.enabled == True,
        ProwlarrServer.is_default == True
    ).first()

    if not prowlarr_server:
        # Try to get any enabled server
        prowlarr_server = db.query(ProwlarrServer).filter(
            ProwlarrServer.enabled == True
        ).first()

    if not prowlarr_server:
        raise HTTPException(
            status_code=404,
            detail="No enabled Prowlarr server configured"
        )

    try:
        # Build Prowlarr URL from server config
        protocol = "https" if prowlarr_server.use_ssl else "http"
        base_url = f"{protocol}://{prowlarr_server.host}:{prowlarr_server.port}"
        if prowlarr_server.url_base:
            base_url = f"{base_url}/{prowlarr_server.url_base.strip('/')}"

        # Parse indexer IDs from JSON if configured
        indexer_ids = None
        if prowlarr_server.indexer_ids_json:
            try:
                indexer_ids = json.loads(prowlarr_server.indexer_ids_json)
            except (json.JSONDecodeError, TypeError):
                pass

        # Initialize Prowlarr source with database config
        source = ProwlarrSource(
            base_url=base_url,
            api_key=prowlarr_server.api_key,
            indexer_ids=indexer_ids
        )

        # Search for releases
        releases = source.search(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            format_type=format_type
        )

        # Filter releases to only include protocols with configured clients
        available_protocols = db.query(DownloadClient.protocol).filter(
            DownloadClient.enabled == True
        ).distinct().all()
        available_protocols = [p.protocol for p in available_protocols if p.protocol]

        if available_protocols:
            releases = [r for r in releases if r.protocol in available_protocols]

        logger.debug(
            "search_filtered_by_protocol",
            available_protocols=available_protocols,
            releases_after_filter=len(releases)
        )

        # Convert to response format and check if already downloaded
        release_info = []
        for r in releases:
            release_hash = compute_release_hash(r.download_url)
            already_downloaded = check_if_already_downloaded(db, book_id, release_hash)

            release_info.append(ReleaseInfo(
                title=r.title,
                download_url=r.download_url,
                protocol=r.protocol,
                indexer=r.indexer,
                size_bytes=r.size_bytes,
                seeders=r.seeders,
                format=r.format,
                language=r.language,
                quality_score=r.quality_score,
                published_date=r.publish_date.isoformat() if r.publish_date else None,
                already_downloaded=already_downloaded,
                info_url=r.info_url
            ))

        logger.info(
            "search_completed",
            book_id=book_id,
            format_type=format_type,
            releases_found=len(release_info)
        )

        return SearchResponse(
            book_id=book_id,
            releases=release_info,
            total=len(release_info)
        )

    except Exception as e:
        logger.error("search_failed", book_id=book_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/download", response_model=DownloadResponse)
async def start_download(
    request: DownloadRequest,
    db: Session = Depends(get_db)
):
    """
    Start downloading a specific release.

    Creates a download task and sends it to the appropriate download client.
    """
    # Check if download path is configured
    download_path = get_download_path(db, request.format_type)
    if not download_path:
        raise HTTPException(
            status_code=400,
            detail=f"Download path not configured for {request.format_type}. Please configure download paths in settings."
        )

    # Get the book
    book = db.query(Book).filter(Book.id == request.book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        # Initialize orchestrator
        orchestrator = DownloadOrchestrator(db_session=db)

        # Create a Release object from the request
        from ..downloads import Release
        release = Release(
            source="manual",
            title=request.release_title,
            download_url=request.download_url,
            protocol=request.protocol,
            indexer=request.indexer,
            size_bytes=request.size_bytes,
            seeders=None,
            format=None,
            language=None,
            quality_score=0.0,  # Already selected by user
            publish_date=None
        )

        # Create download task
        task = orchestrator.create_download_task(
            book=book,
            release=release,
            format_type=request.format_type
        )

        if not task:
            raise HTTPException(
                status_code=500,
                detail="Failed to create download task"
            )

        # Start the download
        success = orchestrator.start_download(task.id)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to start download"
            )

        logger.info(
            "download_started",
            task_id=task.id,
            book_id=request.book_id,
            format_type=request.format_type
        )

        return DownloadResponse(
            task_id=task.id,
            status="downloading",
            message="Download started successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("download_failed", book_id=request.book_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )


@router.post("/auto-download/{book_id}", response_model=DownloadResponse)
async def auto_download(
    book_id: int,
    format_type: str,  # "ebook" or "audiobook"
    db: Session = Depends(get_db)
):
    """
    Automatically search and download the best release for a book.

    Uses quality scoring to select the best release automatically.
    """
    # Check if download path is configured
    download_path = get_download_path(db, format_type)
    if not download_path:
        raise HTTPException(
            status_code=400,
            detail=f"Download path not configured for {format_type}. Please configure download paths in settings."
        )

    # Get the book
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        # Initialize orchestrator
        orchestrator = DownloadOrchestrator(db_session=db)

        # Search and download (orchestrator picks the best release)
        task = orchestrator.search_and_download(
            book=book,
            format_type=format_type,
            source_name="prowlarr"
        )

        if not task:
            raise HTTPException(
                status_code=404,
                detail="No releases found for this book"
            )

        logger.info(
            "auto_download_started",
            task_id=task.id,
            book_id=book_id,
            format_type=format_type
        )

        return DownloadResponse(
            task_id=task.id,
            status="downloading",
            message=f"Automatically downloading best release: {task.release_title}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("auto_download_failed", book_id=book_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Auto-download failed: {str(e)}"
        )


@router.get("/tasks", response_model=List[dict])
async def get_download_tasks(
    skip: int = 0,
    limit: int = 100,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get download tasks with optional filtering.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        state: Filter by state (queued, downloading, complete, error, etc.)
    """
    query = db.query(DownloadTask).order_by(DownloadTask.created_at.desc())

    if state:
        query = query.filter(DownloadTask.state == state)

    tasks = query.offset(skip).limit(limit).all()

    # Convert to dict for response
    result = []
    for task in tasks:
        task_dict = {
            "id": task.id,
            "book_id": task.book_id,
            "format": task.format,
            "source": task.source,
            "release_title": task.release_title,
            "download_url": task.download_url,
            "protocol": task.protocol,
            "state": task.state,
            "progress": task.progress,
            "download_path": task.download_path,
            "message": task.message,
            "client_state": task.client_state,
            "import_status": task.import_status,
            "import_message": task.import_message,
            "imported_at": task.imported_at.isoformat() if task.imported_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        result.append(task_dict)

    return result


@router.post("/import/{task_id}")
async def import_download(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    Manually import/copy a completed download to the configured destination path.

    This is useful for downloads that completed but weren't automatically copied,
    or for re-importing files that were accidentally deleted.

    Args:
        task_id: ID of the download task to import
    """
    # Get the task
    task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Download task not found")

    # Check if task is in a state that can be imported
    if task.state not in ["complete", "seeding"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot import task in state '{task.state}'. Task must be complete or seeding."
        )

    # Check if we have a download path
    if not task.download_path:
        raise HTTPException(
            status_code=400,
            detail="Task has no download path recorded. Cannot determine source location."
        )

    try:
        # Get book info for better message
        from app.models import Book
        book = db.query(Book).filter(Book.id == task.book_id).first()
        book_title = book.title if book else f"Book #{task.book_id}"

        # Use the orchestrator's copy method
        orchestrator = DownloadOrchestrator()
        dest_path = orchestrator._copy_to_destination(task, task.download_path, db)

        if dest_path:
            # Update task with new destination path
            task.download_path = dest_path

            # Add release hash to book's tracking system
            release_hash = compute_release_hash(task.download_url)
            add_release_hash_to_book(db, task.book_id, release_hash)

            # Mark book as available now that import succeeded
            if book:
                if task.format == "ebook":
                    book.ebook_available = True
                elif task.format == "audiobook":
                    book.audiobook_available = True

            # Keep the task in history instead of deleting
            db.commit()

            # Extract filename from path
            import os
            filename = os.path.basename(dest_path)

            logger.info(
                "manual_import_success",
                task_id=task_id,
                book_title=book_title,
                filename=filename,
                dest_path=dest_path,
                release_hash=release_hash
            )

            return {
                "success": True,
                "message": f"Imported '{filename}' for {book_title}",
                "destination_path": dest_path,
                "filename": filename,
                "book_title": book_title
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Import failed. Check server logs for details."
            )

    except Exception as e:
        logger.error("manual_import_error", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )


@router.delete("/task/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a download task from the database.

    Only allows deletion of:
    - Completed tasks that have been imported (have downloaded_release_hashes)
    - Failed tasks
    - Cancelled tasks

    Args:
        task_id: ID of the download task to delete
    """
    # Get the task
    task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Download task not found")

    # Check if task can be deleted
    if task.state in ["complete", "seeding"]:
        # Check if it's been imported using import_status field (most reliable)
        if task.import_status != 'imported':
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete completed download that hasn't been imported yet (import status: {task.import_status or 'unknown'})"
            )

    # Delete the task
    db.delete(task)
    db.commit()

    logger.info("task_deleted", task_id=task_id, state=task.state)

    return {
        "success": True,
        "message": "Task deleted successfully"
    }


@router.delete("/tasks/clear")
async def clear_tasks(
    db: Session = Depends(get_db)
):
    """
    Clear all eligible download tasks from the database.

    Only clears:
    - Completed tasks that have been imported
    - Failed tasks
    - Cancelled tasks

    Does NOT clear:
    - Active downloads (queued, downloading, checking)
    - Completed downloads that haven't been imported
    """
    # Get all tasks that can be cleared
    tasks_to_delete = []

    # Get all tasks
    all_tasks = db.query(DownloadTask).all()

    for task in all_tasks:
        # Skip active tasks
        if task.state in ["queued", "downloading", "checking"]:
            continue

        # Failed and paused tasks can always be deleted
        if task.state in ["error", "paused"]:
            tasks_to_delete.append(task)
            continue

        # For completed tasks, check if imported using import_status
        if task.state in ["complete", "seeding"]:
            # Only delete if successfully imported
            if task.import_status == 'imported':
                tasks_to_delete.append(task)

    # Delete all eligible tasks
    deleted_count = len(tasks_to_delete)
    for task in tasks_to_delete:
        db.delete(task)

    db.commit()

    logger.info("tasks_cleared", count=deleted_count)

    return {
        "success": True,
        "message": f"Cleared {deleted_count} task(s)",
        "deleted_count": deleted_count
    }
