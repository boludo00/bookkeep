from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
import os
import httpx
import structlog
import time
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_
from app import schemas, cache, database, models
from app.models import Book, Series
from app.auth import require_admin

logger = structlog.get_logger()

router = APIRouter()

HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"

# Helper to get token, avoiding circular dependency with settings router
def get_hardcover_token() -> str:
    """Get Hardcover API token from env var or database"""
    # Check environment variable first (takes precedence)
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        return env_token
    
    # Check database (lazy import to avoid circular dependency)
    try:
        from app.database import SessionLocal
        from app.models import AppSettings
        db = SessionLocal()
        try:
            setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
            if setting and setting.value:
                return setting.value
        finally:
            db.close()
    except Exception as e:
        logger.debug("failed_to_load_token_from_db", error=str(e))
    
    return ""

# Log token status on module load (without exposing the actual token)
HARDCOVER_API_TOKEN = get_hardcover_token()
if HARDCOVER_API_TOKEN:
    token_source = "env" if os.getenv("HARDCOVER_API_TOKEN", "") else "db"
    logger.info("hardcover_api_token_loaded", token_length=len(HARDCOVER_API_TOKEN), source=token_source)
else:
    logger.warning("hardcover_api_token_missing", message="HARDCOVER_API_TOKEN not set in environment or database")

def _db_book_to_hardcover_book(db_book: Book) -> schemas.HardcoverBook:
    """Convert database Book model to HardcoverBook schema"""
    # Parse genres
    genres_list = []
    if db_book.genres:
        if isinstance(db_book.genres, str):
            genres_list = [g.strip() for g in db_book.genres.split(",") if g.strip()]
    
    # Parse authors
    authors = [db_book.author] if db_book.author else []
    
    # Build cached_image
    cached_image = None
    if db_book.cover_url:
        cached_image = schemas.HardcoverCachedImage(url=db_book.cover_url)
    
    # Build cached_contributors
    cached_contributors = None
    if authors:
        cached_contributors = [
            schemas.HardcoverCachedContributor(author={"name": author})
            for author in authors
        ]
    
    # Build book_series
    book_series = None
    if db_book.series:
        # Only include position if it's a valid positive number
        position = db_book.series_position if (db_book.series_position is not None and db_book.series_position > 0) else None
        # Use actual series_id from database, or 0 as fallback
        series_id = db_book.series_id if db_book.series_id is not None else 0
        book_series = [schemas.HardcoverBookSeries(
            series=schemas.HardcoverSeries(id=series_id, name=db_book.series),
            position=position
        )]
    
    # Build contributions
    contributions = None
    if authors:
        contributions = [
            schemas.HardcoverContribution(
                author=schemas.HardcoverAuthor(id=0, name=author) # ID 0 as placeholder
            )
            for author in authors
        ]
    
    # Build taggings
    taggings = None
    if genres_list:
        taggings = [
            schemas.HardcoverTagging(tag=schemas.HardcoverTag(tag=genre))
            for genre in genres_list[:5]
        ]
    
    return schemas.HardcoverBook(
        id=db_book.hardcover_id or 0, # Use 0 if None
        title=db_book.title,
        slug=db_book.hardcover_slug,
        default_edition_id=db_book.default_edition_id,
        default_physical_edition_id=db_book.default_physical_edition_id,
        default_ebook_edition_id=db_book.default_ebook_edition_id,
        default_audio_edition_id=db_book.default_audio_edition_id,
        release_year=db_book.release_year,
        release_date=db_book.published_date,
        pages=db_book.page_count,
        description=db_book.description or "",
        cached_image=cached_image,
        cached_contributors=cached_contributors,
        rating=db_book.rating,
        ratings_count=db_book.ratings_count,
        users_count=db_book.users_count,
        activities_count=db_book.activities_count,
        book_series=book_series,
        contributions=contributions,
        taggings=taggings,
        ebook_available=db_book.ebook_available or False,
        audiobook_available=db_book.audiobook_available or False,
    )

def _sample_response(data: dict, max_items: int = 3) -> dict:
    """Create a sample of the response data for logging"""
    if not isinstance(data, dict):
        return {"sample": str(data)[:200]}
    
    sampled = {}
    for key, value in data.items():
        if isinstance(value, list):
            # Sample first few items
            sampled[key] = {
                "count": len(value),
                "sample": value[:max_items] if len(value) > max_items else value
            }
        elif isinstance(value, dict):
            # Recursively sample nested dicts
            sampled[key] = _sample_response(value, max_items)
        else:
            sampled[key] = value
    
    return sampled


def _enrich_books_with_availability(books: list, db: Session) -> list:
    """Enrich a list of HardcoverBook objects with local availability data from database"""
    if not books:
        return books
    
    # Get all hardcover IDs from the books
    hardcover_ids = [book.id for book in books if book.id]
    
    if not hardcover_ids:
        return books
    
    # Query local database for availability in one batch
    local_books = db.query(Book).filter(Book.hardcover_id.in_(hardcover_ids)).all()
    
    # Create a map of hardcover_id -> (ebook_available, audiobook_available)
    availability_map = {
        book.hardcover_id: (book.ebook_available, book.audiobook_available)
        for book in local_books
    }
    
    # Enrich each book with availability data
    enriched_books = []
    for book in books:
        availability = availability_map.get(book.id, (False, False))
        # Create a new book with updated availability
        book_dict = book.model_dump()
        book_dict['ebook_available'] = availability[0]
        book_dict['audiobook_available'] = availability[1]
        enriched_books.append(schemas.HardcoverBook.model_validate(book_dict))
    
    return enriched_books


def _parse_hardcover_book(book_data: dict) -> schemas.HardcoverBook:
    """Safely parse a Hardcover book from API response"""
    # Pre-process the data to handle complex types before validation
    book_dict = book_data.copy()
    
    if "default_physical_edition_id" in book_dict and "default_edition_id" not in book_dict:
        book_dict["default_edition_id"] = book_dict.get("default_physical_edition_id")
    if "default_edition_id" in book_dict and "default_physical_edition_id" not in book_dict:
        book_dict["default_physical_edition_id"] = book_dict.get("default_edition_id")

    # Handle cached_image - convert dict to model or set to None
    if isinstance(book_dict.get("cached_image"), dict):
        try:
            book_dict["cached_image"] = schemas.HardcoverCachedImage(**book_dict["cached_image"])
        except Exception as e:
            logger.debug("failed_to_parse_cached_image", error=str(e), image_data=book_dict.get("cached_image"))
            book_dict["cached_image"] = None
    elif book_dict.get("cached_image") is None:
        book_dict["cached_image"] = None
    
    # Handle cached_contributors - convert list to models or set to None
    if isinstance(book_dict.get("cached_contributors"), list):
        try:
            book_dict["cached_contributors"] = [
                schemas.HardcoverCachedContributor(**item) if isinstance(item, dict) else item
                for item in book_dict["cached_contributors"]
            ]
        except Exception as e:
            logger.debug("failed_to_parse_cached_contributors", error=str(e))
            book_dict["cached_contributors"] = None
    elif book_dict.get("cached_contributors") is None:
        book_dict["cached_contributors"] = None
    
    try:
        return schemas.HardcoverBook.model_validate(book_dict)
    except Exception as e:
        logger.warning(
            "hardcover_book_validation_error",
            book_id=book_dict.get("id"),
            error=str(e),
            book_data_sample=_sample_response(book_dict, max_items=1)
        )
        # Final fallback: create book with minimal required fields
        return schemas.HardcoverBook(
            id=book_dict.get("id", 0),
            title=book_dict.get("title", "Unknown"),
            slug=book_dict.get("slug"),
            default_edition_id=book_dict.get("default_edition_id"),
            default_physical_edition_id=book_dict.get("default_physical_edition_id"),
            default_ebook_edition_id=book_dict.get("default_ebook_edition_id"),
            default_audio_edition_id=book_dict.get("default_audio_edition_id"),
            release_year=book_dict.get("release_year"),
            release_date=book_dict.get("release_date"),
            pages=book_dict.get("pages"),
            description=book_dict.get("description"),
            cached_image=book_dict.get("cached_image"),
            cached_contributors=book_dict.get("cached_contributors"),
            rating=book_dict.get("rating"),
            ratings_count=book_dict.get("ratings_count"),
            users_count=book_dict.get("users_count"),
            book_series=None,
            contributions=None,
            taggings=None,
        )

