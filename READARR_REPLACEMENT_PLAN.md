# Book Hound: Readarr Replacement Implementation Plan

**Goal**: Replace Readarr dependency with standalone download management inspired by Shelfmark architecture

**Current State**: Book Hound relies on Readarr for:
- Book availability checking
- Search across indexers via Prowlarr
- Download orchestration
- File organization

**Target State**: Self-contained download system with direct Prowlarr + download client integration

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Book Hound Backend                       │
│                                                               │
│  ┌───────────────┐      ┌──────────────┐                    │
│  │ Request Queue │─────▶│ Orchestrator │                    │
│  └───────────────┘      └──────┬───────┘                    │
│                                 │                             │
│                    ┌────────────┼────────────┐               │
│                    │            │            │               │
│              ┌─────▼─────┐ ┌───▼────┐ ┌────▼────┐          │
│              │  Prowlarr │ │ Manual │ │ Future  │          │
│              │   Source  │ │ Upload │ │ Sources │          │
│              └─────┬─────┘ └───┬────┘ └────┬────┘          │
│                    │           │           │                 │
│                    └───────────┼───────────┘                 │
│                                │                              │
│                    ┌───────────▼──────────┐                  │
│                    │  Download Handlers   │                  │
│                    └───────────┬──────────┘                  │
│                                │                              │
│              ┌─────────────────┼─────────────────┐           │
│              │                 │                 │           │
│        ┌─────▼─────┐   ┌──────▼──────┐   ┌─────▼──────┐   │
│        │qBittorrent│   │   NZBGet    │   │  SABnzbd   │   │
│        │  Client   │   │   Client    │   │  Client    │   │
│        └─────┬─────┘   └──────┬──────┘   └─────┬──────┘   │
│              │                 │                 │           │
│              └─────────────────┼─────────────────┘           │
│                                │                              │
│                    ┌───────────▼──────────┐                  │
│                    │  Post-Processor      │                  │
│                    │  - Extract archives  │                  │
│                    │  - Hardlink/copy     │                  │
│                    │  - Organize files    │                  │
│                    └───────────┬──────────┘                  │
│                                │                              │
│                         ┌──────▼──────┐                      │
│                         │   Booklore  │                      │
│                         │  Integration│                      │
│                         └─────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Infrastructure (Week 1-2)

### 1.1 Plugin System Foundation

**Create:** `backend/app/downloads/__init__.py`
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Type
from enum import Enum


class DownloadState(Enum):
    """Download state enumeration"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    ERROR = "error"
    SEEDING = "seeding"
    PAUSED = "paused"
    CHECKING = "checking"


@dataclass
class Release:
    """Unified release structure across all sources"""
    source: str  # "prowlarr", "manual", etc.
    title: str
    url: str
    protocol: str  # "torrent" or "usenet"
    size_bytes: int
    seeders: Optional[int] = None
    indexer: Optional[str] = None
    format: Optional[str] = None  # "epub", "mobi", "m4b", etc.
    language: Optional[str] = None
    metadata: Optional[Dict] = None


@dataclass
class DownloadStatus:
    """Current status of a download"""
    state: DownloadState
    progress: float  # 0.0 to 100.0
    download_speed: Optional[float] = None  # bytes/sec
    eta_seconds: Optional[int] = None
    message: Optional[str] = None


@dataclass
class DownloadTask:
    """Task representing a book download"""
    task_id: str
    book_id: int
    format: str  # "ebook" or "audiobook"
    source: str  # "prowlarr", "manual", etc.
    release_data: Dict  # Source-specific release data
    original_download_path: Optional[str] = None  # For hardlinking


class ReleaseSource(ABC):
    """Abstract base for release sources (Prowlarr, etc.)"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source"""
        pass

    @abstractmethod
    def search(
        self,
        title: str,
        author: Optional[str],
        isbn: Optional[str],
        format_type: str  # "ebook" or "audiobook"
    ) -> List[Release]:
        """Search for releases matching book metadata"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if source is reachable and configured"""
        pass


class DownloadHandler(ABC):
    """Abstract base for download execution"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source this handler supports"""
        pass

    @abstractmethod
    def download(
        self,
        task: DownloadTask,
        cancel_flag,
        progress_callback: Callable[[float], None],
        status_callback: Callable[[DownloadState, str], None]
    ) -> Optional[str]:
        """
        Execute download and return path to downloaded file(s).
        Returns None if download fails or is cancelled.
        """
        pass

    def cleanup(self, task: DownloadTask, success: bool):
        """Optional cleanup after download (e.g., remove from usenet client)"""
        pass


# Plugin registry
_SOURCES: Dict[str, Type[ReleaseSource]] = {}
_HANDLERS: Dict[str, Type[DownloadHandler]] = {}


def register_source(name: str):
    """Decorator to register a release source"""
    def decorator(cls: Type[ReleaseSource]):
        _SOURCES[name] = cls
        return cls
    return decorator


