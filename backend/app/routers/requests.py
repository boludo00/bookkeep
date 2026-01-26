from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import structlog
from app import database, models, schemas
from app.cache import get_cached, set_cached, delete_cached, make_cache_key, CACHE_TTL, clear_cache_pattern
from app.auth import get_current_user, require_admin
from app.downloads import DownloadOrchestrator
from app.routers.users import get_password_hash

logger = structlog.get_logger(__name__)

router = APIRouter()

def _normalize_book_genres(book: Optional[models.Book]) -> None:
    if not book or not book.genres or not isinstance(book.genres, str):
        return
    book.__dict__["genres"] = [g.strip() for g in book.genres.split(",") if g.strip()]


@router.post("/", response_model=schemas.BookRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    request: schemas.BookRequestCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify book exists
    book = db.query(models.Book).filter(models.Book.id == request.book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    # Check user permissions for the requested format
    can_request = False
    if request.format == "ebook" and current_user.can_request_ebook:
        can_request = True
    elif request.format == "audiobook" and current_user.can_request_audiobook:
        can_request = True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid format. Only 'ebook' and 'audiobook' are supported."
        )
    
    if not can_request:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to request {request.format}s"
        )

    # Block requests for formats already available in our library
    if (request.format == "ebook" and book.ebook_available) or (
        request.format == "audiobook" and book.audiobook_available
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{request.format.capitalize()} is already available."
        )

    # Check if this book+format already has a request (global - any user)
    # Only allow new requests if existing ones are denied or don't exist
    # Users can request ebook AND audiobook separately for the same book
    existing_request = db.query(models.BookRequest).filter(
        models.BookRequest.book_id == request.book_id,
        models.BookRequest.format == request.format,  # Per-format check
        models.BookRequest.status != "denied"
    ).first()

    if existing_request and existing_request.status == "not_found":
        if existing_request.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This request belongs to another user and cannot be resubmitted."
            )
        # Re-open the request for processing below.
        db_request = existing_request
    elif existing_request:
        # This format already requested - return existing request info
        from sqlalchemy.orm import joinedload
        existing_request = db.query(models.BookRequest).options(
            joinedload(models.BookRequest.book),
            joinedload(models.BookRequest.user)
        ).filter(models.BookRequest.id == existing_request.id).first()
        
        format_label = "ebook" if request.format == "ebook" else "audiobook"
        status_message = {
            "pending": f"The {format_label} has already been requested and is pending approval.",
            "approved": f"The {format_label} has already been approved and is being processed.",
            "processing": f"The {format_label} is currently being processed.",
            "available": f"The {format_label} is already available."
        }.get(existing_request.status, f"The {format_label} has already been requested.")
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{status_message} Requested by: {existing_request.user.username if existing_request.user else 'Unknown'}"
        )
    
    # Check if user has auto-approve permission for this format
    auto_approve = False
    if request.format == "ebook" and current_user.auto_approve_ebooks:
        auto_approve = True
    elif request.format == "audiobook" and current_user.auto_approve_audiobooks:
        auto_approve = True
    
    # Create or re-open request with appropriate initial status
    initial_status = "approved" if auto_approve else "pending"
    if existing_request and existing_request.status == "not_found":
        db_request.status = initial_status
        db_request.notes = request.notes
        db_request.admin_notes = None
        db_request.edition_id = request.edition_id
        db_request.updated_at = datetime.now(timezone.utc)
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    else:
        db_request = models.BookRequest(
            book_id=request.book_id,
            user_id=current_user.id,
            format=request.format,
            notes=request.notes,
            status=initial_status,
            edition_id=request.edition_id
        )
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    
    # Eager load book relationship
    from sqlalchemy.orm import joinedload
    db_request = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    ).filter(models.BookRequest.id == db_request.id).first()
    
    # Automatically trigger download if auto-approved
    if auto_approve:
        try:
            orchestrator = DownloadOrchestrator(db_session=db)
            task = orchestrator.search_and_download(
                book=db_request.book,
                format_type=db_request.format,
                source_name="prowlarr"
            )

            if task:
                logger.info(
                    "auto_download_triggered",
                    request_id=db_request.id,
                    task_id=task.id,
                    format=db_request.format
                )
                # Update status to processing since download started
                db_request.status = "processing"
                db.commit()
                db.refresh(db_request)
            else:
                logger.warning(
                    "auto_download_no_releases",
                    request_id=db_request.id,
                    book_id=db_request.book_id,
                    format=db_request.format
                )
                # Keep as approved but log that no releases found
        except Exception as e:
            logger.error(
                "auto_download_failed",
                request_id=db_request.id,
                error=str(e)
            )
            # Don't fail the request - just keep it as approved for manual fulfillment
    
    # Convert book.genres from comma-separated string to list for response
    _normalize_book_genres(db_request.book)

    if book.hardcover_id:
        await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=book.hardcover_id))
        # Also clear batch caches that might contain this book
        await clear_cache_pattern("requests_by_hardcover_batch:*")

    return db_request