def _save_book_to_db(book_data: dict, db: Session) -> Optional[Book]:
    """Save a book from API response to database"""
    hardcover_id = book_data.get("id")
    if not hardcover_id:
        return None
    
    # ALWAYS check if book already exists FIRST - use flush to ensure we see pending inserts
    existing = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
    
    # If book exists, update it and return early
    if existing:
        # Transform API data to database format
        if "default_physical_edition_id" in book_data and "default_edition_id" not in book_data:
            book_data["default_edition_id"] = book_data.get("default_physical_edition_id")
        if "default_edition_id" in book_data and "default_physical_edition_id" not in book_data:
            book_data["default_physical_edition_id"] = book_data.get("default_edition_id")
        authors = []
        author_id = None
        if book_data.get("contributions"):
            authors = [c["author"]["name"] for c in book_data["contributions"] if c.get("author", {}).get("name")]
            # Extract first author's ID from contributions
            if book_data["contributions"] and book_data["contributions"][0].get("author", {}).get("id"):
                author_id = book_data["contributions"][0]["author"]["id"]
        elif book_data.get("cached_contributors"):
            authors = [c.get("author", {}).get("name") or c.get("name", "") for c in book_data["cached_contributors"]]
        
        author = ", ".join(authors) if authors else "Unknown Author"
        
        # Extract cover URL
        cover_url = None
        if isinstance(book_data.get("cached_image"), dict):
            cover_url = book_data["cached_image"].get("url")
        
        # Extract series info
        series = None
        series_id = None
        series_position = None
        if book_data.get("book_series") and len(book_data["book_series"]) > 0:
            series_info = book_data["book_series"][0].get("series", {})
            series = series_info.get("name")
            series_id = series_info.get("id")
            series_position = book_data["book_series"][0].get("position")
        
        # Extract genres
        genres = []
        if book_data.get("taggings"):
            genres = [t["tag"]["tag"] for t in book_data["taggings"] if t.get("tag", {}).get("tag")]
        
        # Update existing book
        existing.title = book_data.get("title", "Unknown")
        existing.author = author
        existing.author_id = author_id  # Store author ID
        existing.description = book_data.get("description")
        existing.cover_url = cover_url
        existing.published_date = book_data.get("release_date") or str(book_data.get("release_year", ""))
        existing.rating = book_data.get("rating")
        existing.page_count = book_data.get("pages")
        existing.hardcover_slug = book_data.get("slug")
        if "default_edition_id" in book_data:
            existing.default_edition_id = book_data.get("default_edition_id")
        if "default_physical_edition_id" in book_data:
            existing.default_physical_edition_id = book_data.get("default_physical_edition_id")
        if "default_ebook_edition_id" in book_data:
            existing.default_ebook_edition_id = book_data.get("default_ebook_edition_id")
        if "default_audio_edition_id" in book_data:
            existing.default_audio_edition_id = book_data.get("default_audio_edition_id")
        existing.series = series
        existing.series_id = series_id
        existing.series_position = series_position
        existing.genres = ", ".join(genres) if genres else None
        existing.ratings_count = book_data.get("ratings_count")
        existing.users_count = book_data.get("users_count")
        existing.activities_count = book_data.get("activities_count")
        existing.release_year = book_data.get("release_year")
        existing.is_seed_data = False
        existing.last_refreshed = datetime.now()
        
        try:
            db.commit()
            db.refresh(existing)
            return existing
        except Exception as e:
            logger.warning("failed_to_update_book_in_db", book_id=hardcover_id, error=str(e))
            db.rollback()
            return existing
    
    # Book doesn't exist - create new one
    # Transform API data to database format
    if "default_physical_edition_id" in book_data and "default_edition_id" not in book_data:
        book_data["default_edition_id"] = book_data.get("default_physical_edition_id")
    if "default_edition_id" in book_data and "default_physical_edition_id" not in book_data:
        book_data["default_physical_edition_id"] = book_data.get("default_edition_id")
    authors = []
    author_id = None
    if book_data.get("contributions"):
        authors = [c["author"]["name"] for c in book_data["contributions"] if c.get("author", {}).get("name")]
        # Extract first author's ID from contributions
        if book_data["contributions"] and book_data["contributions"][0].get("author", {}).get("id"):
            author_id = book_data["contributions"][0]["author"]["id"]
    elif book_data.get("cached_contributors"):
        authors = [c.get("author", {}).get("name") or c.get("name", "") for c in book_data["cached_contributors"]]
    
    author = ", ".join(authors) if authors else "Unknown Author"
    
    # Extract cover URL
    cover_url = None
    if isinstance(book_data.get("cached_image"), dict):
        cover_url = book_data["cached_image"].get("url")
    
    # Extract series info
    series = None
    series_id = None
    series_position = None
    if book_data.get("book_series") and len(book_data["book_series"]) > 0:
        series_info = book_data["book_series"][0].get("series", {})
        series = series_info.get("name")
        series_id = series_info.get("id")
        series_position = book_data["book_series"][0].get("position")
    
    # Extract genres
    genres = []
    if book_data.get("taggings"):
        genres = [t["tag"]["tag"] for t in book_data["taggings"] if t.get("tag", {}).get("tag")]
    
    book_dict = {
        "title": book_data.get("title", "Unknown"),
        "author": author,
        "author_id": author_id,  # Store author ID
        "description": book_data.get("description"),
        "cover_url": cover_url,
        "published_date": book_data.get("release_date") or str(book_data.get("release_year", "")),
        "rating": book_data.get("rating"),
        "page_count": book_data.get("pages"),
        "hardcover_id": hardcover_id,
        "hardcover_slug": book_data.get("slug"),
        "default_edition_id": book_data.get("default_edition_id"),
        "default_physical_edition_id": book_data.get("default_physical_edition_id"),
        "default_ebook_edition_id": book_data.get("default_ebook_edition_id"),
        "default_audio_edition_id": book_data.get("default_audio_edition_id"),
        "series": series,
        "series_id": series_id,
        "series_position": series_position,
        "genres": ", ".join(genres) if genres else None,
        "ratings_count": book_data.get("ratings_count"),
        "users_count": book_data.get("users_count"),
        "activities_count": book_data.get("activities_count"),
        "release_year": book_data.get("release_year"),
        "is_seed_data": False,  # Mark as API-fetched, not seed data
        "last_refreshed": datetime.now(),
    }
    
    # Double-check RIGHT BEFORE inserting (handle race conditions)
    # This is critical - check again just before we insert
    existing_check = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
    if existing_check:
        # Book was inserted between our first check and now - update it instead
        logger.debug("book_found_on_double_check", book_id=hardcover_id)
        for key, value in book_dict.items():
            setattr(existing_check, key, value)
        existing_check.last_refreshed = datetime.now()
        try:
            db.commit()
            db.refresh(existing_check)
            return existing_check
        except Exception as e:
            logger.warning("failed_to_update_book_in_db_race", book_id=hardcover_id, error=str(e))
            db.rollback()
            return existing_check
    
    # Final check - one more time before insert
    final_check = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
    if final_check:
        logger.debug("book_found_on_final_check", book_id=hardcover_id)
        for key, value in book_dict.items():
            setattr(final_check, key, value)
        final_check.last_refreshed = datetime.now()
        try:
            db.commit()
            db.refresh(final_check)
            return final_check
        except Exception as e:
            logger.warning("failed_to_update_book_in_db_final", book_id=hardcover_id, error=str(e))
            db.rollback()
            return final_check
    
    # Create new book - only if we're absolutely sure it doesn't exist
    # One final check RIGHT before we try to insert
    last_check = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
    if last_check:
        logger.debug("book_found_on_last_check_before_insert", book_id=hardcover_id)
        for key, value in book_dict.items():
            setattr(last_check, key, value)
        last_check.last_refreshed = datetime.now()
        try:
            db.commit()
            db.refresh(last_check)
            return last_check
        except Exception as e:
            logger.warning("failed_to_update_on_last_check", book_id=hardcover_id, error=str(e))
            db.rollback()
            return last_check
    
    try:
        db_book = Book(**book_dict)
        db.add(db_book)
        try:
            db.flush()  # Flush to trigger any constraint checks before commit
        except IntegrityError as flush_error:
            # Catch IntegrityError at flush stage
            db.rollback()
            existing = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
            if existing:
                for key, value in book_dict.items():
                    setattr(existing, key, value)
                existing.last_refreshed = datetime.now()
                db.commit()
                db.refresh(existing)
                return existing
            # Re-raise if we can't find the book
            raise flush_error
        db.commit()

        if series and series_id:
            db.query(Book).filter(
                Book.series == series,
                or_(Book.series_id.is_(None), Book.series_id == 0)
            ).update(
                {Book.series_id: series_id},
                synchronize_session=False
            )
            db.commit()
        db.refresh(db_book)
        logger.debug("book_created_successfully", book_id=hardcover_id)
        return db_book
    except IntegrityError as e:
        # Handle race condition: if book was inserted between check and insert, retry as update
        # This is expected behavior - handle silently
        db.rollback()
        # Retry as update - query again after rollback
        existing = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
        if existing:
            # Silently update - this is the expected behavior when book already exists
            for key, value in book_dict.items():
                setattr(existing, key, value)
            existing.last_refreshed = datetime.now()
            try:
                db.commit()
                db.refresh(existing)
                return existing
            except Exception as update_error:
                logger.warning("failed_to_update_after_integrity_error", book_id=hardcover_id, error=str(update_error))
                db.rollback()
                return existing
        logger.warning("book_not_found_after_integrity_error", book_id=hardcover_id, error=str(e))
        return None
    except Exception as e:
        # Check if it's actually an IntegrityError wrapped in another exception
        error_str = str(e)
        if "UNIQUE constraint failed" in error_str or "IntegrityError" in str(type(e)):
            logger.info("book_already_exists_wrapped_error", book_id=hardcover_id, error=error_str)
            db.rollback()
            existing = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
            if existing:
                for key, value in book_dict.items():
                    setattr(existing, key, value)
                existing.last_refreshed = datetime.now()
                try:
                    db.commit()
                    db.refresh(existing)
                    return existing
                except Exception as update_error:
                    logger.warning("failed_to_update_after_wrapped_error", book_id=hardcover_id, error=str(update_error))
                    db.rollback()
                    return existing
        logger.warning("failed_to_save_book_to_db", book_id=hardcover_id, error=str(e), error_type=str(type(e)))
        db.rollback()
        return None

def _ensure_series_fields(db_book: Book, series_id: Optional[int], series_name: Optional[str], position: Optional[float], db: Session) -> None:
    """Ensure series fields are populated even when the book payload lacks book_series."""
    if not db_book:
        return
    updated = False
    if series_id and (db_book.series_id is None or db_book.series_id == 0):
        db_book.series_id = series_id
        updated = True
    if series_name and db_book.series != series_name:
        db_book.series = series_name
        updated = True
    if position is not None and db_book.series_position != position:
        db_book.series_position = position
        updated = True
    if updated:
        try:
            db.commit()
            db.refresh(db_book)
        except Exception as e:
            logger.warning("failed_to_update_series_fields", book_id=db_book.hardcover_id, error=str(e))
            db.rollback()

async def execute_graphql(query: str, variables: dict = None, db: Session = None):
    """Execute a GraphQL query against the Hardcover API"""
    # Get token - use db if provided, otherwise create a session
    if db:
        from app.routers.settings import get_hardcover_token as get_token_from_db
        token, _ = get_token_from_db(db)
    else:
        token = get_hardcover_token()
    
    if not token:
        logger.error(
            "hardcover_api_token_missing",
            message="Hardcover API token is not configured. Please set it in Settings or via HARDCOVER_API_TOKEN environment variable."
        )
        raise HTTPException(
            status_code=500,
            detail="Hardcover API token is not configured. Please set it in Settings or via HARDCOVER_API_TOKEN environment variable."
        )
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    # Log the request
    query_name = query.split("query")[1].split("(")[0].strip() if "query" in query else "unknown"
    logger.info(
        "hardcover_api_request",
        query_name=query_name,
        variables=variables or {},
        url=HARDCOVER_API_URL
    )
    
    max_retries = 5
    base_delay = 1.0  # seconds
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    HARDCOVER_API_URL,
                    headers=headers,
                    json={"query": query, "variables": variables or {}},
                    timeout=30.0,
                )
                
                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        # Get retry-after header if available, otherwise use exponential backoff
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = base_delay * (2 ** attempt)
                        else:
                            delay = base_delay * (2 ** attempt)
                        
                        logger.warning(
                            "hardcover_rate_limited",
                            query_name=query_name,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            retry_after=delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "hardcover_rate_limit_exhausted",
                            query_name=query_name,
                            attempts=max_retries
                        )
                        raise HTTPException(
                            status_code=429,
                            detail="Hardcover API rate limit exceeded. Please try again later."
                        )
                
                # Try to parse JSON response
                try:
                    data = response.json()
                except Exception as e:
                    logger.error(
                        "hardcover_api_parse_error",
                        query_name=query_name,
                        error=str(e),
                        response_text=response.text[:200]
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse Hardcover API response: {str(e)}"
                    )
                
                # Check for HTTP errors after parsing JSON
                response.raise_for_status()

                # Check for GraphQL errors
                if data.get("errors"):
                    error_messages = [str(err) for err in data["errors"]]
                    logger.error(
                        "hardcover_api_graphql_errors",
                        query_name=query_name,
                        errors=error_messages
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"GraphQL errors: {'; '.join(error_messages)}"
                    )
                
                return data.get("data", {})
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "hardcover_rate_limited_exception",
                    query_name=query_name,
                    attempt=attempt + 1,
                    retry_after=delay
                )
                await asyncio.sleep(delay)
                continue
            # Log and re-raise non-429 errors
            logger.error(
                "hardcover_api_http_error",
                status_code=e.response.status_code,
                detail=e.response.text,
                query_name=query_name
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Hardcover API HTTP error: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(
                "hardcover_api_request_error",
                detail=str(e),
                query_name=query_name
            )
            raise HTTPException(
                status_code=500,
                detail=f"Hardcover API request error: {str(e)}"
            )
        except Exception as e:
            logger.exception(
                "hardcover_api_unexpected_error",
                detail=str(e),
                query_name=query_name
            )
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred: {str(e)}"
            )
    
    # This should never be reached, but just in case
    raise HTTPException(
        status_code=500,
        detail="Hardcover API request failed after all retries"
    )