def register_handler(source_name: str):
    """Decorator to register a download handler"""
    def decorator(cls: Type[DownloadHandler]):
        _HANDLERS[source_name] = cls
        return cls
    return decorator


def get_source(name: str) -> ReleaseSource:
    """Get registered source by name"""
    if name not in _SOURCES:
        raise ValueError(f"Unknown source: {name}")
    return _SOURCES[name]()


def get_handler(source_name: str) -> DownloadHandler:
    """Get registered handler by source name"""
    if source_name not in _HANDLERS:
        raise ValueError(f"No handler for source: {source_name}")
    return _HANDLERS[source_name]()


def list_sources() -> List[str]:
    """List all registered sources"""
    return list(_SOURCES.keys())
```

### 1.2 Database Models

**Update:** `backend/app/models.py`
```python
# Add new models for standalone download system

class DownloadTask(Base):
    """Download task tracking"""
    __tablename__ = "download_tasks"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    format = Column(String, nullable=False)  # "ebook" or "audiobook"

    # Release info
    source = Column(String, nullable=False)  # "prowlarr", "manual"
    release_title = Column(String)
    release_url = Column(String)
    protocol = Column(String)  # "torrent" or "usenet"
    indexer = Column(String)
    size_bytes = Column(BigInteger)

    # Download state
    state = Column(String, default="queued")  # queued, downloading, complete, error
    progress = Column(Float, default=0.0)
    download_speed = Column(Float)  # bytes/sec
    eta_seconds = Column(Integer)
    message = Column(String)

    # Paths
    download_path = Column(String)  # Where file was downloaded
    final_path = Column(String)  # Where file ended up after post-processing

    # Client info
    client_type = Column(String)  # "qbittorrent", "nzbget", etc.
    client_download_id = Column(String)  # ID in download client

    # Metadata
    release_data_json = Column(String)  # JSON blob of full release data
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    book = relationship("Book", back_populates="download_tasks")


class DownloadClient(Base):
    """Download client configuration"""
    __tablename__ = "download_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)  # "qbittorrent", "nzbget", "sabnzbd"
    protocol = Column(String, nullable=False)  # "torrent" or "usenet"

    # Connection
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String)
    password = Column(String)  # Should be encrypted

    # Config
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher = preferred
    category = Column(String)  # Category to use in client

    # Path mappings (JSON array of {remote, local} objects)
    path_mappings_json = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)


# Update Book model
Book.download_tasks = relationship("DownloadTask", back_populates="book")
```

### 1.3 Alembic Migration

**Create:** `backend/alembic/versions/021_add_download_system.py`

---

## Phase 2: Prowlarr Integration (Week 2-3)

### 2.1 Prowlarr API Client

**Create:** `backend/app/downloads/prowlarr/api.py`
```python
import requests
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()


class ProwlarrClient:
    """Prowlarr API client"""

    # Category IDs
    CATEGORY_EBOOK = 7000
    CATEGORY_AUDIOBOOK = 3030

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    def test_connection(self) -> bool:
        """Test connection to Prowlarr"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/system/status")
            return response.status_code == 200
        except Exception as e:
            logger.warning("prowlarr_connection_failed", error=str(e))
            return False

    def search(
        self,
        query: str,
        categories: Optional[List[int]] = None,
        indexer_ids: Optional[List[int]] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search Prowlarr for releases.

        Args:
            query: Search query
            categories: Category IDs (7000=ebook, 3030=audiobook)
            indexer_ids: Specific indexers to search
            limit: Max results

        Returns:
            List of release dicts
        """
        params = {
            "query": query,
            "limit": limit
        }

        if categories:
            params["categories"] = ",".join(str(c) for c in categories)

        if indexer_ids:
            params["indexerIds"] = ",".join(str(i) for i in indexer_ids)

        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            results = response.json()

            logger.info(
                "prowlarr_search_complete",
                query=query,
                results=len(results)
            )

            return results

        except Exception as e:
            logger.error(
                "prowlarr_search_failed",
                query=query,
                error=str(e)
            )
            return []

    def get_indexers(self) -> List[Dict]:
        """Get list of configured indexers"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/indexer")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("prowlarr_get_indexers_failed", error=str(e))
            return []
```

### 2.2 Prowlarr Source Implementation

**Create:** `backend/app/downloads/prowlarr/source.py`

(See detailed implementation in next section)

---

## Phase 3: Download Clients (Week 3-5)

### 3.1 Base Download Client

**Create:** `backend/app/downloads/clients/__init__.py`

### 3.2 qBittorrent Client

**Create:** `backend/app/downloads/clients/qbittorrent.py`

**Dependencies:** Add to `requirements.txt`:
```
qbittorrent-api>=2024.1.59
```

### 3.3 NZBGet Client

**Create:** `backend/app/downloads/clients/nzbget.py`

---

## Phase 4: Download Orchestration (Week 5-6)

### 4.1 Task Queue Manager

**Create:** `backend/app/downloads/orchestrator.py`

### 4.2 Download Handler

**Create:** `backend/app/downloads/prowlarr/handler.py`

---

## Phase 5: Post-Processing (Week 6-7)

### 5.1 Archive Extraction

**Dependencies:** Add to `requirements.txt`:
```
rarfile>=4.0
py7zr>=0.20.0
```

**Create:** `backend/app/downloads/postprocess/extract.py`

### 5.2 File Organization

**Create:** `backend/app/downloads/postprocess/organize.py`

---

## Phase 6: API Endpoints (Week 7-8)

### 6.1 New Endpoints

**Create:** `backend/app/routers/downloads.py`

```python
@router.get("/search")
async def search_releases(
    title: str,
    author: Optional[str] = None,
    isbn: Optional[str] = None,
    format_type: str = "ebook",
    db: Session = Depends(database.get_db)
):
    """Search for releases across configured sources"""
    pass

@router.post("/download")
async def start_download(
    book_id: int,
    release_data: Dict,
    format_type: str,
    db: Session = Depends(database.get_db),
    current_user = Depends(get_current_user)
):
    """Start a download task"""
    pass

@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """List download tasks"""
    pass

@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: int,
    db: Session = Depends(database.get_db)
):
    """Get download task status"""
    pass

@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: int,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Cancel a download task"""
    pass

