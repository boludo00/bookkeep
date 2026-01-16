from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import httpx
import structlog
from app import database, models, schemas
from app.cache import get_cached, set_cached, make_cache_key, CACHE_TTL
from app.services.readarr_service import (
    ReadarrClient,
    ReadarrService,
    build_readarr_url,
    get_readarr_server_for_format,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _get_cached_library(server: models.ReadarrServer) -> List[Dict[str, Any]]:
    cache_key = make_cache_key("readarr_library", server_id=server.id)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    readarr_client = ReadarrClient.from_server(server)
    async with readarr_client.session(timeout=15.0) as client:
        books = await readarr_client.get_library_books(client)
    await set_cached(cache_key, books, ttl=CACHE_TTL.get("readarr_library", 60))
    return books

async def test_readarr_connection(
    hostname: str,
    port: int,
    use_ssl: bool,
    api_key: str,
    url_base: Optional[str] = None
) -> schemas.ReadarrTestConnectionResponse:
    """Test Readarr connection and fetch available resources"""
    base_url = build_readarr_url(hostname, port, use_ssl, url_base)
    api_url = f"{base_url}/api/v1"
    
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test connection with system status
            status_response = await client.get(f"{api_url}/system/status", headers=headers)
            if status_response.status_code != 200:
                return schemas.ReadarrTestConnectionResponse(
                    success=False,
                    error=f"Connection failed: HTTP {status_response.status_code}"
                )
            
            # Fetch quality profiles
            quality_profiles = []
            try:
                profiles_response = await client.get(f"{api_url}/qualityProfile", headers=headers)
                if profiles_response.status_code == 200:
                    profiles_data = profiles_response.json()
                    quality_profiles = [
                        schemas.ReadarrQualityProfile(id=p.get("id"), name=p.get("name", ""))
                        for p in profiles_data
                    ]
            except Exception as e:
                logger.warning("failed_to_fetch_quality_profiles", error=str(e))
            
            # Fetch root folders
            root_folders = []
            try:
                folders_response = await client.get(f"{api_url}/rootFolder", headers=headers)
                if folders_response.status_code == 200:
                    folders_data = folders_response.json()
                    root_folders = [
                        schemas.ReadarrRootFolder(
                            path=f.get("path", ""),
                            freeSpace=f.get("freeSpace"),
                            totalSpace=f.get("totalSpace")
                        )
                        for f in folders_data
                    ]
            except Exception as e:
                logger.warning("failed_to_fetch_root_folders", error=str(e))
            
            # Fetch tags
            tags = []
            try:
                tags_response = await client.get(f"{api_url}/tag", headers=headers)
                if tags_response.status_code == 200:
                    tags_data = tags_response.json()
                    tags = [
                        schemas.ReadarrTag(id=t.get("id"), label=t.get("label", ""))
                        for t in tags_data
                    ]
            except Exception as e:
                logger.warning("failed_to_fetch_tags", error=str(e))
            
            return schemas.ReadarrTestConnectionResponse(
                success=True,
                quality_profiles=quality_profiles,
                root_folders=root_folders,
                tags=tags
            )
    except httpx.TimeoutException:
        return schemas.ReadarrTestConnectionResponse(
            success=False,
            error="Connection timeout - check your hostname and port"
        )
    except httpx.ConnectError:
        return schemas.ReadarrTestConnectionResponse(
            success=False,
            error="Could not connect to Readarr - check your hostname, port, and SSL settings"
        )
    except Exception as e:
        logger.error("readarr_connection_test_failed", error=str(e))
        return schemas.ReadarrTestConnectionResponse(
            success=False,
            error=f"Connection test failed: {str(e)}"
        )

@router.post("/test-connection", response_model=schemas.ReadarrTestConnectionResponse)
async def test_connection(
    request: schemas.ReadarrTestConnectionRequest,
    db: Session = Depends(database.get_db)
):
    """Test Readarr connection and fetch available resources"""
    return await test_readarr_connection(
        hostname=request.hostname,
        port=request.port,
        use_ssl=request.use_ssl,
        api_key=request.api_key,
        url_base=request.url_base
    )

@router.get("/", response_model=List[schemas.ReadarrServerResponse])
def get_readarr_servers(db: Session = Depends(database.get_db)):
    """Get all Readarr servers"""
    servers = db.query(models.ReadarrServer).all()
    return servers


@router.get("/configured-formats")
async def get_configured_formats(db: Session = Depends(database.get_db)):
    """Return which formats (ebook/audiobook) have Readarr servers configured"""
    servers = db.query(models.ReadarrServer).all()
    return {
        "ebook": any(not s.is_audiobook for s in servers),
        "audiobook": any(s.is_audiobook for s in servers)
    }


@router.get("/availability/{hardcover_id}")
async def check_book_availability_by_format(
    hardcover_id: int,
    db: Session = Depends(database.get_db)
):
    """Check if a book is available (has files) in Readarr for each format"""
    result = {"ebook": False, "audiobook": False}
    
    # Check ebook server
    ebook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == False
    ).first()
    
    if ebook_server:
        books = await _get_cached_library(ebook_server)
        for book in books:
            foreign_id = book.get("foreignBookId")
            if foreign_id and str(foreign_id) == str(hardcover_id):
                if book.get("statistics", {}).get("bookFileCount", 0) > 0:
                    result["ebook"] = True
                    logger.debug(
                        "ebook_available_in_readarr",
                        hardcover_id=hardcover_id,
                        book_id=book.get("id"),
                        file_count=book.get("statistics", {}).get("bookFileCount", 0),
                    )
                break
    
    # Check audiobook server
    audiobook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == True
    ).first()
    
    if audiobook_server:
        books = await _get_cached_library(audiobook_server)
        for book in books:
            foreign_id = book.get("foreignBookId")
            if foreign_id and str(foreign_id) == str(hardcover_id):
                if book.get("statistics", {}).get("bookFileCount", 0) > 0:
                    result["audiobook"] = True
                    logger.debug(
                        "audiobook_available_in_readarr",
                        hardcover_id=hardcover_id,
                        book_id=book.get("id"),
                        file_count=book.get("statistics", {}).get("bookFileCount", 0),
                    )
                break
    
    logger.info("book_availability_checked",
               hardcover_id=hardcover_id,
               ebook_available=result["ebook"],
               audiobook_available=result["audiobook"])
    
    return result