async def lookup_book_by_slug(slug: str, db: Session = None) -> Optional[dict]:
    """
    Look up a book on Hardcover by its slug and return full book data.
    Returns None if not found.
    """
    query = """
    query GetBookBySlug($slug: String!) {
      books(where: {slug: {_eq: $slug}}, limit: 1) {
        id
        title
        slug
        release_year
        release_date
        pages
        description
        cached_image
        cached_contributors
        rating
        ratings_count
        users_count
        activities_count
        default_ebook_edition_id
        default_audio_edition_id
        default_physical_edition_id
        book_series {
          position
          series {
            id
            name
          }
        }
        contributions {
          author {
            id
            name
            slug
          }
        }
        taggings(limit: 10) {
          tag {
            tag
          }
        }
      }
    }
    """
    
    try:
        result = await execute_graphql(query, {"slug": slug}, db)
        books = result.get("books", [])
        if books:
            book = books[0]
            logger.info("hardcover_book_found_by_slug", slug=slug, hardcover_id=book.get("id"))
            return book
        else:
            logger.warning("hardcover_book_not_found_by_slug", slug=slug)
            return None
    except Exception as e:
        logger.error("hardcover_lookup_by_slug_error", slug=slug, error=str(e))
        return None


async def lookup_book_by_title_author(title: str, author: str = None, db: Session = None) -> Optional[dict]:
    """
    Search for a book on Hardcover by title and optionally author.
    Returns the best match or None if not found.
    """
    search_query = title
    if author:
        search_query = f"{title} {author}"
    
    query = """
    query SearchBooks($query: String!) {
      search(query: $query, query_type: "Book", per_page: 5, page: 1) {
        results {
          ... on Book {
            document
          }
        }
      }
    }
    """
    
    try:
        result = await execute_graphql(query, {"query": search_query}, db)
        results = result.get("search", {}).get("results", [])
        
        for res in results:
            doc = res.get("document", {})
            if doc and doc.get("id"):
                # Found a match - now fetch full details
                book_id = doc.get("id")
                logger.info("hardcover_search_match_found", 
                          search=search_query, 
                          matched_id=book_id, 
                          matched_title=doc.get("title"))
                
                # Fetch full book details using the ID
                full_query = """
                query GetBook($id: Int!) {
                  books_by_pk(id: $id) {
                    id
                    title
                    slug
                    release_year
                    release_date
                    pages
                    description
                    cached_image
                    cached_contributors
                    rating
                    ratings_count
                    users_count
                    activities_count
                    default_ebook_edition_id
                    default_audio_edition_id
                    default_physical_edition_id
                    book_series {
                      position
                      series {
                        id
                        name
                      }
                    }
                    contributions {
                      author {
                        id
                        name
                        slug
                      }
                    }
                    taggings(limit: 10) {
                      tag {
                        tag
                      }
                    }
                  }
                }
                """
                full_result = await execute_graphql(full_query, {"id": int(book_id)}, db)
                return full_result.get("books_by_pk")
        
        logger.warning("hardcover_search_no_match", search=search_query)
        return None
    except Exception as e:
        logger.error("hardcover_search_error", search=search_query, error=str(e))
        return None


@router.get("/search", response_model=schemas.HardcoverBooksResponse)
async def search_books(
    query: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    db: Session = Depends(database.get_db)
):
    """Search books using Hardcover search API - Database → Cache → API"""
    # 1. Check database first (persistent, fastest)
    db_books = db.query(Book).filter(
        Book.title.ilike(f"%{query}%") | Book.author.ilike(f"%{query}%")
    ).order_by(
        Book.ratings_count.desc().nulls_last()
    ).limit(limit).all()
    
    if db_books:
        logger.info("search_database_hit", query=query, count=len(db_books))
        hc_books = [_db_book_to_hardcover_book(book) for book in db_books]
        return schemas.HardcoverBooksResponse(books=hc_books)
    
    # 2. Check cache second
    cache_key = cache.make_cache_key("search", query=query, limit=limit)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("search_cache_hit", query=query, limit=limit)
        return schemas.HardcoverBooksResponse(**cached_result)
    
    # 3. Call API last - use Hardcover search query
    try:
        # First, get search results (which returns book IDs)
        search_query = """
        query SearchBooks($query: String!) {
          search(query: $query) {
            error
            page
            per_page
            query
            query_type
            results
          }
        }
        """
        
        search_result = await execute_graphql(search_query, {
            "query": query
        }, db=db)
        
        search_response = search_result.get("search", {})
        if search_response.get("error"):
            logger.warning("search_api_error", query=query, error=search_response.get("error"))
            return schemas.HardcoverBooksResponse(books=[])
        
        # results is an object with hits array
        results_obj = search_response.get("results", {})
        if not isinstance(results_obj, dict):
            logger.warning("search_results_not_object", query=query, results_type=type(results_obj).__name__)
            return schemas.HardcoverBooksResponse(books=[])
        
        hits = results_obj.get("hits", [])
        if not hits:
            logger.info("search_no_results", query=query, found=results_obj.get("found", 0))
            return schemas.HardcoverBooksResponse(books=[])
        
        # Extract documents from hits and limit to requested number
        hits = hits[:limit]
        
        # Transform search document structure to match regular book structure
        books_data = []
        for hit in hits:
            doc = hit.get("document", {})
            if not doc:
                continue
            
            # Transform the document to match the structure expected by _parse_hardcover_book
            # Handle image mapping
            image_data = doc.get("image", {})
            cached_image = None
            if image_data and isinstance(image_data, dict) and image_data.get("url"):
                cached_image = {
                    "id": image_data.get("id"),
                    "url": image_data.get("url"),
                    "color_name": image_data.get("color_name")
                }
            
            book_data = {
                "id": int(doc.get("id", 0)) if doc.get("id") else None,
                "title": doc.get("title", ""),
                "slug": doc.get("slug"),
                "release_year": None,  # Not in search results
                "release_date": None,  # Not in search results
                "pages": None,  # Not in search results
                "description": doc.get("description"),
                "cached_image": cached_image,
                "cached_contributors": [
                    {
                        "author": {
                            "id": contrib.get("author", {}).get("id"),
                            "name": contrib.get("author", {}).get("name"),
                            "slug": contrib.get("author", {}).get("slug")
                        },
                        "contribution": contrib.get("author", {}).get("name")  # Use name as contribution
                    }
                    for contrib in doc.get("contributions", [])
                ] if doc.get("contributions") else None,
                "rating": doc.get("rating"),
                "ratings_count": doc.get("ratings_count", 0),
                "users_count": doc.get("users_count", 0),
                "activities_count": doc.get("activities_count", 0),
                "book_series": [],  # Not in search results
                "contributions": [
                    {
                        "author": {
                            "id": contrib.get("author", {}).get("id"),
                            "name": contrib.get("author", {}).get("name"),
                            "slug": contrib.get("author", {}).get("slug")
                        }
                    }
                    for contrib in doc.get("contributions", [])
                ] if doc.get("contributions") else [],
                "taggings": [
                    {"tag": {"tag": tag}}
                    for tag in doc.get("tags", [])
                ] if doc.get("tags") else []
            }
            
            # Skip if no valid ID
            if not book_data["id"]:
                continue
            
            books_data.append(book_data)
        
        if not books_data:
            logger.info("search_no_valid_books", query=query)
            return schemas.HardcoverBooksResponse(books=[])
        
        # Parse books
        books = [_parse_hardcover_book(book) for book in books_data]
        
        # Save ALL results to database first
        for book_data in books_data:
            _save_book_to_db(book_data, db)
        
        # Enrich with local availability data
        books = _enrich_books_with_availability(books, db)
        
        response = schemas.HardcoverBooksResponse(books=books)
        
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["search"]
        )
        
        logger.info("search_api_fetched", query=query, count=len(books))
        return response
    except Exception as e:
        logger.warning("search_api_failed", query=query, error=str(e))
        return schemas.HardcoverBooksResponse(books=[])

