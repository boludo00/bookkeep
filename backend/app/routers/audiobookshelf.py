"""Audiobookshelf API integration for audiobook availability"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
import httpx
import structlog

from app import database, models, schemas
from app.auth import get_current_user, require_admin

logger = structlog.get_logger()

router = APIRouter()


def get_default_audiobookshelf_server(db: Session) -> Optional[models.AudiobookshelfServer]:
    """Get the default Audiobookshelf server"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.is_default == True
    ).first()

    if not server:
        # Fall back to first server if no default
        server = db.query(models.AudiobookshelfServer).first()

    return server


def _auth_headers(server: models.AudiobookshelfServer) -> Dict[str, str]:
    """Build authorization headers for Audiobookshelf API"""
    return {"Authorization": f"Bearer {server.api_key}"}


async def get_audiobookshelf_libraries(server: models.AudiobookshelfServer) -> List[Dict[str, Any]]:
    """Get all libraries from Audiobookshelf, filtering out podcast libraries"""
    url = f"{server.url.rstrip('/')}/api/libraries"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            response = await client.get(url, headers=_auth_headers(server))

            if response.status_code == 200:
                data = response.json()
                libraries = data.get("libraries", data) if isinstance(data, dict) else data
                # Filter out podcast libraries
                return [
                    lib for lib in libraries
                    if lib.get("mediaType") != "podcast"
                ]
            else:
                logger.error("audiobookshelf_libraries_failed",
                             status_code=response.status_code,
                             response=response.text[:200])
                return []
    except httpx.RequestError as e:
        logger.error("audiobookshelf_libraries_error", error=str(e))
        return []


async def get_audiobookshelf_library_items(
    server: models.AudiobookshelfServer,
    library_id: str,
) -> List[Dict[str, Any]]:
    """Get all items from a specific Audiobookshelf library with pagination"""
    base_url = f"{server.url.rstrip('/')}/api/libraries/{library_id}/items"
    all_items = []
    page = 0
    limit = 100

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:
            while True:
                response = await client.get(
                    base_url,
                    headers=_auth_headers(server),
                    params={"minified": "1", "limit": limit, "page": page},
                )

                if response.status_code != 200:
                    logger.error("audiobookshelf_items_failed",
                                 library_id=library_id,
                                 status_code=response.status_code)
                    break

                data = response.json()
                results = data.get("results", [])
                all_items.extend(results)

                total = data.get("total", 0)
                if len(all_items) >= total or not results:
                    break

                page += 1

        logger.info("audiobookshelf_items_fetched",
                     library_id=library_id,
                     count=len(all_items))
        return all_items
    except httpx.RequestError as e:
        logger.error("audiobookshelf_items_error",
                     library_id=library_id,
                     error=str(e))
        return []


def match_book_to_abs_item(book: models.Book, item: Dict[str, Any]) -> bool:
    """Check if an Audiobookshelf item matches a Book record by ISBN or title+author"""
    media = item.get("media", {})
    metadata = media.get("metadata", {})
    item_isbn = metadata.get("isbn")
    if item_isbn and book.isbn and item_isbn == book.isbn:
        return True
    item_title = metadata.get("title", "")
    item_author = metadata.get("authorName", "")
    if (item_title and book.title and
            item_title.lower() == book.title.lower() and
            item_author and book.author and
            item_author.lower() == book.author.lower()):
        return True
    return False


async def search_audiobookshelf_items(
    server: models.AudiobookshelfServer,
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search for items in Audiobookshelf by title/author (targeted, not full scan)"""
    library_ids = [server.library_id] if server.library_id else [
        lib["id"] for lib in await get_audiobookshelf_libraries(server)
    ]
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            for lib_id in library_ids:
                url = f"{server.url.rstrip('/')}/api/libraries/{lib_id}/search"
                response = await client.get(
                    url,
                    headers=_auth_headers(server),
                    params={"q": query, "limit": limit},
                )
                if response.status_code == 200:
                    data = response.json()
                    for entry in data.get("book", []):
                        lib_item = entry.get("libraryItem")
                        if lib_item:
                            results.append(lib_item)
    except httpx.RequestError as e:
        logger.error("audiobookshelf_search_error", query=query, error=str(e))
    return results


async def get_all_audiobookshelf_items(server: models.AudiobookshelfServer) -> List[Dict[str, Any]]:
    """
    Get all audiobook items from Audiobookshelf.
    If server.library_id is set, scan only that library; otherwise scan all book-type libraries.
    """
    if server.library_id:
        return await get_audiobookshelf_library_items(server, server.library_id)

    libraries = await get_audiobookshelf_libraries(server)
    all_items = []

    for lib in libraries:
        lib_id = lib.get("id")
        if lib_id:
            items = await get_audiobookshelf_library_items(server, lib_id)
            all_items.extend(items)

    return all_items


# API Endpoints

@router.get("/", response_model=List[schemas.AudiobookshelfServerResponse])
async def list_servers(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """List all Audiobookshelf servers (admin only)"""
    servers = db.query(models.AudiobookshelfServer).all()
    return servers


@router.post("/", response_model=schemas.AudiobookshelfServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(
    server: schemas.AudiobookshelfServerCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Create a new Audiobookshelf server configuration (admin only)"""
    # If this is set as default, unset other defaults
    if server.is_default:
        db.query(models.AudiobookshelfServer).update({"is_default": False})

    db_server = models.AudiobookshelfServer(
        name=server.name,
        url=server.url,
        api_key=server.api_key,
        is_default=server.is_default,
        library_id=server.library_id,
    )
    db.add(db_server)
    db.commit()
    db.refresh(db_server)

    logger.info("audiobookshelf_server_created", server_id=db_server.id, name=db_server.name)
    return db_server


@router.get("/{server_id}", response_model=schemas.AudiobookshelfServerResponse)
async def get_server(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Get a specific Audiobookshelf server (admin only)"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.id == server_id
    ).first()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audiobookshelf server not found"
        )

    return server


