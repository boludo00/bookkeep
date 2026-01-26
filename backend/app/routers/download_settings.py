"""
API router for download system settings (Prowlarr and Download Clients).

Replaces Readarr configuration with standalone download system configuration.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import structlog
import json

from ..database import get_db
from ..models import ProwlarrServer, DownloadClient
from ..downloads.prowlarr import ProwlarrClient
from ..downloads.clients import QBittorrentClient, NZBGetClient, SabnzbdClient

router = APIRouter()
logger = structlog.get_logger()


# Pydantic models
class ProwlarrServerCreate(BaseModel):
    name: str
    host: str
    port: int = 9696
    use_ssl: bool = False
    api_key: str
    url_base: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    indexer_ids: Optional[List[int]] = None  # List of allowed indexer IDs


class ProwlarrServerUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    use_ssl: Optional[bool] = None
    api_key: Optional[str] = None
    url_base: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    indexer_ids: Optional[List[int]] = None  # List of allowed indexer IDs


class ProwlarrServerResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    use_ssl: bool
    api_key: str
    url_base: Optional[str]
    enabled: bool
    is_default: bool
    indexer_ids: Optional[List[int]] = None  # List of allowed indexer IDs

    class Config:
        from_attributes = True


class ProwlarrTestRequest(BaseModel):
    host: str
    port: int
    use_ssl: bool
    api_key: str
    url_base: Optional[str] = None


class DownloadClientCreate(BaseModel):
    name: str
    type: str  # "qbittorrent", "nzbget", "sabnzbd"
    protocol: str  # "torrent", "usenet"
    host: str
    port: int
    use_ssl: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    category: Optional[str] = None
    ebook_category: Optional[str] = None
    audiobook_category: Optional[str] = None
    path_mappings_json: Optional[str] = None


class DownloadClientUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    protocol: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    use_ssl: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    ebook_category: Optional[str] = None
    audiobook_category: Optional[str] = None
    path_mappings_json: Optional[str] = None


class DownloadClientResponse(BaseModel):
    id: int
    name: str
    type: str
    protocol: str
    host: str
    port: int
    use_ssl: bool
    username: Optional[str]
    password: str  # Will be masked in response
    api_key: Optional[str] = None  # Will be masked in response
    enabled: bool
    priority: int
    category: Optional[str]
    ebook_category: Optional[str]
    audiobook_category: Optional[str]
    path_mappings_json: Optional[str]

    class Config:
        from_attributes = True


class DownloadClientTestRequest(BaseModel):
    type: str
    protocol: str
    host: str
    port: int
    use_ssl: bool
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None


# Prowlarr endpoints
@router.get("/prowlarr", response_model=List[ProwlarrServerResponse])
def get_prowlarr_servers(db: Session = Depends(get_db)):
    """Get all Prowlarr servers"""
    servers = db.query(ProwlarrServer).all()

    # Convert to response with parsed indexer_ids
    responses = []
    for server in servers:
        responses.append(ProwlarrServerResponse(
            id=server.id,
            name=server.name,
            host=server.host,
            port=server.port,
            use_ssl=server.use_ssl,
            api_key=server.api_key,
            url_base=server.url_base,
            enabled=server.enabled,
            is_default=server.is_default,
            indexer_ids=_parse_indexer_ids(server.indexer_ids_json)
        ))
    return responses


def _parse_indexer_ids(indexer_ids_json: Optional[str]) -> Optional[List[int]]:
    """Parse indexer IDs from JSON string"""
    if not indexer_ids_json:
        return None
    try:
        ids = json.loads(indexer_ids_json)
        return ids if ids else None
    except (json.JSONDecodeError, TypeError):
        return None


def _serialize_indexer_ids(indexer_ids: Optional[List[int]]) -> Optional[str]:
    """Serialize indexer IDs to JSON string"""
    if not indexer_ids:
        return None
    return json.dumps(indexer_ids)


@router.post("/prowlarr", response_model=ProwlarrServerResponse)
def create_prowlarr_server(
    server: ProwlarrServerCreate,
    db: Session = Depends(get_db)
):
    """Create a new Prowlarr server"""
    # Check if name exists
    existing = db.query(ProwlarrServer).filter(
        ProwlarrServer.name == server.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Server name already exists")

    # If this is set as default, unset other defaults
    if server.is_default:
        db.query(ProwlarrServer).update({"is_default": False})

    # Convert indexer_ids list to JSON
    server_data = server.model_dump(exclude={"indexer_ids"})
    server_data["indexer_ids_json"] = _serialize_indexer_ids(server.indexer_ids)

    # Create server
    db_server = ProwlarrServer(**server_data)
    db.add(db_server)
    db.commit()
    db.refresh(db_server)

    logger.info("prowlarr_server_created", server_id=db_server.id, name=db_server.name)

    # Convert response to include parsed indexer_ids
    response = ProwlarrServerResponse(
        id=db_server.id,
        name=db_server.name,
        host=db_server.host,
        port=db_server.port,
        use_ssl=db_server.use_ssl,
        api_key=db_server.api_key,
        url_base=db_server.url_base,
        enabled=db_server.enabled,
        is_default=db_server.is_default,
        indexer_ids=_parse_indexer_ids(db_server.indexer_ids_json)
    )
    return response


@router.put("/prowlarr/{server_id}", response_model=ProwlarrServerResponse)
def update_prowlarr_server(
    server_id: int,
    server: ProwlarrServerUpdate,
    db: Session = Depends(get_db)
):
    """Update a Prowlarr server"""
    db_server = db.query(ProwlarrServer).filter(ProwlarrServer.id == server_id).first()
    if not db_server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Check name uniqueness if changing
    if server.name and server.name != db_server.name:
        existing = db.query(ProwlarrServer).filter(
            ProwlarrServer.name == server.name
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Server name already exists")

    # If setting as default, unset other defaults
    if server.is_default:
        db.query(ProwlarrServer).update({"is_default": False})

    # Update fields, handling indexer_ids specially
    update_data = server.model_dump(exclude_unset=True)
    if "indexer_ids" in update_data:
        db_server.indexer_ids_json = _serialize_indexer_ids(update_data.pop("indexer_ids"))

    for key, value in update_data.items():
        setattr(db_server, key, value)

    db.commit()
    db.refresh(db_server)

    logger.info("prowlarr_server_updated", server_id=db_server.id)

    # Convert response to include parsed indexer_ids
    response = ProwlarrServerResponse(
        id=db_server.id,
        name=db_server.name,
        host=db_server.host,
        port=db_server.port,
        use_ssl=db_server.use_ssl,
        api_key=db_server.api_key,
        url_base=db_server.url_base,
        enabled=db_server.enabled,
        is_default=db_server.is_default,
        indexer_ids=_parse_indexer_ids(db_server.indexer_ids_json)
    )
    return response


@router.delete("/prowlarr/{server_id}")
def delete_prowlarr_server(server_id: int, db: Session = Depends(get_db)):
    """Delete a Prowlarr server"""
    db_server = db.query(ProwlarrServer).filter(ProwlarrServer.id == server_id).first()
    if not db_server:
        raise HTTPException(status_code=404, detail="Server not found")

    db.delete(db_server)
    db.commit()

    logger.info("prowlarr_server_deleted", server_id=server_id)
    return {"message": "Server deleted"}


@router.post("/prowlarr/test")
def test_prowlarr_connection(request: ProwlarrTestRequest):
    """Test Prowlarr connection"""
    try:
        # Build URL
        protocol = "https" if request.use_ssl else "http"
        base_url = f"{protocol}://{request.host}:{request.port}"
        if request.url_base:
            base_url += f"/{request.url_base}"

        # Create client and test
        client = ProwlarrClient(base_url, request.api_key)

        if not client.test_connection():
            return {
                "success": False,
                "error": "Connection failed - could not reach Prowlarr"
            }

        # Get indexers to show success
        indexers = client.get_indexers()

        return {
            "success": True,
            "indexers": indexers[:10],  # Return first 10
            "total_indexers": len(indexers)
        }

    except Exception as e:
        logger.error("prowlarr_test_failed", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/prowlarr/{server_id}/indexers")
def get_prowlarr_indexers(server_id: int, db: Session = Depends(get_db)):
    """Get available indexers from a Prowlarr server"""
    db_server = db.query(ProwlarrServer).filter(ProwlarrServer.id == server_id).first()
    if not db_server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        # Build URL
        protocol = "https" if db_server.use_ssl else "http"
        base_url = f"{protocol}://{db_server.host}:{db_server.port}"
        if db_server.url_base:
            base_url += f"/{db_server.url_base.strip('/')}"

        # Create client and get indexers
        client = ProwlarrClient(base_url, db_server.api_key)
        indexers = client.get_indexers()

        # Return simplified indexer info
        return {
            "indexers": [
                {
                    "id": idx.get("id"),
                    "name": idx.get("name"),
                    "protocol": idx.get("protocol"),
                    "privacy": idx.get("privacy"),
                    "enabled": idx.get("enable", True),
                }
                for idx in indexers
            ]
        }

    except Exception as e:
        logger.error("prowlarr_get_indexers_failed", server_id=server_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get indexers: {str(e)}")


# Download Client endpoints
@router.get("/download-clients", response_model=List[DownloadClientResponse])
def get_download_clients(db: Session = Depends(get_db)):
    """Get all download clients"""
    clients = db.query(DownloadClient).order_by(DownloadClient.priority.desc()).all()

    # Mask passwords and API keys
    for client in clients:
        if client.password:
            client.password = "***MASKED***"
        if client.api_key:
            client.api_key = "***MASKED***"

    return clients


@router.post("/download-clients", response_model=DownloadClientResponse)
def create_download_client(
    client: DownloadClientCreate,
    db: Session = Depends(get_db)
):
    """Create a new download client"""
    # Check if name exists
    existing = db.query(DownloadClient).filter(
        DownloadClient.name == client.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Client name already exists")

    # Create client
    db_client = DownloadClient(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    logger.info("download_client_created", client_id=db_client.id, name=db_client.name)

    # Mask password and API key in response
    if db_client.password:
        db_client.password = "***MASKED***"
    if db_client.api_key:
        db_client.api_key = "***MASKED***"

    return db_client


@router.put("/download-clients/{client_id}", response_model=DownloadClientResponse)
def update_download_client(
    client_id: int,
    client: DownloadClientUpdate,
    db: Session = Depends(get_db)
):
    """Update a download client"""
    db_client = db.query(DownloadClient).filter(DownloadClient.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check name uniqueness if changing
    if client.name and client.name != db_client.name:
        existing = db.query(DownloadClient).filter(
            DownloadClient.name == client.name
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Client name already exists")

    # Update fields (skip password/api_key if not provided or empty)
    update_data = client.model_dump(exclude_unset=True)
    if "password" in update_data and not update_data["password"]:
        del update_data["password"]
    if "api_key" in update_data and not update_data["api_key"]:
        del update_data["api_key"]

    for key, value in update_data.items():
        setattr(db_client, key, value)

    db.commit()
    db.refresh(db_client)

    logger.info("download_client_updated", client_id=db_client.id)

    # Mask password and API key in response
    if db_client.password:
        db_client.password = "***MASKED***"
    if db_client.api_key:
        db_client.api_key = "***MASKED***"

    return db_client


@router.delete("/download-clients/{client_id}")
def delete_download_client(client_id: int, db: Session = Depends(get_db)):
    """Delete a download client"""
    db_client = db.query(DownloadClient).filter(DownloadClient.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    db.delete(db_client)
    db.commit()

    logger.info("download_client_deleted", client_id=client_id)
    return {"message": "Client deleted"}


@router.post("/download-clients/test")
def test_download_client(request: DownloadClientTestRequest):
    """Test download client connection"""
    try:
        if request.protocol == "torrent":
            if request.type == "qbittorrent":
                client = QBittorrentClient(
                    host=request.host,
                    port=request.port,
                    username=request.username,
                    password=request.password,
                    use_ssl=request.use_ssl
                )

                if not client.test_connection():
                    return {
                        "success": False,
                        "error": "Connection failed - could not reach qBittorrent"
                    }

                # Get client info
                info = client.get_client_info()

                return {
                    "success": True,
                    "version": info.get("version"),
                    "api_version": info.get("api_version")
                }
            else:
                return {
                    "success": False,
                    "error": f"Unsupported torrent client: {request.type}"
                }

        elif request.protocol == "usenet":
            if request.type == "nzbget":
                client = NZBGetClient(
                    host=request.host,
                    port=request.port,
                    username=request.username,
                    password=request.password,
                    use_ssl=request.use_ssl
                )

                if not client.test_connection():
                    return {
                        "success": False,
                        "error": "Connection failed - could not reach NZBGet"
                    }

                # Get client info
                info = client.get_client_info()

                return {
                    "success": True,
                    "version": info.get("version")
                }
            elif request.type == "sabnzbd":
                client = SabnzbdClient(
                    host=request.host,
                    port=request.port,
                    api_key=request.api_key,
                    use_ssl=request.use_ssl
                )

                if not client.test_connection():
                    return {
                        "success": False,
                        "error": "Connection failed - could not reach Sabnzbd"
                    }

                # Get client info
                info = client.get_client_info()

                return {
                    "success": True,
                    "version": info.get("version")
                }
            else:
                return {
                    "success": False,
                    "error": f"Unsupported usenet client: {request.type}"
                }

        else:
            return {
                "success": False,
                "error": f"Unsupported protocol: {request.protocol}"
            }

    except Exception as e:
        logger.error("download_client_test_failed", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }
