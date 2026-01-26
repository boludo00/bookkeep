"""
Download system for Book Hound - Replaces Readarr dependency.

This module provides a plugin-based architecture for searching and downloading books
from various sources (Prowlarr, direct downloads, etc.) using multiple download clients
(qBittorrent, NZBGet, SABnzbd, etc.).

Architecture inspired by Shelfmark: https://github.com/advplyr/shelfmark
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Type, Any
from enum import Enum
from datetime import datetime


class DownloadState(Enum):
    """Download state enumeration"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    ERROR = "error"
    SEEDING = "seeding"
    PAUSED = "paused"
    CHECKING = "checking"
    PROCESSING = "processing"  # Post-processing (extracting, organizing)


@dataclass
class Release:
    """
    Unified release structure across all sources.

    This represents a single downloadable release (torrent or NZB)
    that was found by searching a source.
    """
    source: str  # "prowlarr", "manual", etc.
    title: str
    download_url: str
    protocol: str  # "torrent" or "usenet"
    size_bytes: int

    # Optional metadata
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    indexer: Optional[str] = None
    indexer_id: Optional[int] = None
    category: Optional[str] = None

    # Extracted metadata
    format: Optional[str] = None  # "epub", "mobi", "m4b", "mp3", etc.
    language: Optional[str] = None  # ISO 639-1 code

    # Quality indicators
    quality_score: float = 0.0  # 0-100, higher is better

    # Raw data from source
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Publishing info
    publish_date: Optional[datetime] = None

    # Link to indexer page with more info
    info_url: Optional[str] = None


@dataclass
class DownloadStatus:
    """Current status of a download"""
    state: DownloadState
    progress: float  # 0.0 to 100.0
    download_speed: Optional[float] = None  # bytes/sec
    upload_speed: Optional[float] = None  # bytes/sec (for torrents)
    eta_seconds: Optional[int] = None
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    message: Optional[str] = None
    client_state: Optional[str] = None  # Raw state from client (e.g., "stalledDL")

    @property
    def complete(self) -> bool:
        """Check if download is complete"""
        return self.state in (DownloadState.COMPLETE, DownloadState.SEEDING)


@dataclass
class DownloadTask:
    """
    Task representing a book download.

    This is the internal representation used by the orchestrator
    and handlers. It maps to the DownloadTask database model.
    """
    task_id: str
    book_id: int
    format: str  # "ebook" or "audiobook"
    source: str  # "prowlarr", "manual", etc.

    # Release information
    release: Release

    # Paths (set during/after download)
    download_path: Optional[str] = None  # Where download client puts files
    original_download_path: Optional[str] = None  # For hardlinking (torrents)
    final_path: Optional[str] = None  # Final organized location

    # Client tracking
    client_type: Optional[str] = None  # "qbittorrent", "nzbget", etc.
    client_download_id: Optional[str] = None  # ID in download client

    # Metadata
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class ReleaseSource(ABC):
    """
    Abstract base for release sources (Prowlarr, manual uploads, etc.).

    Sources are responsible for searching for book releases.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source"""
        pass

    @abstractmethod
    def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"  # "ebook" or "audiobook"
    ) -> List[Release]:
        """
        Search for releases matching book metadata.

        Args:
            title: Book title
            author: Book author (optional)
            isbn: ISBN-10 or ISBN-13 (optional)
            format_type: "ebook" or "audiobook"

        Returns:
            List of Release objects
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if source is reachable and configured properly.

        Returns:
            True if connection succeeds, False otherwise
        """
        pass


class DownloadHandler(ABC):
    """
    Abstract base for download execution.

    Handlers are responsible for:
    1. Adding downloads to clients (qBittorrent, NZBGet, etc.)
    2. Polling for progress
    3. Retrieving completed files
    4. Cleanup
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source this handler supports"""
        pass

    @abstractmethod
    def download(
        self,
        task: DownloadTask,
        cancel_flag,  # threading.Event or similar
        progress_callback: Callable[[float], None],
        status_callback: Callable[[DownloadState, str], None]
    ) -> Optional[str]:
        """
        Execute download and return path to downloaded file(s).

        This method should:
        1. Add download to appropriate client
        2. Poll for progress (calling callbacks)
        3. Wait for completion
        4. Return path to downloaded files

        Args:
            task: DownloadTask with all metadata
            cancel_flag: Event to check for cancellation
            progress_callback: Call with progress 0.0-100.0
            status_callback: Call with (state, message) updates

        Returns:
            Path to downloaded file/directory, or None if failed/cancelled
        """
        pass

    def cleanup(self, task: DownloadTask, success: bool):
        """
        Optional cleanup after download completes or fails.

        For example, usenet clients may want to remove completed downloads
        to save space, while torrent clients may want to keep seeding.

        Args:
            task: DownloadTask that was processed
            success: True if download succeeded, False otherwise
        """
        pass


