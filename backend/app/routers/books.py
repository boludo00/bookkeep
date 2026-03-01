from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import structlog
import httpx
from app import database, models, schemas, cache
from app.auth import require_admin, get_current_user

logger = structlog.get_logger()
router = APIRouter()


async def check_book_availability(book: models.Book, db: Session) -> dict:
    """Check if a book exists in Booklore or Audiobookshelf and update availability flags."""
    # Preserve existing availability — only set True, never reset to False
    ebook_available = bool(book.ebook_available)
    audiobook_available = bool(book.audiobook_available)
    checked_sources = []

    # Check Booklore
    booklore_server = db.query(models.BookloreServer).filter(
        models.BookloreServer.is_default == True
    ).first()

    if booklore_server and book.hardcover_id:
        try:
            # Get or refresh token
            from app.routers.booklore import get_booklore_token
            token = await get_booklore_token(booklore_server, db)

            if token:
                async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                    headers = {"Authorization": f"Bearer {token}"}

                    # Check by hardcover ID
                    response = await client.get(
                        f"{booklore_server.url}/api/v1/books",
                        headers=headers,
                        params={"withDescription": "false"}
                    )

                    if response.status_code == 200:
                        books_data = response.json()
                        for bl_book in books_data:
                            metadata = bl_book.get("metadata", {})
                            bl_hardcover_id = metadata.get("hardcoverId")

                            # Check if hardcover ID matches (numeric or slug)
                            if bl_hardcover_id:
                                if str(bl_hardcover_id) == str(book.hardcover_id) or \
                                   str(bl_hardcover_id) == str(book.hardcover_slug):
                                    # Determine format from bookType and library mapping
                                    book_type = bl_book.get("bookType", "").lower()
                                    bl_library_id = bl_book.get("libraryId")

                                    if "audio" in book_type:
                                        audiobook_available = True
                                    elif bl_library_id and booklore_server.audiobook_library_id and bl_library_id == booklore_server.audiobook_library_id:
                                        audiobook_available = True
                                    elif bl_library_id and booklore_server.ebook_library_id and bl_library_id == booklore_server.ebook_library_id:
                                        ebook_available = True
                                    else:
                                        # Default: if no bookType or library mapping, mark as ebook
                                        ebook_available = True

                                    checked_sources.append(f"booklore:{booklore_server.name}")
                                    # Don't break — same book may exist in multiple libraries
        except Exception as e:
            logger.warning("booklore_availability_check_failed",
                          book_id=book.id,
                          error=str(e))

    # Check Audiobookshelf
    from app.routers.audiobookshelf import (
        get_default_audiobookshelf_server, search_audiobookshelf_items, match_book_to_abs_item,
    )
    abs_server = get_default_audiobookshelf_server(db)

    if abs_server and book.hardcover_id:
        try:
            # Fast path: already linked
            if book.audiobookshelf_id:
                audiobook_available = True
                checked_sources.append(f"audiobookshelf:{abs_server.name}")
            else:
                search_query = book.title or ""
                if book.author:
                    search_query = f"{search_query} {book.author}"
                items = await search_audiobookshelf_items(abs_server, search_query.strip())
                for item in items:
                    if match_book_to_abs_item(book, item):
                        book.audiobookshelf_id = item.get("id")
                        audiobook_available = True
                        checked_sources.append(f"audiobookshelf:{abs_server.name}")
                        break
        except Exception as e:
            logger.warning("audiobookshelf_availability_check_failed",
                          book_id=book.id,
                          error=str(e))

    # Update book availability
    book.ebook_available = ebook_available
    book.audiobook_available = audiobook_available
    book.last_refreshed = datetime.now(timezone.utc)

    updated_requests = 0
    if ebook_available or audiobook_available:
        requests = db.query(models.BookRequest).filter(
            models.BookRequest.book_id == book.id,
            models.BookRequest.status != "denied",
        ).all()
        for request in requests:
            if request.status == "available":
                continue
            if request.format == "ebook" and ebook_available:
                request.status = "available"
            elif request.format == "audiobook" and audiobook_available:
                request.status = "available"
            else:
                continue
            request.updated_at = datetime.now(timezone.utc)
            db.add(request)
            updated_requests += 1

    db.add(book)
    db.commit()
    
    logger.info("book_availability_refreshed",
               book_id=book.id,
               book_title=book.title,
               ebook_available=ebook_available,
               audiobook_available=audiobook_available,
               checked_sources=checked_sources,
               updated_requests=updated_requests)
    
    return {
        "book_id": book.id,
        "title": book.title,
        "ebook_available": ebook_available,
        "audiobook_available": audiobook_available,
        "checked_sources": checked_sources
    }