@router.get("/search-grouped", response_model=schemas.SearchGroupedResponse)
async def search_grouped(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results per group"),
    cache_only: bool = Query(False, description="Only return cached/local results"),
    db: Session = Depends(database.get_db)
):
    """Search series/authors/books with local DB + Hardcover (English-only)."""
    if not query.strip():
        return schemas.SearchGroupedResponse(series=[], authors=[], books=[])

    like_query = f"%{query}%"
    cache_key = cache.make_cache_key("search_grouped", query=query, limit=limit)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        return schemas.SearchGroupedResponse(**cached_result)

    # Series (local)
    series_rows = db.query(Series).filter(
        Series.name.ilike(like_query)
    ).order_by(
        Series.books_count.desc().nulls_last(),
        Series.name.asc()
    ).limit(limit).all()
    series_results = [
        schemas.SearchSeriesResult(
            id=row.hardcover_id,
            name=row.name,
            books_count=row.books_count
        )
        for row in series_rows
    ]

    # Authors (local)
    author_rows = db.query(
        Book.author,
        func.count(Book.id).label("count")
    ).filter(
        Book.author.ilike(like_query)
    ).group_by(
        Book.author
    ).order_by(
        func.count(Book.id).desc()
    ).limit(limit).all()
    authors_results = [
        schemas.SearchAuthorResult(name=name, books_count=count)
        for name, count in author_rows
        if name
    ]

    # Books (local)
    local_books_rows = db.query(Book).filter(
        or_(Book.title.ilike(like_query), Book.author.ilike(like_query))
    ).order_by(
        Book.ratings_count.desc().nulls_last()
    ).limit(limit).all()
    local_books = [
        _db_book_to_hardcover_book(row)
        for row in local_books_rows
        if row.hardcover_id
    ]

    hardcover_books: list[schemas.HardcoverBook] = []
    ordered_ids: list[int] = []
    if cache_only:
        return schemas.SearchGroupedResponse(
            series=series_results,
            authors=authors_results,
            books=local_books[:limit]
        )
    try:
        search_query = """
        query SearchBooks($query: String!) {
          search(query: $query) {
            error
            results
          }
        }
        """
        search_result = await execute_graphql(search_query, {"query": query}, db=db)
        search_response = search_result.get("search", {})
        results_obj = search_response.get("results", {}) if isinstance(search_response, dict) else {}
        hits = results_obj.get("hits", []) if isinstance(results_obj, dict) else []
        for hit in hits[: max(limit * 3, limit)]:
            doc = hit.get("document", {})
            if doc and doc.get("id"):
                ordered_ids.append(int(doc["id"]))
        if ordered_ids:
            books_query = """
            query SearchBooksByIds($ids: [Int!]!) {
              books(where: {id: {_in: $ids}}) {
                id
                title
                slug
                release_year
                release_date
                pages
                description
                cached_image
                cached_contributors
                rating
                ratings_count
                users_count
                activities_count
                compilation
                book_series {
                  series {
                    id
                    name
                  }
                  position
                }
                contributions {
                  author {
                    id
                    name
                    slug
                  }
                }
                taggings(limit: 5) {
                  tag {
                    tag
                  }
                }
              }
            }
            """
            books_result = await execute_graphql(books_query, {"ids": ordered_ids}, db=db)
            books_data = books_result.get("books", [])
            hardcover_books = [_parse_hardcover_book(book) for book in books_data]
            hardcover_books = _enrich_books_with_availability(hardcover_books, db)
    except Exception as e:
        logger.warning("search_grouped_hardcover_failed", query=query, error=str(e))

    # Merge books (prefer Hardcover data when available)
    books_by_id = {book.id: book for book in hardcover_books}
    for book in local_books:
        books_by_id.setdefault(book.id, book)

    merged_books: list[schemas.HardcoverBook] = []
    for book_id in ordered_ids:
        book = books_by_id.get(book_id)
        if book:
            merged_books.append(book)
        if len(merged_books) >= limit:
            break
    if len(merged_books) < limit:
        for book in books_by_id.values():
            if book in merged_books:
                continue
            merged_books.append(book)
            if len(merged_books) >= limit:
                break

    response = schemas.SearchGroupedResponse(
        series=series_results,
        authors=authors_results,
        books=merged_books
    )
    await cache.set_cached(
        cache_key,
        response.model_dump(),
        ttl=cache.CACHE_TTL["search_grouped"]
    )
    return response

@router.get("/author", response_model=schemas.HardcoverAuthorResponse)
async def get_author_details(
    name: str = Query(..., min_length=1),
    books_limit: int = Query(12, ge=1, le=50),
    books_offset: int = Query(0, ge=0),
    series_limit: int = Query(12, ge=1, le=50),
    series_offset: int = Query(0, ge=0),
    db: Session = Depends(database.get_db)
):
    """Get author details, books, and series."""
    query_name = name.strip()
    if not query_name:
        raise HTTPException(status_code=400, detail="Author name is required")
    cache_key = cache.make_cache_key(
        "author",
        name=name,
        books_limit=books_limit,
        books_offset=books_offset,
        series_limit=series_limit,
        series_offset=series_offset,
    )
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        return schemas.HardcoverAuthorResponse(**cached_result)

    search_query = """
    query SearchBooks($query: String!) {
      search(query: $query) {
        error
        results
      }
    }
    """

    search_result = await execute_graphql(search_query, {"query": query_name}, db=db)
    search_response = search_result.get("search", {})
    results_obj = search_response.get("results", {}) if isinstance(search_response, dict) else {}
    hits = results_obj.get("hits", []) if isinstance(results_obj, dict) else []
    ordered_ids: list[int] = []
    for hit in hits:
        doc = hit.get("document", {})
        if doc and doc.get("id"):
            ordered_ids.append(int(doc["id"]))

    if not ordered_ids:
        raise HTTPException(status_code=404, detail="Author not found")

    candidate_limit = min(len(ordered_ids), max(books_offset + books_limit, 30) * 3)
    candidate_ids = ordered_ids[:candidate_limit]

    books_query = """
    query BooksByIds($ids: [Int!]!) {
      books(where: {id: {_in: $ids}}) {
        id
        title
        slug
        release_year
        release_date
        pages
        description
        cached_image
        cached_contributors
        rating
        ratings_count
        users_count
        activities_count
        default_ebook_edition_id
        default_audio_edition_id
        default_physical_edition_id
        book_series {
          series_id
          position
          series {
            id
            name
            primary_books_count
          }
        }
        contributions {
          author {
            id
            name
            slug
          }
        }
        taggings(limit: 5) {
          tag {
            tag
          }
        }
      }
    }
    """

    books_result = await execute_graphql(books_query, {"ids": candidate_ids}, db=db)
    books_data = books_result.get("books", []) or []

    def _author_matches(book: dict, author_name: str) -> bool:
        target = author_name.lower()
        contributions = book.get("contributions") or []
        for contrib in contributions:
            author = contrib.get("author") or {}
            name_value = author.get("name") or ""
            if target in name_value.lower():
                return True
        cached_contributors = book.get("cached_contributors") or []
        for contrib in cached_contributors:
            author = contrib.get("author") or {}
            name_value = author.get("name") or contrib.get("name") or ""
            if target in str(name_value).lower():
                return True
        return False

    matching_books_raw = [book for book in books_data if _author_matches(book, query_name)]
    if not matching_books_raw:
        raise HTTPException(status_code=404, detail="Author not found")

    author_id = None
    for book in matching_books_raw:
        for contrib in book.get("contributions") or []:
            author = contrib.get("author") or {}
            if query_name.lower() in (author.get("name") or "").lower():
                author_id = author.get("id")
                break
        if author_id:
            break

    author = {"id": author_id or 0, "name": query_name, "slug": None, "bio": None, "image_url": None}
    if author_id:
        author_query = """
        query AuthorByPk($id: Int!) {
          authors_by_pk(id: $id) {
            id
            name
            slug
            bio
            image {
              url
            }
          }
        }
        """
        author_result = await execute_graphql(author_query, {"id": author_id}, db=db)
        author_payload = author_result.get("authors_by_pk")
        if author_payload:
            author = {
                "id": author_payload.get("id"),
                "name": author_payload.get("name"),
                "slug": author_payload.get("slug"),
                "bio": author_payload.get("bio"),
                "image_url": (author_payload.get("image") or {}).get("url"),
            }

    for book_data in matching_books_raw:
        _save_book_to_db(book_data, db)

    books_total = len(matching_books_raw)
    paged_books_raw = matching_books_raw[books_offset:books_offset + books_limit]
    books = [_parse_hardcover_book(book) for book in paged_books_raw]
    books = _enrich_books_with_availability(books, db)

    series_map: dict[int, dict] = {}
    for book in matching_books_raw:
        for entry in book.get("book_series") or []:
            series_info = entry.get("series") or {}
            series_id = entry.get("series_id") or series_info.get("id")
            if not series_id:
                continue
            if series_id not in series_map:
                series_map[series_id] = {
                    "id": series_id,
                    "name": series_info.get("name") or "Untitled Series",
                    "books_count": 0,
                }
            series_map[series_id]["books_count"] += 1

    series_list = list(series_map.values())
    series_total = len(series_list)
    series = series_list[series_offset:series_offset + series_limit]

    response = schemas.HardcoverAuthorResponse(
        author=author,
        books=books,
        books_total=books_total,
        series=series,
        series_total=series_total,
    )

    await cache.set_cached(
        cache_key,
        response.model_dump(),
        ttl=cache.CACHE_TTL["author"]
    )

    return response