# Plugin registry
_SOURCES: Dict[str, Type[ReleaseSource]] = {}
_HANDLERS: Dict[str, Type[DownloadHandler]] = {}


def register_source(name: str):
    """
    Decorator to register a release source.

    Usage:
        @register_source("prowlarr")
        class ProwlarrSource(ReleaseSource):
            ...
    """
    def decorator(cls: Type[ReleaseSource]):
        _SOURCES[name] = cls
        return cls
    return decorator


def register_handler(source_name: str):
    """
    Decorator to register a download handler.

    Usage:
        @register_handler("prowlarr")
        class ProwlarrHandler(DownloadHandler):
            ...
    """
    def decorator(cls: Type[DownloadHandler]):
        _HANDLERS[source_name] = cls
        return cls
    return decorator


def get_source(name: str, db_session=None) -> ReleaseSource:
    """
    Get registered source by name, loading configuration from database.

    Args:
        name: Source name (e.g., "prowlarr")
        db_session: Optional database session (creates new if not provided)

    Returns:
        Instantiated ReleaseSource configured from database

    Raises:
        ValueError: If source not found
    """
    if name not in _SOURCES:
        available = ", ".join(_SOURCES.keys())
        raise ValueError(f"Unknown source: {name}. Available: {available}")

    # Load configuration from database for prowlarr
    if name == "prowlarr":
        from ..database import SessionLocal
        from ..models import ProwlarrServer
        import json

        db = db_session or SessionLocal()
        try:
            prowlarr_server = db.query(ProwlarrServer).filter(
                ProwlarrServer.enabled == True
            ).first()

            if prowlarr_server:
                # Build URL from database config
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

                return _SOURCES[name](
                    base_url=base_url,
                    api_key=prowlarr_server.api_key,
                    indexer_ids=indexer_ids
                )
        finally:
            if not db_session:
                db.close()

    # Default instantiation for other sources
    return _SOURCES[name]()


def get_handler(source_name: str) -> Type[DownloadHandler]:
    """
    Get registered handler class by source name.

    Args:
        source_name: Source name (e.g., "torrent", "usenet")

    Returns:
        DownloadHandler class (not instantiated)

    Raises:
        ValueError: If handler not found
    """
    if source_name not in _HANDLERS:
        available = ", ".join(_HANDLERS.keys())
        raise ValueError(f"No handler for source: {source_name}. Available: {available}")
    return _HANDLERS[source_name]


def list_sources() -> List[str]:
    """List all registered sources"""
    return list(_SOURCES.keys())


def list_handlers() -> List[str]:
    """List all registered handlers"""
    return list(_HANDLERS.keys())


# Import plugins to register them
# This ensures all plugins are loaded when the module is imported
try:
    from .prowlarr import source as _prowlarr_source  # noqa: F401
except ImportError as e:
    import structlog
    logger = structlog.get_logger()
    logger.warning("prowlarr_import_failed", error=str(e))
    pass  # Prowlarr dependencies may not be installed

try:
    from .handlers import torrent as _torrent_handler  # noqa: F401
    from .handlers import usenet as _usenet_handler  # noqa: F401
except ImportError as e:
    import structlog
    logger = structlog.get_logger()
    logger.warning("handlers_import_failed", error=str(e))
    pass  # Handler dependencies may not be installed

# Export orchestrator
from .orchestrator import DownloadOrchestrator  # noqa: F401

__all__ = [
    "DownloadState",
    "Release",
    "DownloadStatus",
    "DownloadTask",
    "ReleaseSource",
    "DownloadHandler",
    "register_source",
    "register_handler",
    "get_source",
    "get_handler",
    "list_sources",
    "list_handlers",
    "DownloadOrchestrator",
]
