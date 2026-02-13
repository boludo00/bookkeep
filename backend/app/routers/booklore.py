"""Booklore API integration for checking book availability"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import httpx
import structlog

from app import database, models, schemas
from app.auth import get_current_user, require_admin

logger = structlog.get_logger()

router = APIRouter()


# Token cache - stores tokens in memory for quick access
_token_cache: Dict[int, Dict[str, Any]] = {}

def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def get_booklore_token(server: models.BookloreServer, db: Session) -> str:
    """
    Get a valid access token for Booklore API.
    Uses cached token if valid, otherwise refreshes or re-authenticates.
    """
    server_id = server.id
    
    # Check memory cache first
    if server_id in _token_cache:
        cached = _token_cache[server_id]
        cached_expires_at = _as_utc(cached.get("expires_at"))
        if cached_expires_at and cached_expires_at > datetime.now(timezone.utc):
            return cached["access_token"]
    
    # Check database cache
    if server.access_token and server.token_expires_at:
        token_expires_at = _as_utc(server.token_expires_at)
        if token_expires_at and token_expires_at > datetime.now(timezone.utc):
            # Cache in memory
            _token_cache[server_id] = {
                "access_token": server.access_token,
                "expires_at": token_expires_at
            }
            return server.access_token
        
        # Token expired, try to refresh
        if server.refresh_token:
            try:
                new_tokens = await _refresh_token(server)
                if new_tokens:
                    return new_tokens["access_token"]
            except Exception as e:
                logger.warning("booklore_token_refresh_failed", error=str(e))
    
    # Need to authenticate fresh
    tokens = await _authenticate(server)
    
    # Save tokens to database
    server.access_token = tokens["access_token"]
    server.refresh_token = tokens.get("refresh_token")
    # JWT tokens typically expire in 24 hours, but we'll be conservative
    server.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=23)
    db.add(server)
    db.commit()
    
    # Cache in memory
    _token_cache[server_id] = {
        "access_token": tokens["access_token"],
        "expires_at": server.token_expires_at
    }
    
    return tokens["access_token"]


async def _authenticate(server: models.BookloreServer) -> Dict[str, str]:
    """Authenticate with Booklore and get JWT tokens"""
    url = f"{server.url.rstrip('/')}/api/v1/auth/login"
    
    logger.info("booklore_authenticating", url=url, username=server.username)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json={"username": server.username, "password": server.password}
            )
            
            if response.status_code == 200:
                tokens = response.json()
                logger.info("booklore_auth_success", has_access_token=bool(tokens.get("accessToken")))
                return {
                    "access_token": tokens.get("accessToken"),
                    "refresh_token": tokens.get("refreshToken")
                }
            else:
                logger.error("booklore_auth_failed", 
                           status_code=response.status_code,
                           response=response.text[:200])
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Booklore authentication failed: {response.status_code}"
                )
    except httpx.RequestError as e:
        logger.error("booklore_auth_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to Booklore: {str(e)}"
        )


async def _refresh_token(server: models.BookloreServer) -> Optional[Dict[str, str]]:
    """Refresh the access token using refresh token"""
    url = f"{server.url.rstrip('/')}/api/v1/auth/refresh"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json={"refreshToken": server.refresh_token}
            )
            
            if response.status_code == 200:
                tokens = response.json()
                return {
                    "access_token": tokens.get("accessToken"),
                    "refresh_token": tokens.get("refreshToken")
                }
    except Exception as e:
        logger.warning("booklore_refresh_error", error=str(e))
    
    return None


async def get_booklore_books(server: models.BookloreServer, db: Session) -> List[Dict[str, Any]]:
    """Get all books from Booklore with their metadata"""
    try:
        token = await get_booklore_token(server, db)
    except HTTPException as e:
        logger.error("booklore_token_error", detail=e.detail, status_code=e.status_code)
        return []
    except Exception as e:
        logger.error("booklore_token_error", error=str(e), error_type=type(e).__name__)
        return []
    
    url = f"{server.url.rstrip('/')}/api/v1/books?withDescription=false"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                books = response.json()
                logger.info("booklore_books_fetched", count=len(books))
                return books
            elif response.status_code == 401:
                # Token might be invalid, clear cache and retry
                if server.id in _token_cache:
                    del _token_cache[server.id]
                server.access_token = None
                server.refresh_token = None
                server.token_expires_at = None
                db.add(server)
                db.commit()
                
                # Retry once
                token = await get_booklore_token(server, db)
                headers = {"Authorization": f"Bearer {token}"}
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response.json()
            
            logger.error("booklore_books_fetch_failed",
                        status_code=response.status_code,
                        response_text=response.text[:500] if response.text else "empty")
            return []
    except httpx.RequestError as e:
        logger.error("booklore_books_request_error", 
                    error=str(e), 
                    error_type=type(e).__name__,
                    url=url)
        return []
    except Exception as e:
        logger.error("booklore_books_error", 
                    error=str(e), 
                    error_type=type(e).__name__)
        return []


async def find_book_by_hardcover_id(
    server: models.BookloreServer, 
    hardcover_id: int, 
    db: Session
) -> Optional[Dict[str, Any]]:
    """
    Find a book in Booklore by its Hardcover ID.
    Returns the book data if found, None otherwise.
    """
    books = await get_booklore_books(server, db)
    
    for book in books:
        metadata = book.get("metadata", {})
        book_hardcover_id = metadata.get("hardcoverId")
        
        if book_hardcover_id and str(book_hardcover_id) == str(hardcover_id):
            logger.info("booklore_book_found",
                       hardcover_id=hardcover_id,
                       booklore_id=book.get("id"),
                       title=book.get("title"))
            return book
    
    logger.debug("booklore_book_not_found", hardcover_id=hardcover_id)
    return None


def get_default_booklore_server(db: Session) -> Optional[models.BookloreServer]:
    """Get the default Booklore server"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.is_default == True
    ).first()
    
    if not server:
        # Fall back to first server if no default
        server = db.query(models.BookloreServer).first()
    
    return server


