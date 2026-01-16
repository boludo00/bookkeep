from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import structlog
from app import database, models, schemas
from app.cache import get_cached, set_cached, delete_cached, make_cache_key, CACHE_TTL
from app.auth import get_current_user, require_admin
from app.routers.readarr import add_book_to_readarr
from app.services.readarr_service import (
    ReadarrClient,
    get_readarr_server_for_format,
    is_format_available_in_readarr,
    get_readarr_availability_map,
)
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

    # Block requests for formats already available in Readarr
    try:
        if book.hardcover_id and await is_format_available_in_readarr(
            db,
            book.hardcover_id,
            request.format,
            isbns=[book.isbn] if book.isbn else None,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{request.format.capitalize()} already available in Readarr."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("readarr_availability_check_failed", error=str(e))

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
        # Re-open the request and re-send to Readarr below.
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
            "requested": f"The {format_label} has already been requested and is pending approval.",
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
    initial_status = "approved" if auto_approve else "requested"
    if existing_request and existing_request.status == "not_found":
        db_request.status = initial_status
        db_request.notes = request.notes
        db_request.admin_notes = None
        db_request.readarr_received = None
        db_request.readarr_search_triggered = None
        db_request.readarr_search_status_code = None
        db_request.readarr_message = None
        db_request.edition_id = request.edition_id
        db_request.updated_at = datetime.now()
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
    
    # Automatically add to Readarr if auto-approved or if manually approved
    if auto_approve or db_request.status == "approved":
        try:
            # Get appropriate Readarr server based on format
            readarr_server = get_readarr_server_for_format(db_request.format, db)
            
            if readarr_server:
                # Refresh server from database to ensure we have latest config
                db.refresh(readarr_server)
                logger.info("readarr_server_selected", 
                           server_id=readarr_server.id,
                           server_name=readarr_server.name,
                           format=db_request.format,
                           auto_approve=auto_approve)
                # Add book to Readarr
                try:
                    result = await add_book_to_readarr(
                        readarr_server,
                        db_request.book,
                        db_request.format,
                        db,
                        edition_id=db_request.edition_id
                    )
                    readarr_book_id = result.get("readarr_book_id")
                    db_request.readarr_received = result.get("readarr_received")
                    db_request.readarr_search_triggered = result.get("search_triggered")
                    db_request.readarr_search_status_code = result.get("search_status_code")
                    db_request.readarr_message = result.get("message")
                    logger.info(
                        "request_sent_to_readarr_on_create",
                        request_id=db_request.id,
                        readarr_book_id=readarr_book_id,
                        server_id=readarr_server.id,
                        auto_approve=auto_approve
                    )
                    # Update status to processing and store readarr_book_id
                    db_request.status = "processing"
                    if readarr_book_id:
                        db_request.readarr_book_id = readarr_book_id
                    db.commit()
                    # Refresh to get updated status
                    db.refresh(db_request)
                except Exception as e:
                    logger.error(
                        "readarr_add_failed_on_create",
                        request_id=db_request.id,
                        error=str(e)
                    )
                    # If Readarr add fails, do not keep the request around.
                    db.delete(db_request)
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Failed to add to Readarr: {str(e)}"
                    )
            else:
                logger.warning(
                    "request_created_no_readarr_server",
                    request_id=db_request.id,
                    format=db_request.format
                )
                # Keep status as requested/approved if no Readarr server configured
        except HTTPException:
            raise
        except Exception as e:
            logger.error("request_creation_error", request_id=db_request.id, error=str(e))
            # Don't fail the request creation, just log the error
    
    # Convert book.genres from comma-separated string to list for response
    _normalize_book_genres(db_request.book)

    if book.hardcover_id:
        await delete_cached(make_cache_key("requests_by_hardcover", hardcover_id=book.hardcover_id))

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
        "ebook_readarr_book_id": None,
        "audiobook_readarr_book_id": None,
        "book_id": book.id,
    }
    for r in requests:
        result[r.format] = r.status
        if r.format == "ebook":
            result["ebook_readarr_book_id"] = r.readarr_book_id
        elif r.format == "audiobook":
            result["audiobook_readarr_book_id"] = r.readarr_book_id
    
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
    books_in_series = db.query(models.Book).filter(
        models.Book.series_id == series_id
    ).order_by(models.Book.series_position.asc().nulls_last()).all()
    
    if not books_in_series:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No books found in this series"
        )
    
    requested_count = 0
    skipped_count = 0
    already_available = 0
    already_requested = 0

    availability_map = {}
    hardcover_ids = [book.hardcover_id for book in books_in_series if book.hardcover_id]
    isbn_map = {
        int(book.hardcover_id): [book.isbn]
        for book in books_in_series
        if book.hardcover_id and book.isbn
    }
    if hardcover_ids:
        try:
            availability_map = await get_readarr_availability_map(db, hardcover_ids, isbn_map=isbn_map)
        except Exception as e:
            logger.warning("series_readarr_availability_failed", error=str(e))
    
    for book in books_in_series:
        # Check if book is already available for this format (Readarr preferred)
        readarr_availability = availability_map.get(book.hardcover_id or 0, {})
        readarr_has_format = (
            (format == "ebook" and readarr_availability.get("ebook"))
            or (format == "audiobook" and readarr_availability.get("audiobook"))
        )
        if readarr_has_format or (format == "ebook" and book.ebook_available):
            already_available += 1
            skipped_count += 1
            continue
        elif format == "audiobook" and book.audiobook_available:
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
        
        initial_status = "approved" if should_auto_approve else "requested"
        
        # Create the request
        now = datetime.now()
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
        
        # Add to Readarr if auto-approved
        if should_auto_approve:
            readarr_server = get_readarr_server_for_format(format, db)
            if readarr_server:
                try:
                    result = await add_book_to_readarr(
                        readarr_server,
                        book,
                        format,
                        db,
                        edition_id=new_request.edition_id
                    )
                    readarr_book_id = result.get("readarr_book_id")
                    new_request.status = "processing"
                    if readarr_book_id:
                        new_request.readarr_book_id = readarr_book_id
                    logger.info("series_book_added_to_readarr",
                               series_id=series_id,
                               book_id=book.id,
                               book_title=book.title,
                               readarr_book_id=readarr_book_id)
                except Exception as e:
                    logger.warning("series_book_readarr_failed",
                                  series_id=series_id,
                                  book_id=book.id,
                                  book_title=book.title,
                                  error=str(e))
                    new_request.notes = (new_request.notes or "") + f"\n[Error] Readarr: {str(e)}"
            else:
                logger.warning("series_book_no_readarr_server",
                              series_id=series_id,
                              book_id=book.id,
                              format=format)
        
        requested_count += 1
        
        logger.info("series_book_requested",
                   series_id=series_id,
                   book_id=book.id,
                   book_title=book.title,
                   format=format,
                   status=new_request.status,
                   user_id=current_user.id)
    
    db.commit()
    
    logger.info("series_request_complete",
               series_id=series_id,
               requested_count=requested_count,
               skipped_count=skipped_count,
               already_available=already_available,
               already_requested=already_requested,
               format=format,
               user_id=current_user.id)
    
    return {
        "series_id": series_id,
        "format": format,
        "requested_count": requested_count,
        "skipped_count": skipped_count,
        "already_available": already_available,
        "already_requested": already_requested,
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
    
    # If status changed to approved, send to Readarr
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
            
            # Get appropriate Readarr server based on format
            readarr_server = get_readarr_server_for_format(db_request.format, db)
            
            if not readarr_server:
                logger.warning(
                    "request_approved_no_readarr_server",
                    request_id=request_id,
                    format=db_request.format
                )
                # Don't fail the request, just log it
                db_request.admin_notes = (
                    (db_request.admin_notes or "") + 
                    "\n[Warning] No Readarr server configured for this format."
                )
                db.commit()
            else:
                # Add book to Readarr
                try:
                    result = await add_book_to_readarr(
                        readarr_server,
                        db_request.book,
                        db_request.format,
                        db,
                        edition_id=db_request.edition_id
                    )
                    readarr_book_id = result.get("readarr_book_id")
                    logger.info(
                        "request_sent_to_readarr",
                        request_id=request_id,
                        readarr_book_id=readarr_book_id,
                        server_id=readarr_server.id
                    )
                    # Store readarr_book_id in the column
                    if readarr_book_id:
                        db_request.readarr_book_id = readarr_book_id
                    # Update status to processing
                    db_request.status = "processing"
                    db.commit()
                except Exception as e:
                    logger.error(
                        "readarr_add_failed",
                        request_id=request_id,
                        error=str(e)
                    )
                    # Update admin notes with error
                    db_request.admin_notes = (
                        (db_request.admin_notes or "") + 
                        f"\n[Error] Failed to add to Readarr: {str(e)}"
                    )
                    db.commit()
                    # Don't fail the request approval, just log the error
        except Exception as e:
            logger.error("request_approval_error", request_id=request_id, error=str(e))
            # Don't fail the request update, just log the error
    
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
    return None

def _extract_readarr_book_id_from_notes(admin_notes: str) -> Optional[int]:
    """Extract readarr_book_id from admin_notes (legacy storage)"""
    if not admin_notes:
        return None
    import re
    match = re.search(r'\[Readarr Book ID: (\d+)\]', admin_notes)
    if match:
        return int(match.group(1))
    return None


async def _lookup_readarr_book_id(server: models.ReadarrServer, hardcover_id: int) -> Optional[int]:
    """Look up a book in Readarr by Hardcover ID and return the Readarr book ID"""
    from app.services.readarr_service import build_readarr_url
    import httpx
    
    base_url = build_readarr_url(server.hostname, server.port, server.use_ssl, server.url_base)
    api_url = f"{base_url}/api/v1"
    
    headers = {
        "X-Api-Key": server.api_key,
        "Content-Type": "application/json"
    }
    
    logger.info("lookup_readarr_book_id_starting",
               hardcover_id=hardcover_id,
               api_url=api_url)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Search for the book by foreignBookId (Hardcover ID)
            # First try to get all books and find the matching one
            response = await client.get(
                f"{api_url}/book",
                headers=headers
            )
            
            logger.info("readarr_book_list_response",
                       status_code=response.status_code,
                       content_length=len(response.content) if response.content else 0)
            
            if response.status_code == 200:
                books = response.json()
                logger.info("readarr_library_books",
                           total_books=len(books),
                           sample_foreign_ids=[str(b.get("foreignBookId")) for b in books[:5]] if books else [])
                
                for book in books:
                    foreign_id = book.get("foreignBookId")
                    if str(foreign_id) == str(hardcover_id):
                        readarr_book_id = book.get("id")
                        logger.info("found_readarr_book_id",
                                   hardcover_id=hardcover_id,
                                   readarr_book_id=readarr_book_id,
                                   title=book.get("title"))
                        return readarr_book_id
                
                logger.warning("book_not_found_in_readarr_library",
                             hardcover_id=hardcover_id,
                             searched_books_count=len(books))
            else:
                logger.warning("readarr_book_lookup_failed",
                             hardcover_id=hardcover_id,
                             status_code=response.status_code,
                             response_text=response.text[:200] if response.text else None)
    except Exception as e:
        logger.error("readarr_book_lookup_error",
                    hardcover_id=hardcover_id,
                    error=str(e),
                    error_type=type(e).__name__)
    
    return None


async def update_processing_requests_status(db: Session) -> None:
    """Background task to check Readarr for book availability and update processing requests"""
    try:
        from sqlalchemy.orm import joinedload
        not_found_after = timedelta(hours=6)
        
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
        
        # Get Readarr servers for each format
        ebook_server = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_audiobook == False
        ).first()
        
        audiobook_server = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_audiobook == True
        ).first()
        
        if not ebook_server and not audiobook_server:
            logger.warning("no_readarr_servers_configured")
            return
        
        logger.info("using_readarr_servers", 
                   ebook_server_id=ebook_server.id if ebook_server else None,
                   audiobook_server_id=audiobook_server.id if audiobook_server else None)
        
        # Check each request against the appropriate Readarr server
        updated_count = 0
        for req in processing_requests:
            if not req.book:
                logger.warning("request_missing_book", request_id=req.id)
                continue
            
            if not req.book.hardcover_id:
                logger.warning("request_missing_hardcover_id",
                             request_id=req.id,
                             book_title=req.book.title)
                continue
            
            # Select the appropriate server based on request format
            server = None
            if req.format == "audiobook":
                server = audiobook_server
            else:  # ebook or default
                server = ebook_server
            
            if not server:
                logger.warning("no_server_for_format",
                             request_id=req.id,
                             format=req.format)
                continue
            
            logger.debug("checking_request_in_readarr",
                        request_id=req.id,
                        book_title=req.book.title,
                        format=req.format,
                        hardcover_id=req.book.hardcover_id,
                        server_id=server.id)
            
            # Check if book exists in Readarr and has files
            readarr_client = ReadarrClient.from_server(server)
            book_data = await readarr_client.find_book_in_library(None, req.book.hardcover_id)
            last_touch = req.updated_at or req.created_at
            if last_touch and last_touch.tzinfo is None:
                last_touch = last_touch.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if last_touch is None:
                last_touch = now
            
            if book_data:
                file_count = book_data.get("statistics", {}).get("bookFileCount", 0)
                readarr_book_id = book_data.get("id")
                
                if file_count > 0:
                    # Book has files - mark as available
                    req.status = "available"
                    req.updated_at = now
                    db.add(req)
                    
                    # Set per-format availability on the book
                    if req.format == "ebook":
                        req.book.ebook_available = True
                    elif req.format == "audiobook":
                        req.book.audiobook_available = True
                    db.add(req.book)
                    
                    updated_count += 1
                    logger.info("request_marked_available_from_readarr",
                              request_id=req.id,
                              book_title=req.book.title,
                              format=req.format,
                              hardcover_id=req.book.hardcover_id,
                              readarr_book_id=readarr_book_id,
                              file_count=file_count)
                else:
                    # If it's been processing for a while with no queue/history, mark not_found.
                    download_status = await readarr_client.check_book_download_status(None, readarr_book_id)
                    if (
                        download_status.get("status") == "unknown"
                        and (now - last_touch) >= not_found_after
                    ):
                        req.status = "not_found"
                        req.updated_at = now
                        db.add(req)
                        updated_count += 1
                        logger.info("request_marked_not_found",
                                  request_id=req.id,
                                  book_title=req.book.title,
                                  format=req.format,
                                  hardcover_id=req.book.hardcover_id,
                                  readarr_book_id=readarr_book_id)
                    else:
                        logger.debug("book_in_readarr_no_files",
                                   request_id=req.id,
                                   book_title=req.book.title,
                                   format=req.format,
                                   readarr_book_id=readarr_book_id,
                                   download_status=download_status.get("status"))
            else:
                if (now - last_touch) >= not_found_after:
                    req.status = "not_found"
                    req.updated_at = now
                    db.add(req)
                    updated_count += 1
                    logger.info("request_marked_not_found_no_readarr_book",
                              request_id=req.id,
                              book_title=req.book.title,
                              format=req.format,
                              hardcover_id=req.book.hardcover_id)
                else:
                    logger.debug("book_not_in_readarr",
                               request_id=req.id,
                               book_title=req.book.title,
                               format=req.format,
                               hardcover_id=req.book.hardcover_id)
        
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