@router.get("/manage-link/{hardcover_id}")
async def get_readarr_manage_link(
    hardcover_id: int,
    format: Optional[str] = Query(None, description="Optional format: 'ebook' or 'audiobook'"),
    db: Session = Depends(database.get_db),
):
    """Get Readarr UI link for a book if it exists in Readarr."""
    servers: List[models.ReadarrServer] = []
    if format:
        server = get_readarr_server_for_format(format, db)
        if server:
            servers.append(server)
    else:
        ebook_server = get_readarr_server_for_format("ebook", db)
        audiobook_server = get_readarr_server_for_format("audiobook", db)
        if ebook_server:
            servers.append(ebook_server)
        if audiobook_server and audiobook_server != ebook_server:
            servers.append(audiobook_server)

    if servers:
        server = servers[0]
        base_url = build_readarr_url(
            server.hostname,
            server.port,
            server.use_ssl,
            server.url_base,
        )
        return {
            "url": f"{base_url}/book/{hardcover_id}",
            "format": "audiobook" if server.is_audiobook else "ebook",
            "readarr_book_id": hardcover_id,
        }

    return {"url": None, "format": None, "readarr_book_id": None}


@router.post("/availability/batch", response_model=schemas.ReadarrAvailabilityBatchResponse)
async def check_books_availability_batch(
    payload: schemas.ReadarrAvailabilityBatchRequest,
    db: Session = Depends(database.get_db)
):
    """Check availability in Readarr for multiple Hardcover IDs."""
    hardcover_ids = list({int(book_id) for book_id in payload.hardcover_ids if book_id is not None})
    if not hardcover_ids:
        return schemas.ReadarrAvailabilityBatchResponse(results=[])

    result_map = {
        hardcover_id: {"ebook": False, "audiobook": False}
        for hardcover_id in hardcover_ids
    }

    # Ebook server
    ebook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == False
    ).first()
    if ebook_server:
        try:
            books = await _get_cached_library(ebook_server)
            for book in books:
                foreign_id = book.get("foreignBookId")
                if foreign_id is None:
                    continue
                hardcover_id = int(foreign_id)
                if hardcover_id in result_map and book.get("statistics", {}).get("bookFileCount", 0) > 0:
                    result_map[hardcover_id]["ebook"] = True
        except Exception as e:
            logger.warning("readarr_batch_ebook_availability_failed", error=str(e))

    # Audiobook server
    audiobook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == True
    ).first()
    if audiobook_server:
        try:
            books = await _get_cached_library(audiobook_server)
            for book in books:
                foreign_id = book.get("foreignBookId")
                if foreign_id is None:
                    continue
                hardcover_id = int(foreign_id)
                if hardcover_id in result_map and book.get("statistics", {}).get("bookFileCount", 0) > 0:
                    result_map[hardcover_id]["audiobook"] = True
        except Exception as e:
            logger.warning("readarr_batch_audiobook_availability_failed", error=str(e))

    results = [
        schemas.ReadarrAvailabilityItem(
            hardcover_id=hardcover_id,
            ebook=availability["ebook"],
            audiobook=availability["audiobook"]
        )
        for hardcover_id, availability in result_map.items()
    ]
    return schemas.ReadarrAvailabilityBatchResponse(results=results)