# API Endpoints

@router.get("/", response_model=List[schemas.BookloreServerResponse])
async def list_servers(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """List all Booklore servers (admin only)"""
    servers = db.query(models.BookloreServer).all()
    return servers


@router.post("/", response_model=schemas.BookloreServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(
    server: schemas.BookloreServerCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Create a new Booklore server configuration (admin only)"""
    # If this is set as default, unset other defaults
    if server.is_default:
        db.query(models.BookloreServer).update({"is_default": False})
    
    db_server = models.BookloreServer(
        name=server.name,
        url=server.url,
        username=server.username,
        password=server.password,
        is_default=server.is_default,
        ebook_library_id=server.ebook_library_id,
        audiobook_library_id=server.audiobook_library_id,
    )
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    
    logger.info("booklore_server_created", server_id=db_server.id, name=db_server.name)
    return db_server


@router.get("/{server_id}", response_model=schemas.BookloreServerResponse)
async def get_server(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Get a specific Booklore server (admin only)"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.id == server_id
    ).first()
    
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booklore server not found"
        )
    
    return server


@router.put("/{server_id}", response_model=schemas.BookloreServerResponse)
async def update_server(
    server_id: int,
    server_update: schemas.BookloreServerUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Update a Booklore server configuration (admin only)"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.id == server_id
    ).first()
    
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booklore server not found"
        )
    
    # If setting as default, unset others
    if server_update.is_default:
        db.query(models.BookloreServer).filter(
            models.BookloreServer.id != server_id
        ).update({"is_default": False})
    
    # Update fields
    update_data = server_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)
    
    # Clear cached tokens if credentials changed
    if "username" in update_data or "password" in update_data or "url" in update_data:
        server.access_token = None
        server.refresh_token = None
        server.token_expires_at = None
        if server_id in _token_cache:
            del _token_cache[server_id]
    
    db.add(server)
    db.commit()
    db.refresh(server)
    
    logger.info("booklore_server_updated", server_id=server_id)
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Delete a Booklore server configuration (admin only)"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.id == server_id
    ).first()
    
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booklore server not found"
        )
    
    # Clear from cache
    if server_id in _token_cache:
        del _token_cache[server_id]
    
    db.delete(server)
    db.commit()
    
    logger.info("booklore_server_deleted", server_id=server_id)
    return None


@router.post("/test", response_model=schemas.BookloreTestConnectionResponse)
async def test_connection(
    request: schemas.BookloreTestConnectionRequest,
    current_user: models.User = Depends(require_admin)
):
    """Test connection to a Booklore server (admin only)"""
    url = f"{request.url.rstrip('/')}/api/v1/auth/login"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Try to authenticate
            response = await client.post(
                url,
                json={"username": request.username, "password": request.password}
            )
            
            if response.status_code == 200:
                tokens = response.json()
                access_token = tokens.get("accessToken")
                
                # Try to get libraries
                libraries_url = f"{request.url.rstrip('/')}/api/v1/libraries"
                headers = {"Authorization": f"Bearer {access_token}"}
                
                lib_response = await client.get(libraries_url, headers=headers)
                libraries = []
                
                if lib_response.status_code == 200:
                    libraries = lib_response.json()
                
                return schemas.BookloreTestConnectionResponse(
                    success=True,
                    libraries=libraries
                )
            else:
                return schemas.BookloreTestConnectionResponse(
                    success=False,
                    error=f"Authentication failed: {response.status_code}"
                )
    except httpx.RequestError as e:
        return schemas.BookloreTestConnectionResponse(
            success=False,
            error=f"Connection error: {str(e)}"
        )
    except Exception as e:
        return schemas.BookloreTestConnectionResponse(
            success=False,
            error=f"Error: {str(e)}"
        )


@router.get("/{server_id}/books")
async def get_books(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Get all books from a Booklore server (admin only)"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.id == server_id
    ).first()
    
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booklore server not found"
        )
    
    books = await get_booklore_books(server, db)
    return books


@router.get("/{server_id}/check/{hardcover_id}")
async def check_book_availability(
    server_id: int,
    hardcover_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Check if a book is available in Booklore by Hardcover ID"""
    server = db.query(models.BookloreServer).filter(
        models.BookloreServer.id == server_id
    ).first()
    
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booklore server not found"
        )
    
    book = await find_book_by_hardcover_id(server, hardcover_id, db)
    
    return {
        "available": book is not None,
        "book": book
    }