@router.get("/", response_model=list[schemas.BookRequestResponse])
def get_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status_filter: Optional[str] = Query(None, alias="status_filter"),
    user_id: Optional[int] = Query(None, alias="user_id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    
    query = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    )
    
    # If user is not admin, only show their own requests
    # If admin, allow filtering by user_id or show all
    if not current_user.is_admin:
        query = query.filter(models.BookRequest.user_id == current_user.id)
    elif user_id:
        query = query.filter(models.BookRequest.user_id == user_id)
    
    if status_filter:
        query = query.filter(models.BookRequest.status == status_filter)
    
    requests = query.order_by(
        models.BookRequest.created_at.desc(),
        models.BookRequest.id.desc()
    ).offset(skip).limit(limit).all()
    
    # Convert book.genres from comma-separated string to list for each request
    for req in requests:
        _normalize_book_genres(req.book)
    
    return requests


@router.get("/by-book/{book_id}")
async def get_requests_for_book(
    book_id: int,
    db: Session = Depends(database.get_db)
):
    """Get all non-denied requests for a book by local book_id (to show which formats are already requested)"""
    requests = db.query(models.BookRequest).filter(
        models.BookRequest.book_id == book_id,
        models.BookRequest.status != "denied"
    ).all()
    
    # Build a response with format status
    result = {"ebook": None, "audiobook": None}
    for r in requests:
        result[r.format] = r.status
    
    logger.debug("requests_for_book", book_id=book_id, ebook=result["ebook"], audiobook=result["audiobook"])
    return result


@router.get("/by-hardcover/{hardcover_id}")
async def get_requests_for_hardcover_book(
    hardcover_id: int,
    db: Session = Depends(database.get_db)
):
    """Get all non-denied requests for a book by hardcover_id (to show which formats are already requested)"""
    cache_key = make_cache_key("requests_by_hardcover", hardcover_id=hardcover_id)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    # First find the book by hardcover_id
    book = db.query(models.Book).filter(models.Book.hardcover_id == hardcover_id).first()
    
    if not book:
        # No book in database yet, so no requests exist
        result = {"ebook": None, "audiobook": None, "book_id": None}
        await set_cached(cache_key, result, ttl=CACHE_TTL.get("requests_by_hardcover", 30))
        return result
    
    requests = db.query(models.BookRequest).filter(
        models.BookRequest.book_id == book.id,
        models.BookRequest.status != "denied"
    ).all()
    
    # Build a response with format status
    result = {
        "ebook": None,
        "audiobook": None,
        "book_id": book.id,
    }
    for r in requests:
        result[r.format] = r.status
    
    logger.debug("requests_for_hardcover_book", 
                hardcover_id=hardcover_id, 
                book_id=book.id,
                ebook=result["ebook"], 
                audiobook=result["audiobook"])
    await set_cached(cache_key, result, ttl=CACHE_TTL.get("requests_by_hardcover", 30))
    return result