@router.get("/details/{book_id}", response_model=schemas.HardcoverBookDetailResponse)
async def get_book_details(
    book_id: int,
    bypass_cache: bool = Query(False),
    db: Session = Depends(database.get_db)
):
    """Get detailed information about a book - Cache → API"""
    from app.models import Series

    # Check cache first
    cache_key = cache.make_cache_key("book_details", book_id=book_id)
    cached_result = None if bypass_cache else await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("book_details_cache_hit", book_id=book_id)
        cached_book = cached_result.get("books_by_pk") if isinstance(cached_result, dict) else None
        if cached_book:
            db_book = db.query(Book).filter(Book.hardcover_id == book_id).first()
            if db_book and not cached_book.get("book_series") and db_book.series_id:
                cached_book["book_series"] = [
                    {
                        "series_id": db_book.series_id,
                        "position": db_book.series_position,
                        "series": {
                            "id": db_book.series_id,
                            "name": db_book.series or "",
                            "primary_books_count": None,
                        },
                    }
                ]
        return schemas.HardcoverBookDetailResponse(**cached_result)
    
    # Call API last
    try:
        graphql_query = """
        query GetBook($id: Int!) {
          books_by_pk(id: $id) {
            id
            title
            slug
            release_year
            release_date
            pages
            description
            cached_image
            cached_contributors
            rating
            ratings_count
            users_count
            activities_count
            default_ebook_edition_id
            default_audio_edition_id
            default_physical_edition_id
            book_series {
              series_id
              position
              series {
                primary_books_count
                name
                id
              }
            }
            contributions {
              author {
                id
                name
                slug
              }
            }
            taggings(limit: 10) {
              tag {
                tag
              }
            }
            editions(limit: 5) {
              id
              title
              edition_format
              physical_format
              reading_format_id
              pages
              isbn_10
              isbn_13
              asin
            }
          }
        }
        """
        
        result = await execute_graphql(graphql_query, {"id": book_id}, db=db)
        book_data = result.get("books_by_pk")
        
        if not book_data:
            raise HTTPException(status_code=404, detail="Book not found")
        
        # Parse the book detail with proper handling of complex fields
        try:
            book = schemas.HardcoverBookDetail.model_validate(book_data)
        except Exception as e:
            logger.warning(
                "hardcover_book_detail_validation_error",
                book_id=book_id,
                error=str(e),
                book_data_sample=_sample_response(book_data, max_items=1)
            )
            # Fallback handling
            book_dict = book_data.copy()
            if isinstance(book_dict.get("cached_image"), dict):
                try:
                    book_dict["cached_image"] = schemas.HardcoverCachedImage(**book_dict["cached_image"])
                except:
                    book_dict["cached_image"] = None
            if isinstance(book_dict.get("cached_contributors"), list):
                try:
                    book_dict["cached_contributors"] = [
                        schemas.HardcoverCachedContributor(**item) if isinstance(item, dict) else item
                        for item in book_dict["cached_contributors"]
                    ]
                except:
                    book_dict["cached_contributors"] = None
            book = schemas.HardcoverBookDetail.model_validate(book_dict)
        
        # Enrich with local availability (if present)
        db_book = db.query(Book).filter(Book.hardcover_id == book_id).first()
        if db_book:
            book.ebook_available = db_book.ebook_available or False
            book.audiobook_available = db_book.audiobook_available or False
            if not book.book_series and db_book.series_id:
                book.book_series = [
                    schemas.HardcoverBookSeries(
                        series_id=db_book.series_id,
                        position=db_book.series_position,
                        series=schemas.HardcoverSeries(
                            id=db_book.series_id,
                            name=db_book.series or "",
                            primary_books_count=None,
                        ),
                    )
                ]

        response = schemas.HardcoverBookDetailResponse(books_by_pk=book)
        
        # Save to database and cache
        _save_book_to_db(book_data, db)
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["book_details"]
        )
        
        logger.info("book_details_api_fetched", book_id=book_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("book_details_api_failed", book_id=book_id, error=str(e))
        raise HTTPException(status_code=404, detail="Book not found")


@router.get("/editions/{book_id}", response_model=schemas.HardcoverEditionPickerResponse)
async def get_book_editions(
    book_id: int,
    format: Optional[str] = Query(None, description="Filter by format: 'ebook' or 'audiobook'"),
    db: Session = Depends(database.get_db),
):
    """Fetch editions for a book and return them sorted by score."""
    graphql_query = """
    query GetBookEditions($id: Int!) {
      books_by_pk(id: $id) {
        id
        title
        default_cover_edition_id
        default_ebook_edition_id
        default_audio_edition_id
        editions {
          id
          audio_seconds
          edition_format
          reading_format {
            format
            id
          }
          language {
            code2
            id
            language
          }
          pages
          publisher {
            name
            id
          }
          release_year
          release_date
          score
          title
        }
      }
    }
    """

    result = await execute_graphql(graphql_query, {"id": book_id}, db=db)
    book_data = result.get("books_by_pk")
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found")

    editions = book_data.get("editions", []) or []
    format_filter = None
    if format == "ebook":
        format_filter = 1
    elif format == "audiobook":
        format_filter = 2

    filtered = []
    for edition in editions:
        reading_format = edition.get("reading_format") or {}
        reading_format_id = reading_format.get("id")
        if format_filter and reading_format_id != format_filter:
            continue
        language = edition.get("language") or {}
        publisher = edition.get("publisher") or {}
        filtered.append({
            "id": edition.get("id"),
            "title": edition.get("title"),
            "score": edition.get("score"),
            "reading_format_id": reading_format_id,
            "reading_format": reading_format.get("format"),
            "language": language.get("language"),
            "language_code2": language.get("code2"),
            "publisher": publisher.get("name"),
            "pages": edition.get("pages"),
            "audio_seconds": edition.get("audio_seconds"),
            "edition_format": edition.get("edition_format"),
            "release_date": edition.get("release_date"),
            "release_year": edition.get("release_year"),
        })

    filtered.sort(key=lambda e: (e.get("score") or 0), reverse=True)

    return {
        "default_cover_edition_id": book_data.get("default_cover_edition_id"),
        "default_ebook_edition_id": book_data.get("default_ebook_edition_id"),
        "default_audio_edition_id": book_data.get("default_audio_edition_id"),
        "editions": filtered,
    }

@router.get("/trending", response_model=schemas.HardcoverBooksResponse)
async def get_trending_books(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(database.get_db)
):
    """Get trending books - Cache → API (trending changes frequently, so DB check less useful)"""
    from datetime import datetime, timedelta
    
    today = datetime.now()
    # Use yesterday to today (last 24 hours) - API needs a date range
    yesterday = today - timedelta(days=1)
    to_date = today.strftime("%Y-%m-%d")
    from_date = yesterday.strftime("%Y-%m-%d")  # Yesterday to today - last 24 hours
    current_date = today.strftime("%Y-%m-%d")
    
    # Check cache first (include date in key so it refreshes daily)
    cache_key = cache.make_cache_key("trending", limit=limit, date=current_date)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("trending_cache_hit", limit=limit, date=current_date)
        return schemas.HardcoverBooksResponse(**cached_result)
    
    try:
        
        trending_query = """
        query TrendingBooks($from: date!, $to: date!, $limit: Int!) {
          books_trending(from: $from, to: $to, limit: $limit, offset: 0) {
            ids
            error
          }
        }
        """
        
        trending_result = await execute_graphql(trending_query, {
            "from": from_date,
            "to": to_date,
            "limit": limit
        }, db=db)
        
        trending_data = trending_result.get("books_trending", {})
        trending_response = schemas.HardcoverTrendingResponse(**trending_data)
        
        if trending_response.error:
            raise HTTPException(
                status_code=400,
                detail=f"Trending API error: {trending_response.error}"
            )
        
        book_ids = trending_response.ids
        
        if not book_ids:
            return schemas.HardcoverBooksResponse(books=[])
        
        # Check database for these IDs first
        db_books = db.query(Book).filter(Book.hardcover_id.in_(book_ids)).all()
        db_book_map = {book.hardcover_id: book for book in db_books}
        
        # Fetch missing books from API
        missing_ids = [bid for bid in book_ids if bid not in db_book_map]
        books_data = []
        
        if missing_ids:
            books_query = """
            query GetBooksByIds($ids: [Int!]!) {
              books(where: {
                _and: [
                  {id: {_in: $ids}},
                  {ratings_count: {_gte: 50}}
                ]
              }) {
                id
                title
                slug
                release_year
                release_date
                pages
                description
                cached_image
                cached_contributors
                rating
                ratings_count
                users_count
                activities_count
                default_ebook_edition_id
                default_audio_edition_id
                default_physical_edition_id
                compilation
                book_series {
                  series {
                    id
                    name
                  }
                  position
                }
                contributions {
                  author {
                    id
                    name
                    slug
                  }
                }
                taggings(limit: 5) {
                  tag {
                    tag
                  }
                }
              }
            }
            """
            
            books_result = await execute_graphql(books_query, {"ids": missing_ids}, db=db)
            books_data = books_result.get("books", [])
            
            # Save new books to database
            for book_data in books_data:
                _save_book_to_db(book_data, db)
        
        # Combine database and API books, maintaining trending order
        books = []
        for book_id in book_ids:
            if book_id in db_book_map:
                books.append(_db_book_to_hardcover_book(db_book_map[book_id]))
            else:
                # Find in API results
                api_book = next((b for b in books_data if b.get("id") == book_id), None)
                if api_book:
                    books.append(_parse_hardcover_book(api_book))
        
        # Enrich with local availability data
        books = _enrich_books_with_availability(books, db)
        
        response = schemas.HardcoverBooksResponse(books=books)
        
        # Cache the result
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["trending"]
        )
        
        logger.info("trending_api_fetched", limit=limit, count=len(books), date=current_date)
        return response
    except Exception as e:
        logger.warning("trending_api_failed", error=str(e))
        return schemas.HardcoverBooksResponse(books=[])

@router.get("/popular", response_model=schemas.HardcoverBooksResponse)
async def get_popular_books(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(database.get_db)
):
    """Get popular books this month - Cache → API (uses books_trending for current month)"""
    # Include current month in cache key so it refreshes monthly
    from datetime import datetime, timedelta
    from calendar import monthrange
    
    today = datetime.now()
    # First day of current month
    first_day = today.replace(day=1)
    # Last day of current month
    last_day = today.replace(day=monthrange(today.year, today.month)[1])
    
    from_date = first_day.strftime("%Y-%m-%d")
    to_date = last_day.strftime("%Y-%m-%d")
    current_month = today.strftime("%Y-%m")
    
    # Check cache first (with month in key for monthly refresh)
    cache_key = cache.make_cache_key("popular", limit=limit, month=current_month)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("popular_cache_hit", limit=limit, month=current_month)
        return schemas.HardcoverBooksResponse(**cached_result)
    
    # Use books_trending API for current month
    try:
        trending_query = """
        query PopularBooksThisMonth($from: date!, $to: date!, $limit: Int!) {
          books_trending(from: $from, to: $to, limit: $limit, offset: 0) {
            ids
            error
          }
        }
        """
        
        trending_result = await execute_graphql(trending_query, {
            "from": from_date,
            "to": to_date,
            "limit": limit
        }, db=db)
        
        trending_data = trending_result.get("books_trending", {})
        trending_response = schemas.HardcoverTrendingResponse(**trending_data)
        
        if trending_response.error:
            raise HTTPException(
                status_code=400,
                detail=f"Trending API error: {trending_response.error}"
            )
        
        book_ids = trending_response.ids
        
        if not book_ids:
            return schemas.HardcoverBooksResponse(books=[])
        
        # Fetch full book details for trending IDs
        books_query = """
        query GetBooksByIds($ids: [Int!]!) {
          books(where: {
            _and: [
              {id: {_in: $ids}},
              {ratings_count: {_gte: 50}}
            ]
          }) {
            id
            title
            slug
            release_year
            release_date
            pages
            description
            cached_image
            cached_contributors
            rating
            ratings_count
            users_count
            activities_count
            default_ebook_edition_id
            default_audio_edition_id
            default_physical_edition_id
            book_series {
              series {
                id
                name
              }
              position
            }
            contributions {
              author {
                id
                name
                slug
              }
            }
            taggings(limit: 5) {
              tag {
                tag
              }
            }
          }
        }
        """
        
        books_result = await execute_graphql(books_query, {"ids": book_ids}, db=db)
        books_data = books_result.get("books", [])
        
        # Save to database
        for book_data in books_data:
            _save_book_to_db(book_data, db)
        
        # Sort books to match trending order
        books_map = {book.get("id"): book for book in books_data}
        ordered_books = []
        for book_id in book_ids:
            if book_id in books_map:
                ordered_books.append(_parse_hardcover_book(books_map[book_id]))
        
        # Enrich with local availability data
        ordered_books = _enrich_books_with_availability(ordered_books, db)
        
        response = schemas.HardcoverBooksResponse(books=ordered_books)
        
        # Cache the result
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["popular"]
        )
        
        logger.info("popular_api_fetched", limit=limit, count=len(ordered_books), month=current_month, from_date=from_date, to_date=to_date)
        return response
    except Exception as e:
        logger.warning("popular_api_failed", error=str(e))
        # Return empty on failure - don't fallback to stale database data for time-sensitive queries
        return schemas.HardcoverBooksResponse(books=[])