@router.post("/", response_model=schemas.BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(book: schemas.BookCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(require_admin)):
    book_dict = book.model_dump()
    
    # Check if book already exists by hardcover_id
    if book_dict.get("hardcover_id"):
        existing = db.query(models.Book).filter(models.Book.hardcover_id == book_dict["hardcover_id"]).first()
        if existing:
            # Update existing book instead of creating duplicate
            # Convert genres list to comma-separated string for database storage
            if book_dict.get("genres") and isinstance(book_dict["genres"], list):
                book_dict["genres"] = ", ".join(book_dict["genres"])
            for key, value in book_dict.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            # Convert genres back to list for response
            response_dict = {
                **{k: v for k, v in existing.__dict__.items() if not k.startswith('_')},
                "genres": [g.strip() for g in existing.genres.split(',')] if existing.genres else []
            }
            return schemas.BookResponse(**response_dict)
    
    # Convert genres list to comma-separated string for database storage
    if book_dict.get("genres") and isinstance(book_dict["genres"], list):
        book_dict["genres"] = ", ".join(book_dict["genres"])
    
    # Double-check before inserting (handle race conditions)
    if book_dict.get("hardcover_id"):
        final_check = db.query(models.Book).filter(models.Book.hardcover_id == book_dict["hardcover_id"]).first()
        if final_check:
            # Book was inserted between checks - update it
            for key, value in book_dict.items():
                setattr(final_check, key, value)
            db.commit()
            db.refresh(final_check)
            response_dict = {
                **{k: v for k, v in final_check.__dict__.items() if not k.startswith('_')},
                "genres": [g.strip() for g in final_check.genres.split(',')] if final_check.genres else []
            }
            return schemas.BookResponse(**response_dict)
    
    # Create new book
    try:
        db_book = models.Book(**book_dict)
        db.add(db_book)
        db.flush()  # Flush to catch constraint violations early
        db.commit()
        db.refresh(db_book)
    except IntegrityError:
        # Handle race condition - book was inserted between check and insert
        db.rollback()
        if book_dict.get("hardcover_id"):
            existing = db.query(models.Book).filter(models.Book.hardcover_id == book_dict["hardcover_id"]).first()
            if existing:
                # Update existing book
                for key, value in book_dict.items():
                    setattr(existing, key, value)
                db.commit()
                db.refresh(existing)
                db_book = existing
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create book - duplicate constraint violation"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create book - duplicate constraint violation"
            )
    
    # Convert genres back to list for response
    response_dict = {
        **{k: v for k, v in db_book.__dict__.items() if not k.startswith('_')},
        "genres": [g.strip() for g in db_book.genres.split(',')] if db_book.genres else []
    }
    return schemas.BookResponse(**response_dict)

@router.get("/{book_id}", response_model=schemas.BookResponse)
def get_book(book_id: int, db: Session = Depends(database.get_db)):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    # Convert genres string to list for response
    response_dict = {
        **{k: v for k, v in db_book.__dict__.items() if not k.startswith('_')},
        "genres": [g.strip() for g in db_book.genres.split(',')] if db_book.genres else []
    }
    return schemas.BookResponse(**response_dict)

@router.get("/", response_model=list[schemas.BookResponse])
def get_books(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    books = db.query(models.Book).offset(skip).limit(limit).all()
    # Convert genres string to list for each book
    return [
        schemas.BookResponse(
            **{
                **{k: v for k, v in book.__dict__.items() if not k.startswith('_')},
                "genres": [g.strip() for g in book.genres.split(',')] if book.genres else []
            }
        )
        for book in books
    ]

@router.put("/{book_id}", response_model=schemas.BookResponse)
def update_book(book_id: int, book: schemas.BookCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(require_admin)):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    book_dict = book.model_dump()
    # Convert genres list to comma-separated string for database storage
    if book_dict.get("genres") and isinstance(book_dict["genres"], list):
        book_dict["genres"] = ", ".join(book_dict["genres"])
    
    # Convert series_position from float to int if needed
    if book_dict.get("series_position") is not None:
        pos = book_dict["series_position"]
        if isinstance(pos, float):
            if pos.is_integer():
                book_dict["series_position"] = int(pos)
            else:
                book_dict["series_position"] = None  # Skip partial positions
        elif not isinstance(pos, int):
            book_dict["series_position"] = None
    
    for key, value in book_dict.items():
        setattr(db_book, key, value)
    db.commit()
    db.refresh(db_book)
    # Convert genres back to list for response
    response_dict = {
        **{k: v for k, v in db_book.__dict__.items() if not k.startswith('_')},
        "genres": [g.strip() for g in db_book.genres.split(',')] if db_book.genres else []
    }
    return schemas.BookResponse(**response_dict)

@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(require_admin)):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    db.delete(db_book)
    db.commit()
    return None


@router.post("/{book_id}/refresh")
async def refresh_book_availability(book_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    """Refresh availability status for a single book by checking Booklore and Audiobookshelf."""
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    result = await check_book_availability(db_book, db)
    return result


@router.post("/by-hardcover/{hardcover_id}/refresh")
async def refresh_book_by_hardcover_id(hardcover_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    """Refresh availability status for a book by its Hardcover ID."""
    db_book = db.query(models.Book).filter(models.Book.hardcover_id == hardcover_id).first()
    if not db_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    result = await check_book_availability(db_book, db)
    return result


@router.post("/series/{series_id}/refresh")
async def refresh_series_availability(series_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(get_current_user)):
    """Refresh availability status for all books in a series."""
    books = db.query(models.Book).filter(models.Book.series_id == series_id).all()
    
    if not books:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No books found in this series"
        )
    
    results = []
    ebook_count = 0
    audiobook_count = 0
    
    for book in books:
        try:
            result = await check_book_availability(book, db)
            results.append(result)
            if result["ebook_available"]:
                ebook_count += 1
            if result["audiobook_available"]:
                audiobook_count += 1
        except Exception as e:
            logger.warning("series_book_refresh_failed",
                          series_id=series_id,
                          book_id=book.id,
                          error=str(e))
    
    logger.info("series_availability_refreshed",
               series_id=series_id,
               total_books=len(books),
               ebooks_available=ebook_count,
               audiobooks_available=audiobook_count)

    cache_key = cache.make_cache_key("series", series_id=series_id)
    await cache.delete_cached(cache_key)
    
    return {
        "series_id": series_id,
        "total_books": len(books),
        "ebooks_available": ebook_count,
        "audiobooks_available": audiobook_count,
        "books": results
    }