@router.get("/{server_id}", response_model=schemas.ReadarrServerResponse)
def get_readarr_server(server_id: int, db: Session = Depends(database.get_db)):
    """Get a specific Readarr server"""
    server = db.query(models.ReadarrServer).filter(models.ReadarrServer.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Readarr server not found"
        )
    return server

@router.post("/", response_model=schemas.ReadarrServerResponse, status_code=status.HTTP_201_CREATED)
def create_readarr_server(
    server: schemas.ReadarrServerCreate,
    db: Session = Depends(database.get_db)
):
    """Create a new Readarr server"""
    # If this is set as default, unset other defaults of the same type
    if server.is_default:
        existing_defaults = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_default == True,
            models.ReadarrServer.is_audiobook == server.is_audiobook
        ).all()
        for existing in existing_defaults:
            existing.is_default = False
    
    db_server = models.ReadarrServer(**server.model_dump())
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

@router.put("/{server_id}", response_model=schemas.ReadarrServerResponse)
def update_readarr_server(
    server_id: int,
    server_update: schemas.ReadarrServerUpdate,
    db: Session = Depends(database.get_db)
):
    """Update a Readarr server"""
    db_server = db.query(models.ReadarrServer).filter(models.ReadarrServer.id == server_id).first()
    if not db_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Readarr server not found"
        )
    
    # Handle default server logic
    if server_update.is_default is True:
        existing_defaults = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_default == True,
            models.ReadarrServer.is_audiobook == (server_update.is_audiobook if server_update.is_audiobook is not None else db_server.is_audiobook),
            models.ReadarrServer.id != server_id
        ).all()
        for existing in existing_defaults:
            existing.is_default = False
    
    # Update fields
    update_data = server_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_server, key, value)
    
    db.commit()
    db.refresh(db_server)
    return db_server

@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_readarr_server(server_id: int, db: Session = Depends(database.get_db)):
    """Delete a Readarr server"""
    db_server = db.query(models.ReadarrServer).filter(models.ReadarrServer.id == server_id).first()
    if not db_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Readarr server not found"
        )
    db.delete(db_server)
    db.commit()
    return None