@router.post("/by-hardcover/batch")
async def get_requests_for_hardcover_batch(
    payload: schemas.ReadarrAvailabilityBatchRequest,
    db: Session = Depends(database.get_db),
):
    """Get request status for multiple hardcover IDs."""
    hardcover_ids = list({int(book_id) for book_id in payload.hardcover_ids if book_id is not None})
    if not hardcover_ids:
        return {"results": []}

    ids_key = ",".join(str(book_id) for book_id in sorted(hardcover_ids))
    cache_key = make_cache_key("requests_by_hardcover_batch", ids=ids_key)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    results_map = {
        hardcover_id: {"hardcover_id": hardcover_id, "ebook": None, "audiobook": None}
        for hardcover_id in hardcover_ids
    }

    rows = (
        db.query(models.Book.hardcover_id, models.BookRequest.format, models.BookRequest.status)
        .join(models.BookRequest, models.BookRequest.book_id == models.Book.id)
        .filter(models.Book.hardcover_id.in_(hardcover_ids))
        .filter(models.BookRequest.status != "denied")
        .all()
    )

    for hardcover_id, format_value, status_value in rows:
        entry = results_map.get(hardcover_id)
        if not entry:
            continue
        if format_value in ["ebook", "audiobook"]:
            entry[format_value] = status_value

    response = {"results": list(results_map.values())}
    await set_cached(cache_key, response, ttl=CACHE_TTL.get("requests_by_hardcover_batch", 300))
    return response