@router.get("/new-releases", response_model=schemas.HardcoverBooksResponse)
async def get_new_releases(
    limit: int = Query(20, ge=1, le=100),
    min_ratings: int = Query(5, ge=0, description="Minimum number of ratings required"),
    db: Session = Depends(database.get_db)
):
    """Get new releases - Database → Cache → API"""
    from datetime import datetime
    current_year = datetime.now().year
    
    # 1. Check database first
    db_books = db.query(Book).filter(
        Book.release_year >= (current_year - 1),
        Book.ratings_count >= min_ratings
    ).order_by(
        Book.published_date.desc().nulls_last()
    ).limit(limit).all()
    
    if len(db_books) >= limit:
        logger.info("new_releases_database_hit", limit=limit, count=len(db_books))
        hc_books = [_db_book_to_hardcover_book(book) for book in db_books]
        return schemas.HardcoverBooksResponse(books=hc_books)
    
    # 2. Check cache
    cache_key = cache.make_cache_key("new_releases", limit=limit, min_ratings=min_ratings)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("new_releases_cache_hit", limit=limit, min_ratings=min_ratings)
        return schemas.HardcoverBooksResponse(**cached_result)
    
    # 3. Call API
    try:
        graphql_query = """
        query NewReleases($limit: Int!, $year: Int!, $minRatings: Int!) {
          books(
            order_by: {release_date: desc_nulls_last},
            limit: $limit,
            where: {
              release_year: {_gte: $year},
              ratings_count: {_gte: $minRatings}
            }
          ) {
            id
            title
            slug
            release_year
            release_date
            pages
            description
            cached_image
            cached_contributors
            rating
            ratings_count
            users_count
            activities_count
            default_ebook_edition_id
            default_audio_edition_id
            default_physical_edition_id
            book_series {
              series {
                id
                name
              }
              position
            }
            contributions {
              author {
                id
                name
                slug
              }
            }
            taggings(limit: 5) {
              tag {
                tag
              }
            }
          }
        }
        """
        
        result = await execute_graphql(graphql_query, {
            "limit": limit,
            "year": current_year - 1,
            "minRatings": min_ratings
        }, db=db)
        books_data = result.get("books", [])
        books = [_parse_hardcover_book(book) for book in books_data]
        
        # Save to database first
        for book_data in books_data:
            _save_book_to_db(book_data, db)
        
        # Enrich with local availability data
        books = _enrich_books_with_availability(books, db)
        
        response = schemas.HardcoverBooksResponse(books=books)
        
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["new_releases"]
        )
        
        logger.info("new_releases_api_fetched", limit=limit, count=len(books))
        return response
    except Exception as e:
        logger.warning("new_releases_api_failed", error=str(e))
        # Fallback to database
        if db_books:
            hc_books = [_db_book_to_hardcover_book(book) for book in db_books]
            return schemas.HardcoverBooksResponse(books=hc_books)
        return schemas.HardcoverBooksResponse(books=[])

@router.get("/series/{series_id}", response_model=schemas.HardcoverSeriesResponse)
async def get_series_books(
    series_id: int,
    db: Session = Depends(database.get_db),
    bypass_cache: bool = False
):
    """Get books in a series - Database → Cache → API"""
    from app.models import Series
    
    # 1. Skip database shortcut: compilation filtering requires fresh API data
    
    # 2. Check cache
    cache_key = cache.make_cache_key("series", series_id=series_id)
    if bypass_cache:
        logger.info("series_cache_bypass", series_id=series_id)
        await cache.delete_cached(cache_key)
    if not bypass_cache:
        cached_result = await cache.get_cached(cache_key)
        if cached_result is not None:
            logger.info("series_cache_hit", series_id=series_id)
            return schemas.HardcoverSeriesResponse(**cached_result)
    
    # 3. Call API
    try:
        graphql_query = """
        query SeriesBooks($seriesId: Int!) {
          series(where: {id: {_eq: $seriesId}}) {
            id
            name
            books_count
            author {
              name
            }
            book_series(
              order_by: {book: {activities_count: desc_nulls_last}, position: asc}
              where: {
                book: {
                  editions: {language_id: {_eq: 1}, language: {id: {_eq: 1}}}
                }
              }
            ) {
              position
              book {
                id
                title
                subtitle
                slug
                release_year
                release_date
                pages
                description
                cached_image
                cached_contributors
                rating
                ratings_count
                users_count
                activities_count
                default_ebook_edition_id
                default_audio_edition_id
                default_physical_edition_id
                compilation
                book_series {
                  series {
                    id
                    name
                  }
                  position
                }
                contributions {
                  author {
                    id
                    name
                    slug
                  }
                }
                taggings(limit: 5) {
                  tag {
                    tag
                  }
                }
              }
            }
          }
        }
        """
        
        result = await execute_graphql(graphql_query, {"seriesId": series_id}, db=db)
        series_list = result.get("series", [])
        logger.debug("series_list", series_list=series_list[:10])
        if not series_list:
            logger.warning("series_not_found", series_id=series_id)
            raise HTTPException(status_code=404, detail=f"Series {series_id} not found")
        series_info = series_list[0]
        book_series_data = series_info.get("book_series", []) or []
        if not book_series_data:
            logger.info("book_series_data_not_found", series_id=series_id)
            fallback_query = """
            query SeriesBooksFallback($seriesId: Int!) {
              series(where: {id: {_eq: $seriesId}}) {
                id
                name
                books_count
                author {
                  name
                }
                book_series(
                  order_by: {book: {activities_count: desc_nulls_last}, position: asc}
                  where: {
                    book: {
                      editions: {language_id: {_eq: 1}, language: {id: {_eq: 1}}}
                    }
                  }
                ) {
                  position
                  book {
                    id
                    title
                    subtitle
                    slug
                    release_year
                    release_date
                    pages
                    description
                    cached_image
                    cached_contributors
                    rating
                    ratings_count
                    users_count
                    activities_count
                    default_ebook_edition_id
                    default_audio_edition_id
                    default_physical_edition_id
                    compilation
                    book_series {
                      series {
                        id
                        name
                      }
                      position
                    }
                    contributions {
                      author {
                        id
                        name
                        slug
                      }
                    }
                    taggings(limit: 5) {
                      tag {
                        tag
                      }
                    }
                  }
                }
              }
            }
            """
            fallback_result = await execute_graphql(fallback_query, {"seriesId": series_id}, db=db)
            fallback_series_list = fallback_result.get("series", [])
            if fallback_series_list:
                fallback_info = fallback_series_list[0]
                fallback_books = fallback_info.get("book_series", []) or []
                if fallback_books:
                    series_info = fallback_info
                    book_series_data = fallback_books
                    logger.info("series_api_fallback_books", series_id=series_id, count=len(book_series_data))

        compilation_count = sum(
            1 for entry in book_series_data
            if entry.get("book", {}).get("compilation") is True
        )
        if compilation_count:
            logger.warning(
                "series_api_contains_compilations",
                series_id=series_id,
                compilation_count=compilation_count
            )
        else:
            logger.info(
                "series_api_no_compilations",
                series_id=series_id,
                books_count=len(book_series_data)
            )

        logger.debug(
            "series_api_books_snapshot",
            series_id=series_id,
            books=[
                {
                    "id": entry.get("book", {}).get("id"),
                    "title": entry.get("book", {}).get("title"),
                    "compilation": entry.get("book", {}).get("compilation"),
                    "position": entry.get("position"),
                }
                for entry in book_series_data[:25]
            ],
            truncated=len(book_series_data) > 25
        )
        
        if not book_series_data:
            logger.warning("series_no_books", series_id=series_id, series_name=series_info.get("name"))
            # Series exists but has no books - return series info with empty books list
            return schemas.HardcoverSeriesResponse(
                series_by_pk=schemas.HardcoverSeriesDetail(
                    id=series_info["id"],
                    name=series_info["name"],
                    author=series_info.get("author"),
                    books_count=series_info.get("books_count") or 0,
                    book_series=[]
                )
            )
        
        seen_positions = set()
        deduped_series_books = []
        for entry in book_series_data:
            position = entry.get("position")
            if position is None or isinstance(position, bool):
                continue
            try:
                normalized_position = float(position)
            except (TypeError, ValueError):
                continue
            if normalized_position < 0:
                continue
            if normalized_position in seen_positions:
                continue
            seen_positions.add(normalized_position)
            deduped_series_books.append(entry)

        if not deduped_series_books:
            def _fallback_sort_key(entry: dict) -> tuple:
                position = entry.get("position")
                activities_count = entry.get("book", {}).get("activities_count") or 0
                position_sort = position if position is not None else float("inf")
                return (position_sort, -activities_count)

            sorted_series_books = sorted(book_series_data, key=_fallback_sort_key)
            seen_positions = set()
            deduped_series_books = []
            for entry in sorted_series_books:
                position = entry.get("position")
                if position is not None:
                    if position in seen_positions:
                        continue
                    seen_positions.add(position)
                deduped_series_books.append(entry)

        
        series_entries = []
        for entry in deduped_series_books:
            book_data = entry.get("book")
            if not book_data:
                continue
            # Keep compilations for now
            # if book_data.get("compilation") is True: 
            #     continue
            parsed_book = _parse_hardcover_book(book_data)
            series_entries.append({
                "position": entry.get("position"),
                "book": parsed_book,
            })

        # Save books to database first
        for entry in deduped_series_books:
            book_data = entry.get("book")
            if not book_data:
                continue
            if book_data.get("compilation") is True:
                continue
            saved_book = _save_book_to_db(book_data, db)
            _ensure_series_fields(
                saved_book,
                series_info.get("id"),
                series_info.get("name"),
                entry.get("position"),
                db
            )
        
        # Enrich with local availability data
        books = _enrich_books_with_availability([entry["book"] for entry in series_entries], db)
        for entry, enriched in zip(series_entries, books):
            entry["book"] = enriched
        
        # Save series to database
        from app.models import Series
        db_series = db.query(Series).filter(Series.hardcover_id == series_info["id"]).first()
        if db_series:
            # Update existing series
            db_series.name = series_info["name"]
            db_series.books_count = series_info.get("books_count")
            db_series.last_refreshed = datetime.now()
        else:
            # Create new series
            db_series = Series(
                hardcover_id=series_info["id"],
                name=series_info["name"],
                books_count=series_info.get("books_count"),
                is_seed_data=False,
                last_refreshed=datetime.now()
            )
            db.add(db_series)
        db.commit()

        # Construct the series detail response
        books_count = series_info.get("books_count")
        if books_count is None:
            positions = [
                book.book_series[0].position
                for book in books
                if book.book_series and book.book_series[0] and book.book_series[0].position is not None
            ]
            max_position = max(positions) if positions else len(books)
            books_count = int(max_position) if max_position == int(max_position) else int(max_position) + 1
        
        series_detail = schemas.HardcoverSeriesDetail(
            id=series_info["id"],
            name=series_info["name"],
            author=series_info.get("author"),
            books_count=books_count,
            book_series=[
                schemas.HardcoverBookSeries(
                    position=entry.get("position"),
                    book=entry.get("book")
                ) for entry in series_entries
            ]
        )
        
        response = schemas.HardcoverSeriesResponse(series_by_pk=series_detail)
        
        # Cache the result
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["series"]
        )
        
        logger.info("series_api_fetched", series_id=series_id, count=len(books))
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("series_api_failed", series_id=series_id, error=str(e))
        raise HTTPException(status_code=404, detail="Series not found or no relevant books")