async def add_book_to_readarr_via_import_list(
    server: models.ReadarrServer,
    book: models.Book,
    format_type: str  # 'ebook' or 'audiobook'
) -> dict:
    """Add book to Readarr via import list (simpler approach)"""
    readarr_client = ReadarrClient.from_server(server, timeout=30.0)
    
    try:
        async with readarr_client.session(timeout=30.0) as client:
            # Get import lists
            import_lists_response = await client.get(f"{api_url}/importList", headers=headers)
            if import_lists_response.status_code != 200:
                raise HTTPException(
                    status_code=import_lists_response.status_code,
                    detail="Could not fetch import lists from Readarr"
                )
            
            import_lists = import_lists_response.json()
            if not import_lists or len(import_lists) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="No import lists configured in Readarr. Please create an import list first."
                )
            
            # Use the first import list (or find a specific one)
            import_list = import_lists[0]
            import_list_id = import_list.get("id")
            
            if not import_list_id:
                raise HTTPException(
                    status_code=400,
                    detail="Import list has no ID"
                )
            
            # Add book to import list using foreignBookId (Hardcover ID)
            # Readarr will process the import list and add the book
            add_payload = {
                "foreignBookId": book.hardcover_id,
                "title": book.title,
                "authorName": book.author,
            }
            
            # Try to add via import list items endpoint
            # Note: Readarr import lists work differently - they sync from external sources
            # We might need to use a different approach
            
            logger.info("readarr_import_list_approach",
                       book_id=book.id,
                       import_list_id=import_list_id,
                       hardcover_id=book.hardcover_id)
            
            # For now, fall back to direct add
            raise HTTPException(
                status_code=501,
                detail="Import list approach not yet implemented. Using direct add instead."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("readarr_import_list_error", error=str(e), book_id=book.id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add book via import list: {str(e)}"
        )

async def add_book_to_readarr(
    server: models.ReadarrServer,
    book: models.Book,
    format_type: str,  # 'ebook' or 'audiobook'
    db: Session,  # Database session for Hardcover API calls
    edition_id: Optional[int] = None,
) -> dict:
    """Add a book to Readarr - simplified to only call Readarr API"""
    readarr_client = ReadarrClient.from_server(server, timeout=30.0)
    readarr_service = ReadarrService(readarr_client, db)
    quality_profile_id, root_folder = readarr_service.get_readarr_settings(server)
    
    try:
        async with readarr_client.session(timeout=30.0) as client:
            author_id, book_data = await readarr_service.determine_author_id(client, book)
            book_data = await readarr_service.ensure_book_data_for_edition(client, book, book_data)
            edition_id = await readarr_service.select_edition_id(
                client,
                book,
                server,
                format_type,
                book_data,
                edition_id_override=edition_id,
            )
            add_payload = readarr_service.build_add_payload(
                book, quality_profile_id, root_folder, edition_id
            )
            readarr_service.validate_add_payload(add_payload, book)
            
            # Log the author ID and edition ID we're using
            logger.info("readarr_using_author_id",
                       author_id=author_id,
                       hardcover_author_id=book.author_id,
                       book_title=book.title,
                       edition_id=edition_id)

            logger.debug(
                "readarr_add_payload",
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
                author_id=author_id,
                any_edition_ok=add_payload.get("anyEditionOk"),
            )
            
            # Check if book already exists in Readarr by foreignBookId
            # We need to verify exact match because Readarr API might return incorrect results
            existing_book = await readarr_service.find_existing_book(client, book)
            
            # If book exists, ensure it's monitored and trigger a search
            if existing_book:
                existing_result = await readarr_service.ensure_existing_book_monitored_and_search(
                    client,
                    existing_book,
                    book,
                    server,
                )
                if existing_result:
                    return existing_result
            
            # Log the full payload before POST request
            logger.debug(
                "readarr_post_payload_full",
                endpoint=f"{readarr_client.api_url}/book",
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
                any_edition_ok=add_payload.get("anyEditionOk"),
            )
            
            response, used_any_edition_retry, used_search_retry, add_payload = (
                await readarr_service.post_add_book_with_retries(
                    client,
                    add_payload,
                    book,
                )
            )
            logger.info("readarr_adding_new_book")
            
            if response.status_code not in [200, 201]:
                # Handle 409 Conflict (book/edition already exists)
                if response.status_code == 409:
                    conflict_result = await readarr_service.resolve_conflict(client, book)
                    if conflict_result:
                        return conflict_result
                
                if response.status_code not in [200, 201]:
                    logger.error("readarr_add_book_failed", 
                                status=response.status_code, 
                                error=response.text, 
                                book_id=book.id,
                                method="POST",
                                used_any_edition_retry=used_any_edition_retry,
                                used_search_retry=used_search_retry)
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to add book to Readarr: {response.text}"
                    )
            
            result = response.json()
            readarr_book_id = result.get("id")
        
        logger.info("readarr_book_added", 
                    book_id=book.id, 
                    readarr_book_id=readarr_book_id,
                    server_id=server.id)
        
        # Trigger search command if searchForNewBook was true in addOptions
        # This ensures the book is searched immediately instead of waiting for author scan
        search_triggered = False
        search_status_code = None
        if add_payload.get("addOptions", {}).get("searchForNewBook"):
            search_triggered, search_status_code = await readarr_service.trigger_search_for_new(
                readarr_book_id,
                book,
            )
        return {
            "success": True,
            "readarr_book_id": readarr_book_id,
            "readarr_received": True,
            "search_triggered": search_triggered,
            "search_status_code": search_status_code,
            "message": "Book added to Readarr"
        }
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Readarr connection timeout"
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to Readarr server"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("readarr_add_book_error", error=str(e), book_id=book.id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add book to Readarr: {str(e)}"
        )

async def _disable_author_monitoring(
    client: httpx.AsyncClient,
    api_url: str,
    headers: dict,
    author_id: int
) -> None:
    """Disable monitoring for an author in Readarr"""
    try:
        author_response = await client.get(
            f"{api_url}/author/{author_id}",
            headers=headers
        )
        
        if author_response.status_code == 200:
            author_data = author_response.json()
            author_data["monitored"] = False
            author_data["monitorNewItems"] = "none"
            
            update_response = await client.put(
                f"{api_url}/author/{author_id}",
                headers=headers,
                json=author_data
            )
            
            if update_response.status_code == 200:
                logger.info("readarr_author_monitoring_disabled", author_id=author_id)
            else:
                logger.warning("readarr_author_update_failed", author_id=author_id, status=update_response.status_code)
    except Exception as e:
        logger.warning("readarr_author_update_error", author_id=author_id, error=str(e))