@router.delete("/by-hardcover/{hardcover_id}")
async def clear_requests_for_book(
    hardcover_id: int,
    format: Optional[str] = Query(None, description="Format to clear: 'ebook', 'audiobook', or None for all"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Clear/delete requests for a book by hardcover_id. Admins can clear any request, users can only clear their own."""
    # Find the book by hardcover_id
    book = db.query(models.Book).filter(models.Book.hardcover_id == hardcover_id).first()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    # Build query for requests to delete
    query = db.query(models.BookRequest).filter(
        models.BookRequest.book_id == book.id
    )
    
    # Filter by format if specified
    if format:
        if format not in ["ebook", "audiobook"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format must be 'ebook' or 'audiobook'"
            )
        query = query.filter(models.BookRequest.format == format)
    
    # Non-admins can only delete their own requests
    if not current_user.is_admin:
        query = query.filter(models.BookRequest.user_id == current_user.id)
    
    requests_to_delete = query.all()
    
    if not requests_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No requests found to clear"
        )
    
    deleted_count = 0
    deleted_formats = []
    for req in requests_to_delete:
        deleted_formats.append(req.format)
        db.delete(req)
        deleted_count += 1
    
    # Reset per-format availability based on what was cleared
    if format:
        # Only reset the specific format
        if format == "ebook":
            book.ebook_available = False
        elif format == "audiobook":
            book.audiobook_available = False
    else:
        # Clear all format availability
        book.ebook_available = False
        book.audiobook_available = False
    db.add(book)
    
    db.commit()

    await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=hardcover_id))
    # Clear batch caches
    await clear_cache_pattern("requests_by_hardcover_batch:*")

    logger.info("requests_cleared",
               hardcover_id=hardcover_id,
               book_id=book.id,
               deleted_count=deleted_count,
               formats=deleted_formats,
               user_id=current_user.id,
               is_admin=current_user.is_admin)

    return {
        "message": f"Cleared {deleted_count} request(s)",
        "deleted_count": deleted_count,
        "formats": deleted_formats
    }


@router.post("/series/{series_id}")
async def request_series(
    series_id: int,
    format: str = Query("ebook", description="Format to request: 'ebook' or 'audiobook'"),
    original_only: bool = Query(False, description="Only request whole-number series positions"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Request all missing books in a series.
    
    Only requests books that are not already available or have pending requests.
    """
    if format not in ["ebook", "audiobook"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be 'ebook' or 'audiobook'"
        )
    
    # Get all books in this series from the database
    books_query = db.query(models.Book).filter(models.Book.series_id == series_id)
    if original_only:
        books_query = books_query.filter(
            models.Book.series_position.isnot(None),
            func.floor(models.Book.series_position) == models.Book.series_position
        )
    books_in_series = books_query.order_by(models.Book.series_position.asc().nulls_last()).all()
    
    if not books_in_series:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No books found in this series"
        )
    
    requested_count = 0
    skipped_count = 0
    already_available = 0
    already_requested = 0
    failed_count = 0
    failed_books = []  # Track which books failed for better user feedback

    for book in books_in_series:
        # Check if book is already available for this format
        if (format == "ebook" and book.ebook_available) or (
            format == "audiobook" and book.audiobook_available
        ):
            already_available += 1
            skipped_count += 1
            continue
        
        # Check if there's already a non-denied request for this book+format
        existing_request = db.query(models.BookRequest).filter(
            models.BookRequest.book_id == book.id,
            models.BookRequest.format == format,
            models.BookRequest.status != "denied"
        ).first()
        
        if existing_request:
            already_requested += 1
            skipped_count += 1
            continue
        
        # Check auto-approval settings
        should_auto_approve = False
        if format == "ebook" and current_user.auto_approve_ebooks:
            should_auto_approve = True
        elif format == "audiobook" and current_user.auto_approve_audiobooks:
            should_auto_approve = True
        
        initial_status = "approved" if should_auto_approve else "pending"
        
        # Create the request
        now = datetime.now(timezone.utc)
        new_request = models.BookRequest(
            book_id=book.id,
            user_id=current_user.id,
            format=format,
            status=initial_status,
            notes=f"Requested as part of series (ID: {series_id})",
            created_at=now,
            updated_at=now,
        )
        db.add(new_request)
        db.flush()  # Get the ID
        
        # Trigger download if auto-approved
        if should_auto_approve:
            try:
                orchestrator = DownloadOrchestrator(db_session=db)
                task = orchestrator.search_and_download(
                    book=book,
                    format_type=format,
                    source_name="prowlarr"
                )

                if task:
                    new_request.status = "processing"
                    logger.info("series_book_download_triggered",
                               series_id=series_id,
                               book_id=book.id,
                               book_title=book.title,
                               task_id=task.id)
                else:
                    logger.warning("series_book_no_releases",
                                  series_id=series_id,
                                  book_id=book.id,
                                  book_title=book.title,
                                  format=format)
                    # Keep as approved — can be retried
            except Exception as e:
                error_msg = str(e)
                logger.warning("series_book_download_failed",
                              series_id=series_id,
                              book_id=book.id,
                              book_title=book.title,
                              error=error_msg)

                new_request.notes = (new_request.notes or "") + f"\n[Error] Download: {error_msg}"

                failed_count += 1
                failed_books.append({
                    "title": book.title,
                    "position": book.series_position,
                    "error": error_msg
                })
                requested_count -= 1
        
        requested_count += 1
        
        logger.info("series_book_requested",
                   series_id=series_id,
                   book_id=book.id,
                   book_title=book.title,
                   format=format,
                   status=new_request.status,
                   user_id=current_user.id)
    
    db.commit()

    # Clear batch cache for all books in this series
    for book in books_in_series:
        if book.hardcover_id:
            await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=book.hardcover_id))

    # Clear all batch caches (they contain combinations of hardcover IDs)
    # This is a bit aggressive but necessary since batch caches contain arbitrary combinations
    await clear_cache_pattern("requests_by_hardcover_batch:*")

    logger.info("series_request_complete",
               series_id=series_id,
               requested_count=requested_count,
               skipped_count=skipped_count,
               already_available=already_available,
               already_requested=already_requested,
               failed_count=failed_count,
               format=format,
               user_id=current_user.id)

    return {
        "series_id": series_id,
        "format": format,
        "requested_count": requested_count,
        "skipped_count": skipped_count,
        "already_available": already_available,
        "already_requested": already_requested,
        "failed_count": failed_count,
        "failed_books": failed_books if failed_books else None,
        "total_books": len(books_in_series)
    }