@router.get("/clients")
async def list_clients(db: Session = Depends(database.get_db)):
    """List configured download clients"""
    pass

@router.post("/clients")
async def add_client(
    client_data: Dict,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Add a download client"""
    pass

@router.put("/clients/{client_id}")
async def update_client(
    client_id: int,
    client_data: Dict,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Update a download client"""
    pass

@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: int,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Delete a download client"""
    pass
```

---

## Phase 7: Frontend Integration (Week 8-9)

### 7.1 Download Search Modal

**Create:** `src/components/downloads/SearchModal.tsx`

### 7.2 Download Queue View

**Create:** `src/pages/Downloads.tsx`

### 7.3 Client Management

**Create:** `src/pages/admin/DownloadClients.tsx`

---

## Phase 8: Migration & Testing (Week 9-10)

### 8.1 Readarr Compatibility Layer (Temporary)

Keep Readarr endpoints working during transition:
- Detect if new system is configured
- Fall back to Readarr if not
- Gradual migration path

### 8.2 Testing Checklist

- [ ] Prowlarr search returns results
- [ ] qBittorrent adds torrents correctly
- [ ] Download progress updates
- [ ] Archive extraction works
- [ ] Files organized correctly
- [ ] Booklore integration works
- [ ] Multiple concurrent downloads
- [ ] Cancellation works
- [ ] Error handling
- [ ] Path mappings (Docker)

---

## Benefits Over Readarr

1. **Stability**: No Readarr bugs or abandoned development
2. **Simplicity**: One less service to maintain
3. **Performance**: Direct API calls, no proxy layer
4. **Control**: Full access to download client features
5. **Extensibility**: Easy to add new sources/clients
6. **Debugging**: All code in one place

---

## Migration Path for Users

### Option 1: Fresh Start
1. Configure Prowlarr connection
2. Add download clients (qBittorrent/NZBGet)
3. Disable Readarr
4. Test with new requests

### Option 2: Side-by-Side
1. Keep Readarr enabled
2. Configure new system
3. New requests use new system
4. Old requests stay in Readarr
5. Eventually disable Readarr

---

## Configuration Examples

### Prowlarr Settings
```env
PROWLARR_URL=http://prowlarr:9696
PROWLARR_API_KEY=your_api_key_here
```

### Download Client Settings
```env
# qBittorrent
QBITTORRENT_HOST=qbittorrent
QBITTORRENT_PORT=8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=adminadmin
QBITTORRENT_CATEGORY=books

# NZBGet
NZBGET_HOST=nzbget
NZBGET_PORT=6789
NZBGET_USERNAME=nzbget
NZBGET_PASSWORD=tegbzn6789
NZBGET_CATEGORY=Books
```

### Path Mappings (Docker)
```env
# Format: client:remote_path:local_path
DOWNLOAD_PATH_MAPPINGS=qbittorrent:/downloads:/data/downloads,nzbget:/downloads:/data/downloads
```

---

## Estimated Timeline

**Total: 10 weeks**

- Phase 1: 2 weeks
- Phase 2: 1 week
- Phase 3: 2 weeks
- Phase 4: 1 week
- Phase 5: 1 week
- Phase 6: 1 week
- Phase 7: 1 week
- Phase 8: 1 week

**Parallel work possible:**
- Frontend can start in Phase 6
- Testing throughout all phases

---

## Next Steps

1. Review this plan and adjust timeline
2. Set up development environment with Prowlarr + qBittorrent
3. Start Phase 1: Core infrastructure
4. Create feature branch: `feature/standalone-downloads`
5. Incremental commits with testing at each phase