@router.post("/series/{series_id}/rebuild", response_model=schemas.HardcoverSeriesResponse)
async def rebuild_series(
    series_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Admin-only: clear series cache + DB record, then refetch from API."""
    cache_key = cache.make_cache_key("series", series_id=series_id)
    await cache.delete_cached(cache_key)

    db_series = db.query(Series).filter(Series.hardcover_id == series_id).first()
    if db_series:
        db.delete(db_series)
        db.commit()

    logger.info("series_rebuild_forcing_api", series_id=series_id)
    return await get_series_books(series_id, db, bypass_cache=True)

def _get_owned_counts_for_series(series_ids: list, db: Session) -> dict:
    """Get fresh owned counts for series from the database."""
    if not series_ids:
        return {}
    
    owned_books = db.query(
        Book.series_id,
        func.count(Book.id).label('count')
    ).filter(
        Book.series_id.in_(series_ids),
        or_(Book.ebook_available == True, Book.audiobook_available == True)
    ).group_by(Book.series_id).all()
    
    return {series_id: count for series_id, count in owned_books}


@router.get("/popular-series", response_model=schemas.HardcoverPopularSeriesResponse)
async def get_popular_series(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_total_ratings: int = Query(500, ge=0, description="Minimum total ratings across all books in series"),
    db: Session = Depends(database.get_db)
):
    """Get popular series - Cache → API (complex query, cache is better)"""
    # Check cache first (complex query)
    cache_key = cache.make_cache_key(
        "popular_series",
        limit=limit,
        offset=offset,
        min_total_ratings=min_total_ratings
    )
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("popular_series_cache_hit", limit=limit)
        # Always fetch fresh owned counts from database
        series_list = cached_result.get("series", [])
        series_ids = [s["id"] for s in series_list]
        owned_counts = _get_owned_counts_for_series(series_ids, db)
        
        # Update owned counts in cached result
        for series in series_list:
            series["owned_count"] = owned_counts.get(series["id"], 0)

        total = cached_result.get("total", len(series_list))
        cached_offset = cached_result.get("offset", offset)
        cached_limit = cached_result.get("limit", limit)
        has_more = cached_result.get("has_more")
        if has_more is None or has_more is False:
            # If the page is full, allow the client to attempt the next page.
            has_more = len(series_list) == cached_limit

        return schemas.HardcoverPopularSeriesResponse(
            series=series_list,
            total=total,
            has_more=has_more,
            offset=cached_offset,
            limit=cached_limit
        )
    
    try:
        fetch_limit = min((offset + limit) * 10, 500)
        
        graphql_query = """
        query PopularSeries($limit: Int!) {
          book_series(
            limit: $limit
            where: {
              book: {ratings_count: {_gt: 500}},
              series: {books_count: {_gte: 3, _lte: 10}}
            }
            order_by: {book: {activities_count: desc}}
          ) {
            position
            series {
              id
              name
              books_count
            }
            book {
              id
              title
              slug
              release_year
              release_date
              pages
              description
              cached_image
              cached_contributors
              rating
              ratings_count
              users_count
              activities_count
              default_ebook_edition_id
              default_audio_edition_id
              default_physical_edition_id
              contributions {
                author {
                  id
                  name
                  slug
                }
              }
              taggings(limit: 5) {
                tag {
                  tag
                }
              }
            }
          }
        }
        """
        
        result = await execute_graphql(graphql_query, {"limit": fetch_limit}, db=db)
        book_series_data = result.get("book_series", [])
        
        # Group by series and collect books
        series_map = {}
        for bs in book_series_data:
            series_info = bs.get("series")
            book_data = bs.get("book")
            position = bs.get("position")
            
            if not series_info or not book_data:
                continue
            
            series_id = series_info.get("id")
            if series_id not in series_map:
                series_map[series_id] = {
                    "id": series_id,
                    "name": series_info.get("name"),
                    "positions": set(),  # Track distinct positions
                    "books": [],
                    "total_activities_count": 0
                }
            
            # Track distinct positions
            if position is not None:
                series_map[series_id]["positions"].add(position)
            
            # Parse book and add to series
            try:
                parsed_book = _parse_hardcover_book(book_data)
                series_map[series_id]["books"].append(parsed_book)
                
                # Save book to database and ensure series fields are set
                saved_book = _save_book_to_db(book_data, db)
                _ensure_series_fields(
                    saved_book,
                    series_id,
                    series_info.get("name"),
                    position,
                    db
                )
                
                activities_count = book_data.get("activities_count", 0) or 0
                series_map[series_id]["total_activities_count"] += activities_count
            except Exception as e:
                logger.debug("failed_to_parse_book_in_series", series_id=series_id, error=str(e))
        
        # Convert to list and filter/sort
        series_with_activity = []
        for series_id, series_data in series_map.items():
            if len(series_data["books"]) > 0:
                first_book = series_data["books"][0]
                # Calculate books_count using MAX(position) instead of counting distinct positions
                # This handles partial positions (e.g., 0.5, 1.5) correctly
                positions = list(series_data["positions"])
                if positions:
                    max_position = max(positions)
                    books_count = int(max_position) if max_position == int(max_position) else int(max_position) + 1
                else:
                    books_count = len(series_data["books"])
                
                series_with_activity.append({
                    "id": series_data["id"],
                    "name": series_data["name"],
                    "books_count": books_count,  # Use MAX(position) rounded up
                    "first_book": first_book,
                    "total_activities_count": series_data["total_activities_count"]
                })
        
        # Sort by total activities_count
        series_with_activity.sort(key=lambda x: (x["total_activities_count"], x["books_count"]), reverse=True)
        
        total = len(series_with_activity)
        page_series = series_with_activity[offset:offset + limit]
        has_more = len(page_series) == limit
        
        # Get owned counts from database for each series
        series_ids = [s["id"] for s in page_series]
        owned_counts = _get_owned_counts_for_series(series_ids, db)
        
        # Transform to match schema
        series_list = [
            {
                "id": s["id"],
                "name": s["name"],
                "books_count": s["books_count"],
                "owned_count": owned_counts.get(s["id"], 0),
                "first_book": s["first_book"]
            }
            for s in page_series
        ]
        
        response = schemas.HardcoverPopularSeriesResponse(
            series=series_list,
            total=total,
            has_more=has_more,
            offset=offset,
            limit=limit
        )
        
        # Cache the result
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["popular_series"]
        )
        
        logger.info("popular_series_api_fetched", limit=limit, count=len(series_list))
        return response
    except Exception as e:
        logger.warning("popular_series_api_failed", error=str(e))
        return schemas.HardcoverPopularSeriesResponse(series=[])

@router.get("/similar/{book_id}", response_model=schemas.HardcoverBooksResponse)
async def get_similar_books(
    book_id: int,
    limit: int = Query(10, ge=1, le=50),
    bypass_cache: bool = False,
    db: Session = Depends(database.get_db)
):
    """Get similar books - Cache → API (complex recommendation logic)"""
    start_time = time.time()
    
    cache_key = cache.make_cache_key("similar_books", book_id=book_id, limit=limit)
    if bypass_cache:
        await cache.delete_cached(cache_key)
        logger.info("similar_books_cache_bypass", book_id=book_id, limit=limit)
    if not bypass_cache:
        cached_result = await cache.get_cached(cache_key)
        if cached_result is not None:
            logger.info("similar_books_cache_hit", book_id=book_id, limit=limit, duration_ms=(time.time() - start_time) * 1000)
            return schemas.HardcoverBooksResponse(**cached_result)
    
    # Get details of the target book
    book_details_query_start = time.time()
    book_details_query = """
    query GetBookForSimilar($id: Int!) {
      books_by_pk(id: $id) {
        id
        rating
        ratings_count
        contributions {
          author {
            id
          }
        }
        taggings(limit: 15) {
          tag {
            tag
          }
        }
        book_series {
          series {
            id
          }
        }
      }
    }
    """
    book_result = await execute_graphql(book_details_query, {"id": book_id}, db=db)
    book_data = book_result.get("books_by_pk")
    book_details_duration = (time.time() - book_details_query_start) * 1000
    
    if not book_data:
        raise HTTPException(status_code=404, detail="Target book not found for similarity search")
    
    # Extract metadata
    author_ids = [c["author"]["id"] for c in book_data.get("contributions", []) if c.get("author", {}).get("id")]
    tag_names = [t["tag"]["tag"] for t in book_data.get("taggings", []) if t.get("tag", {}).get("tag")]
    series_id = None
    if book_data.get("book_series") and len(book_data["book_series"]) > 0:
        series_id = book_data["book_series"][0].get("series", {}).get("id")
    
    similar_books = []
    seen_book_ids = {book_id}
    
    # Fetch books from the same series (highest priority)
    series_query_start = time.time()
    if series_id and len(similar_books) < limit:
        series_books_to_fetch = limit * 2
        series_query = """
        query SimilarBySeries($limit: Int!, $excludeId: Int!, $seriesId: Int!) {
          books(
            limit: $limit,
            order_by: {users_count: desc_nulls_last, rating: desc_nulls_last},
            where: {
              _and: [
                {id: {_neq: $excludeId}},
                {book_series: {series: {id: {_eq: $seriesId}}}},
                {ratings_count: {_gte: 50}}
              ]
            }
          ) {
            id
            title
            slug
            release_year
            release_date
            pages
            description
            cached_image
            cached_contributors
            rating
            ratings_count
            users_count
            activities_count
            default_ebook_edition_id
            default_audio_edition_id
            default_physical_edition_id
            book_series {
              series {
                id
                name
              }
              position
            }
            contributions {
              author {
                id
                name
                slug
              }
            }
            taggings(limit: 5) {
              tag {
                tag
              }
            }
          }
        }
        """
        result = await execute_graphql(series_query, {"limit": series_books_to_fetch, "excludeId": book_id, "seriesId": series_id}, db=db)
        series_duration = (time.time() - series_query_start) * 1000
        new_books = result.get("books", [])
        for book in new_books:
            if book["id"] not in seen_book_ids:
                book_author_ids = [c["author"]["id"] for c in book.get("contributions", []) if c.get("author", {}).get("id")]
                if not set(book_author_ids) & set(author_ids):
                    similar_books.append(book)
                    seen_book_ids.add(book["id"])
                    # Save to database
                    _save_book_to_db(book, db)
        logger.info("similar_books_series_query", duration_ms=series_duration, books_found=len(new_books), books_added=len(similar_books))
    
    # Fetch books with overlapping tags
    tags_query_start = time.time()
    if len(similar_books) < limit and len(tag_names) >= 1:
        top_tags = tag_names[:3]
        tags_str = ", ".join([f'"{tag}"' for tag in top_tags])
        tags_books_to_fetch = (limit - len(similar_books)) * 3
        
        tags_query = f"""
        query SimilarByTags($limit: Int!, $excludeId: Int!) {{
          books(
            limit: $limit,
            order_by: {{users_count: desc_nulls_last, rating: desc_nulls_last}},
            where: {{
              _and: [
                {{id: {{_neq: $excludeId}}}},
                {{taggings: {{tag: {{tag: {{_in: [{tags_str}]}}}}}}}},
                {{ratings_count: {{_gte: 50}}}}
              ]
            }}
          ) {{
            id
            title
            slug
            release_year
            release_date
            pages
            description
            cached_image
            cached_contributors
            rating
            ratings_count
            users_count
            activities_count
            default_ebook_edition_id
            default_audio_edition_id
            default_physical_edition_id
            book_series {{
              series {{
                id
                name
              }}
              position
            }}
            contributions {{
              author {{
                id
                name
                slug
              }}
            }}
            taggings(limit: 5) {{
              tag {{
                tag
              }}
            }}
          }}
        }}
        """
        result = await execute_graphql(tags_query, {"limit": tags_books_to_fetch, "excludeId": book_id}, db=db)
        tags_duration = (time.time() - tags_query_start) * 1000
        all_tag_books = result.get("books", [])
        
        scored_tag_books = []
        for book in all_tag_books:
            if book["id"] not in seen_book_ids:
                book_author_ids = [c["author"]["id"] for c in book.get("contributions", []) if c.get("author", {}).get("id")]
                if not set(book_author_ids) & set(author_ids):
                    book_tags = [t["tag"]["tag"] for t in book.get("taggings", []) if t.get("tag", {}).get("tag")]
                    tag_overlap = len(set(top_tags) & set(book_tags))
                    if tag_overlap > 0:
                        scored_tag_books.append((book, tag_overlap))
        
        scored_tag_books.sort(key=lambda x: x[1], reverse=True)
        for book, _ in scored_tag_books[:limit - len(similar_books)]:
            similar_books.append(book)
            seen_book_ids.add(book["id"])
            # Save to database
            _save_book_to_db(book, db)
        logger.info("similar_books_tags_query", duration_ms=tags_duration, books_found=len(all_tag_books), books_added=len(scored_tag_books[:limit - len(similar_books)]))
    
    # Parse books
    books = [_parse_hardcover_book(book) for book in similar_books[:limit]]
    
    # Enrich with local availability data
    books = _enrich_books_with_availability(books, db)
    
    response = schemas.HardcoverBooksResponse(books=books)
    
    total_duration = (time.time() - start_time) * 1000
    logger.info(
        "similar_books_fetched",
        book_id=book_id,
        limit=limit,
        books_count=len(books),
        total_duration_ms=total_duration,
        book_details_duration_ms=book_details_duration,
        series_query_duration_ms=series_duration if 'series_duration' in locals() else 0,
        tags_query_duration_ms=tags_duration if 'tags_duration' in locals() else 0,
    )
    
    # Cache the result
    await cache.set_cached(
        cache_key,
        response.model_dump(),
        ttl=cache.CACHE_TTL["similar_books"]
    )
    
    return response

@router.get("/prompts/{book_id}", response_model=schemas.HardcoverBookPromptsResponse)
async def get_book_prompts(
    book_id: int,
    limit: int = Query(12, ge=1, le=40),
    bypass_cache: bool = False,
    db: Session = Depends(database.get_db)
):
    """Get Hardcover prompts that include this book - Cache → API"""
    cache_key = cache.make_cache_key("book_prompts", book_id=book_id, limit=limit)
    if bypass_cache:
        await cache.delete_cached(cache_key)
        logger.info("book_prompts_cache_bypass", book_id=book_id, limit=limit)
    if not bypass_cache:
        cached_result = await cache.get_cached(cache_key)
        if cached_result is not None:
            logger.info("book_prompts_cache_hit", book_id=book_id, limit=limit)
            return schemas.HardcoverBookPromptsResponse(**cached_result)

    try:
        graphql_query = """
        query BookPrompts($id: Int!) {
          books_by_pk(id: $id) {
            prompt_summaries(order_by: {answers_count: desc_nulls_last}) {
              answers_count
              prompt {
                slug
                answers_count
                books_count
                question
                prompt_books {
                  book {
                    id
                    title
                    slug
                    release_year
                    release_date
                    pages
                    description
                    cached_image
                    cached_contributors
                    rating
                    ratings_count
                    users_count
                    activities_count
                    default_ebook_edition_id
                    default_audio_edition_id
                    default_physical_edition_id
                    book_series {
                      series {
                        id
                        name
                      }
                      position
                    }
                    contributions {
                      author {
                        id
                        name
                        slug
                      }
                    }
                    taggings(limit: 5) {
                      tag {
                        tag
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        result = await execute_graphql(graphql_query, {"id": book_id}, db=db)
        book_data = result.get("books_by_pk") or {}
        prompt_summaries = book_data.get("prompt_summaries", []) or []

        trimmed_summaries = []
        for summary in prompt_summaries:
            prompt = summary.get("prompt") or {}
            prompt_books = prompt.get("prompt_books", []) or []
            prompt_books = prompt_books[:limit]

            parsed_prompt_books = []
            for entry in prompt_books:
                book_data = entry.get("book")
                if not book_data:
                    continue
                parsed_prompt_books.append({"book": _parse_hardcover_book(book_data)})

            trimmed_summaries.append({
                "answers_count": summary.get("answers_count"),
                "prompt": {
                    "slug": prompt.get("slug"),
                    "answers_count": prompt.get("answers_count"),
                    "books_count": prompt.get("books_count"),
                    "question": prompt.get("question"),
                    "prompt_books": parsed_prompt_books,
                }
            })

        response = schemas.HardcoverBookPromptsResponse(prompt_summaries=trimmed_summaries)
        await cache.set_cached(
            cache_key,
            response.model_dump(),
            ttl=cache.CACHE_TTL["book_prompts"]
        )
        return response
    except Exception as e:
        logger.warning("book_prompts_api_failed", book_id=book_id, error=str(e))
        return schemas.HardcoverBookPromptsResponse(prompt_summaries=[])

@router.get("/by-author/{book_id}", response_model=schemas.HardcoverBooksResponse)
async def get_books_by_author(book_id: int, limit: int = Query(10, ge=1, le=50), db: Session = Depends(database.get_db)):
    """Get other books by the same author(s) - Database → Cache → API"""
    # Get the book to extract author IDs
    db_book = db.query(Book).filter(Book.hardcover_id == book_id).first()
    
    if db_book:
        # Try to find books by same author in database
        author_name = db_book.author
        if author_name:
            db_author_books = db.query(Book).filter(
                Book.author.ilike(f"%{author_name}%"),
                Book.hardcover_id != book_id,
                Book.ratings_count >= 50
            ).order_by(
                Book.users_count.desc().nulls_last(),
                Book.rating.desc().nulls_last()
            ).limit(limit).all()
            
            if len(db_author_books) >= limit:
                logger.info("books_by_author_database_hit", book_id=book_id, count=len(db_author_books))
                hc_books = [_db_book_to_hardcover_book(book) for book in db_author_books]
                return schemas.HardcoverBooksResponse(books=hc_books)
    
    # Check cache
    cache_key = cache.make_cache_key("books_by_author", book_id=book_id, limit=limit)
    cached_result = await cache.get_cached(cache_key)
    if cached_result is not None:
        logger.info("books_by_author_cache_hit", book_id=book_id, limit=limit)
        return schemas.HardcoverBooksResponse(**cached_result)
    
    # Get author IDs from API
    book_details_query = """
    query GetBookAuthors($id: Int!) {
      books_by_pk(id: $id) {
        id
        contributions {
          author {
            id
            name
          }
        }
      }
    }
    """
    
    book_result = await execute_graphql(book_details_query, {"id": book_id}, db=db)
    book_data = book_result.get("books_by_pk")
    
    if not book_data:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Extract author IDs
    author_ids = [c["author"]["id"] for c in book_data.get("contributions", []) if c.get("author", {}).get("id")]
    
    if not author_ids:
        response = schemas.HardcoverBooksResponse(books=[])
        await cache.set_cached(cache_key, response.model_dump(), ttl=cache.CACHE_TTL["similar_books"])
        return response
    
    # Query books by same authors
    authors_query = """
    query BooksByAuthor($limit: Int!, $excludeId: Int!, $authorIds: [Int!]!) {
      books(
        limit: $limit,
        order_by: {users_count: desc_nulls_last, rating: desc_nulls_last},
        where: {
          _and: [
            {id: {_neq: $excludeId}},
            {contributions: {author: {id: {_in: $authorIds}}}},
            {ratings_count: {_gte: 50}}
          ]
        }
      ) {
        id
        title
        slug
        release_year
        release_date
        pages
        description
        cached_image
        cached_contributors
        rating
        ratings_count
        users_count
        activities_count
        default_ebook_edition_id
        default_audio_edition_id
        default_physical_edition_id
        book_series {
          series {
            id
            name
          }
          position
        }
        contributions {
          author {
            id
            name
            slug
          }
        }
        taggings(limit: 5) {
          tag {
            tag
          }
        }
      }
    }
    """
    
    result = await execute_graphql(authors_query, {
        "limit": limit,
        "excludeId": book_id,
        "authorIds": author_ids[:3]
    }, db=db)
    
    books_data = result.get("books", [])
    books = [_parse_hardcover_book(book) for book in books_data]
    
    # Save to database first
    for book_data in books_data:
        _save_book_to_db(book_data, db)
    
    # Enrich with local availability data
    books = _enrich_books_with_availability(books, db)
    
    response = schemas.HardcoverBooksResponse(books=books)
    
    await cache.set_cached(
        cache_key,
        response.model_dump(),
        ttl=cache.CACHE_TTL["similar_books"]
    )
    
    logger.info("books_by_author_api_fetched", book_id=book_id, count=len(books))
    return response