@router.delete("/series/{series_id}")
async def clear_series_requests(
    series_id: int,
    format: Optional[str] = Query(None, description="Format to clear: 'ebook' or 'audiobook'. If not specified, clears all formats."),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Clear all requests for books in a series.
    
    Non-admins can only clear their own requests.
    """
    if format and format not in ["ebook", "audiobook"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be 'ebook' or 'audiobook'"
        )
    
    # Get all books in this series
    books_in_series = db.query(models.Book).filter(
        models.Book.series_id == series_id
    ).all()
    
    if not books_in_series:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No books found in this series"
        )
    
    book_ids = [book.id for book in books_in_series]
    
    # Build query for requests to delete
    query = db.query(models.BookRequest).filter(
        models.BookRequest.book_id.in_(book_ids)
    )
    
    # Filter by format if specified
    if format:
        query = query.filter(models.BookRequest.format == format)
    
    # Non-admins can only delete their own requests
    if not current_user.is_admin:
        query = query.filter(models.BookRequest.user_id == current_user.id)
    
    requests_to_delete = query.all()
    
    if not requests_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No requests found to clear for this series"
        )
    
    deleted_count = 0
    deleted_formats = []
    affected_books = set()
    
    for req in requests_to_delete:
        deleted_formats.append(req.format)
        affected_books.add(req.book_id)
        db.delete(req)
        deleted_count += 1
    
    # Reset availability for affected books if all their requests are cleared
    for book_id in affected_books:
        remaining_requests = db.query(models.BookRequest).filter(
            models.BookRequest.book_id == book_id
        ).count()
        
        if remaining_requests == 0:
            book = db.query(models.Book).filter(models.Book.id == book_id).first()
            if book:
                book.ebook_available = False
                book.audiobook_available = False
                db.add(book)
    
    db.commit()

    # Clear individual and batch caches for all affected books
    affected_hardcover_ids = []
    for book_id in affected_books:
        book = db.query(models.Book).filter(models.Book.id == book_id).first()
        if book and book.hardcover_id:
            affected_hardcover_ids.append(book.hardcover_id)
            await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=book.hardcover_id))

    # Clear batch caches
    if affected_hardcover_ids:
        await clear_cache_pattern("requests_by_hardcover_batch:*")

    logger.info("series_requests_cleared",
               series_id=series_id,
               deleted_count=deleted_count,
               formats=list(set(deleted_formats)),
               affected_books=len(affected_books),
               user_id=current_user.id,
               is_admin=current_user.is_admin)

    return {
        "message": f"Cleared {deleted_count} request(s) for series",
        "series_id": series_id,
        "deleted_count": deleted_count,
        "formats": list(set(deleted_formats)),
        "affected_books": len(affected_books)
    }


@router.get("/{request_id}", response_model=schemas.BookRequestResponse)
def get_request(request_id: int, db: Session = Depends(database.get_db)):
    from sqlalchemy.orm import joinedload
    
    db_request = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    ).filter(models.BookRequest.id == request_id).first()
    
    if not db_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
    
    # Convert book.genres from comma-separated string to list for response
    _normalize_book_genres(db_request.book)
    
    return db_request

@router.put("/{request_id}", response_model=schemas.BookRequestResponse)
async def update_request(
    request_id: int,
    update: schemas.BookRequestUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    db_request = db.query(models.BookRequest).filter(models.BookRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
    
    # Track if status is changing to approved
    status_changing_to_approved = (
        update.status == "approved" and 
        db_request.status != "approved"
    )
    
    if update.status:
        db_request.status = update.status
    if update.admin_notes is not None:
        db_request.admin_notes = update.admin_notes
    
    db.commit()
    
    # If status changed to approved, trigger download via Prowlarr
    if status_changing_to_approved:
        try:
            # Eager load book relationship
            from sqlalchemy.orm import joinedload
            db_request = db.query(models.BookRequest).options(
                joinedload(models.BookRequest.book)
            ).filter(models.BookRequest.id == db_request.id).first()

            if not db_request.book:
                logger.warning("request_approved_no_book", request_id=request_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot approve request: book not found"
                )

            orchestrator = DownloadOrchestrator(db_session=db)
            task = orchestrator.search_and_download(
                book=db_request.book,
                format_type=db_request.format,
                source_name="prowlarr"
            )

            if task:
                logger.info(
                    "approval_download_triggered",
                    request_id=request_id,
                    task_id=task.id,
                    format=db_request.format
                )
                db_request.status = "processing"
                db.commit()
            else:
                logger.warning(
                    "approval_download_no_releases",
                    request_id=request_id,
                    book_id=db_request.book_id,
                    format=db_request.format
                )
                # Keep as approved — admin can retry
        except HTTPException:
            raise
        except Exception as e:
            logger.error("request_approval_error", request_id=request_id, error=str(e))
            db_request.admin_notes = (
                (db_request.admin_notes or "") +
                f"\n[Error] Download search failed: {str(e)}"
            )
            db.commit()
    
    # Eager load relationships
    from sqlalchemy.orm import joinedload
    db_request = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    ).filter(models.BookRequest.id == db_request.id).first()
    
    # Convert book.genres from comma-separated string to list for response
    _normalize_book_genres(db_request.book if db_request else None)

    if db_request and db_request.book and db_request.book.hardcover_id:
        await delete_cached(
            make_cache_key("requests_by_hardcover", hardcover_id=db_request.book.hardcover_id)
        )
        # Clear batch caches
        await clear_cache_pattern("requests_by_hardcover_batch:*")

    return db_request

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(request_id: int, db: Session = Depends(database.get_db)):
    db_request = db.query(models.BookRequest).filter(models.BookRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
    hardcover_id = db_request.book.hardcover_id if db_request.book else None
    db.delete(db_request)
    db.commit()
    if hardcover_id:
        await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=hardcover_id))
        # Clear batch caches
        await clear_cache_pattern("requests_by_hardcover_batch:*")
    return None


async def update_processing_requests_status(db: Session) -> None:
    """Background task to check DownloadTask table and update processing requests."""
    try:
        from sqlalchemy.orm import joinedload
        not_found_after = timedelta(hours=6)
        now = datetime.now(timezone.utc)

        # Get all processing requests
        processing_requests = db.query(models.BookRequest).options(
            joinedload(models.BookRequest.book)
        ).filter(
            models.BookRequest.status == "processing"
        ).all()

        if not processing_requests:
            logger.debug("no_processing_requests_to_check")
            return

        logger.info("checking_processing_requests", count=len(processing_requests))

        updated_count = 0
        for req in processing_requests:
            if not req.book:
                logger.warning("request_missing_book", request_id=req.id)
                continue

            # Look for a completed + imported DownloadTask for this book+format
            completed_task = db.query(models.DownloadTask).filter(
                models.DownloadTask.book_id == req.book_id,
                models.DownloadTask.format == req.format,
                models.DownloadTask.state == "complete",
                models.DownloadTask.import_status == "imported",
            ).first()

            if completed_task:
                req.status = "available"
                req.updated_at = now

                # Set per-format availability on the book
                if req.format == "ebook":
                    req.book.ebook_available = True
                elif req.format == "audiobook":
                    req.book.audiobook_available = True
                db.add(req.book)

                updated_count += 1
                logger.info("request_marked_available",
                          request_id=req.id,
                          book_title=req.book.title,
                          format=req.format,
                          task_id=completed_task.id)
                continue

            # No completed task — check if we should mark as not_found
            active_task = db.query(models.DownloadTask).filter(
                models.DownloadTask.book_id == req.book_id,
                models.DownloadTask.format == req.format,
                models.DownloadTask.state.notin_(["complete", "error"]),
            ).first()

            if active_task:
                # Still downloading — leave as processing
                logger.debug("request_still_downloading",
                           request_id=req.id,
                           book_title=req.book.title,
                           task_state=active_task.state)
                continue

            # No active task — check age for not_found timeout
            last_touch = req.updated_at or req.created_at
            if last_touch and last_touch.tzinfo is None:
                last_touch = last_touch.replace(tzinfo=timezone.utc)
            if last_touch is None:
                last_touch = now

            if (now - last_touch) >= not_found_after:
                req.status = "not_found"
                req.updated_at = now
                updated_count += 1
                logger.info("request_marked_not_found",
                          request_id=req.id,
                          book_title=req.book.title,
                          format=req.format)
            else:
                logger.debug("request_waiting",
                           request_id=req.id,
                           book_title=req.book.title,
                           age_seconds=(now - last_touch).total_seconds())

        if updated_count > 0:
            db.commit()
            logger.info("processing_requests_updated",
                       updated_count=updated_count,
                       total_checked=len(processing_requests))
        else:
            logger.info("no_requests_updated",
                       total_checked=len(processing_requests))

    except Exception as e:
        logger.error("update_processing_requests_error", error=str(e))
        import traceback
        logger.error("update_processing_requests_traceback", traceback=traceback.format_exc())
        db.rollback()

@router.post("/check-status", status_code=status.HTTP_200_OK)
async def check_processing_requests_status(
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Manually trigger status check for processing requests (admin only)"""
    background_tasks.add_task(update_processing_requests_status, db)
    return {"message": "Status check initiated"}