@router.put("/{server_id}", response_model=schemas.AudiobookshelfServerResponse)
async def update_server(
    server_id: int,
    server_update: schemas.AudiobookshelfServerUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Update an Audiobookshelf server configuration (admin only)"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.id == server_id
    ).first()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audiobookshelf server not found"
        )

    # If setting as default, unset others
    if server_update.is_default:
        db.query(models.AudiobookshelfServer).filter(
            models.AudiobookshelfServer.id != server_id
        ).update({"is_default": False})

    # Update fields (skip api_key if not provided or empty)
    update_data = server_update.model_dump(exclude_unset=True)
    if "api_key" in update_data and not update_data["api_key"]:
        del update_data["api_key"]
    for field, value in update_data.items():
        setattr(server, field, value)

    db.add(server)
    db.commit()
    db.refresh(server)

    logger.info("audiobookshelf_server_updated", server_id=server_id)
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Delete an Audiobookshelf server configuration (admin only)"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.id == server_id
    ).first()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audiobookshelf server not found"
        )

    db.delete(server)
    db.commit()

    logger.info("audiobookshelf_server_deleted", server_id=server_id)
    return None


@router.post("/test", response_model=schemas.AudiobookshelfTestConnectionResponse)
async def test_connection(
    request: schemas.AudiobookshelfTestConnectionRequest,
    current_user: models.User = Depends(require_admin)
):
    """Test connection to an Audiobookshelf server (admin only)"""
    url = f"{request.url.rstrip('/')}/api/authorize"
    headers = {"Authorization": f"Bearer {request.api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            response = await client.post(url, headers=headers)

            logger.debug("audiobookshelf_test_connection",
                        status_code=response.status_code)

            if response.status_code == 200:
                # Get libraries
                lib_url = f"{request.url.rstrip('/')}/api/libraries"
                lib_response = await client.get(lib_url, headers=headers)
                libraries = []

                if lib_response.status_code == 200:
                    data = lib_response.json()
                    raw_libs = data.get("libraries", data) if isinstance(data, dict) else data
                    libraries = [
                        {"id": lib.get("id"), "name": lib.get("name"), "mediaType": lib.get("mediaType")}
                        for lib in raw_libs
                        if lib.get("mediaType") != "podcast"
                    ]

                return schemas.AudiobookshelfTestConnectionResponse(
                    success=True,
                    libraries=libraries
                )
            else:
                return schemas.AudiobookshelfTestConnectionResponse(
                    success=False,
                    error=f"Authentication failed (HTTP {response.status_code}). Check your URL and API key."
                )
    except httpx.RequestError as e:
        return schemas.AudiobookshelfTestConnectionResponse(
            success=False,
            error=f"Connection error: {str(e)}"
        )
    except Exception as e:
        return schemas.AudiobookshelfTestConnectionResponse(
            success=False,
            error=f"Error: {str(e)}"
        )


@router.get("/{server_id}/items")
async def get_items(
    server_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Get all items from an Audiobookshelf server (admin only)"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.id == server_id
    ).first()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audiobookshelf server not found"
        )

    items = await get_all_audiobookshelf_items(server)
    return items


@router.get("/{server_id}/check/{hardcover_id}")
async def check_book_availability(
    server_id: int,
    hardcover_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Check if a book is available in Audiobookshelf by Hardcover ID"""
    server = db.query(models.AudiobookshelfServer).filter(
        models.AudiobookshelfServer.id == server_id
    ).first()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audiobookshelf server not found"
        )

    # Check if we already have a linked audiobookshelf_id for this book
    book = db.query(models.Book).filter(
        models.Book.hardcover_id == hardcover_id
    ).first()

    if book and book.audiobookshelf_id:
        return {"available": True, "source": "cached_link"}

    if not book:
        return {"available": False}

    # Targeted search instead of fetching all items
    search_query = book.title or ""
    if book.author:
        search_query = f"{search_query} {book.author}"

    items = await search_audiobookshelf_items(server, search_query.strip())

    for item in items:
        if match_book_to_abs_item(book, item):
            book.audiobookshelf_id = item.get("id")
            db.commit()
            return {"available": True, "item_id": item.get("id"), "source": "search_match"}

    return {"available": False}
