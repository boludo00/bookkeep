"""
qBittorrent client implementation.

Provides downloading capabilities for torrent files via qBittorrent Web API.
"""
import time
import hashlib
from typing import Optional, Dict, Any, List
from pathlib import Path
import structlog

try:
    from qbittorrentapi import Client as QBClient
    from qbittorrentapi.exceptions import (
        APIConnectionError,
        LoginFailed,
        Conflict409Error,
        HTTPError,
    )
    HAS_QBITTORRENT = True
except ImportError:
    HAS_QBITTORRENT = False
    QBClient = None
    APIConnectionError = Exception
    LoginFailed = Exception
    Conflict409Error = Exception
    HTTPError = Exception

from ..import DownloadState

logger = structlog.get_logger()


class QBittorrentClient:
    """
    qBittorrent Web API client for torrent downloads.

    Features:
    - Add torrents via URL, magnet, or file
    - Monitor download progress
    - Get completed file paths
    - Category management
    - Path mapping for Docker environments
    """

    def __init__(
        self,
        host: str,
        port: int = 8080,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        category: Optional[str] = None,
        path_mappings: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize qBittorrent client.

        Args:
            host: qBittorrent host (e.g., "localhost", "qbittorrent")
            port: qBittorrent Web UI port (default: 8080)
            username: Web UI username
            password: Web UI password
            use_ssl: Use HTTPS connection
            category: Default category for downloads
            path_mappings: Docker path mappings {"container_path": "host_path"}
        """
        if not HAS_QBITTORRENT:
            raise ImportError(
                "qbittorrent-api package is required. "
                "Install with: pip install qbittorrent-api"
            )

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.category = category
        self.path_mappings = path_mappings or {}

        # Initialize client
        self.client: Optional[QBClient] = None
        self._connect()

    def _connect(self):
        """Establish connection to qBittorrent"""
        try:
            # Build the full URL with protocol
            protocol = "https" if self.use_ssl else "http"
            url = f"{protocol}://{self.host}:{self.port}"

            self.client = QBClient(
                host=url,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False,  # Allow self-signed certs
            )

            # Test connection
            self.client.auth_log_in()

            logger.info(
                "qbittorrent_connected",
                host=self.host,
                port=self.port,
                version=self.client.app.version
            )

        except LoginFailed as e:
            logger.error(
                "qbittorrent_login_failed",
                host=self.host,
                error=str(e)
            )
            raise
        except APIConnectionError as e:
            logger.error(
                "qbittorrent_connection_failed",
                host=self.host,
                port=self.port,
                error=str(e)
            )
            raise

    def test_connection(self) -> bool:
        """
        Test connection to qBittorrent.

        Returns:
            True if connection successful
        """
        try:
            if not self.client:
                self._connect()

            # Try to get app version
            version = self.client.app.version
            logger.info("qbittorrent_test_success", version=version)
            return True

        except Exception as e:
            logger.warning("qbittorrent_test_failed", error=str(e))
            return False

    def add_torrent(
        self,
        url: Optional[str] = None,
        magnet: Optional[str] = None,
        torrent_file: Optional[bytes] = None,
        save_path: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Add a torrent to qBittorrent.

        Args:
            url: Torrent file URL
            magnet: Magnet link
            torrent_file: Torrent file bytes
            save_path: Download save path
            category: Torrent category
            tags: List of tags to apply

        Returns:
            Torrent hash (info_hash) or None if failed
        """
        if not any([url, magnet, torrent_file]):
            raise ValueError("Must provide url, magnet, or torrent_file")

        # Use default category if not specified
        if category is None:
            category = self.category

        try:
            # Prepare add parameters
            add_params = {}
            if save_path:
                add_params['save_path'] = save_path
            if category:
                add_params['category'] = category
                # Ensure category exists
                self._ensure_category(category)
            if tags:
                add_params['tags'] = tags

            # Add torrent
            if url:
                logger.info("qbittorrent_add_url", url=url, category=category)
                result = self.client.torrents_add(urls=url, **add_params)
            elif magnet:
                logger.info("qbittorrent_add_magnet", category=category)
                result = self.client.torrents_add(urls=magnet, **add_params)
            elif torrent_file:
                logger.info("qbittorrent_add_file", category=category)
                result = self.client.torrents_add(torrent_files=torrent_file, **add_params)

            # qBittorrent returns "Ok." on success
            if result != "Ok.":
                logger.warning("qbittorrent_add_unexpected_response", result=result)
                return None

            # Wait a moment for torrent to be added
            time.sleep(0.5)

            # Get the torrent hash (pass tags to enable tag-based lookup)
            info_hash = self._get_torrent_hash(url, magnet, torrent_file, category, tags)

            if info_hash:
                logger.info("qbittorrent_torrent_added", info_hash=info_hash)
            else:
                logger.warning("qbittorrent_torrent_hash_not_found")

            return info_hash

        except Conflict409Error:
            # Torrent already exists
            logger.info("qbittorrent_torrent_exists")
            info_hash = self._get_torrent_hash(url, magnet, torrent_file, category, tags)
            return info_hash

        except Exception as e:
            logger.error("qbittorrent_add_failed", error=str(e))
            return None

    def _ensure_category(self, category: str):
        """Ensure category exists, create if not"""
        try:
            categories = self.client.torrents_categories()
            if category not in categories:
                logger.info("qbittorrent_create_category", category=category)
                self.client.torrents_create_category(name=category)
        except Exception as e:
            logger.warning("qbittorrent_category_error", error=str(e))

    def _get_torrent_hash(
        self,
        url: Optional[str] = None,
        magnet: Optional[str] = None,
        torrent_file: Optional[bytes] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Get torrent hash after adding.

        Tries to find the torrent by various methods, preferring tag-based lookup.
        """
        # If tags provided, look for torrent with matching tag (most reliable method)
        if tags:
            try:
                # Wait a moment for torrent to be fully added
                import time
                time.sleep(1.0)

                # Try each tag
                for tag in tags:
                    torrents = self.client.torrents_info(tag=tag)
                    if torrents and len(torrents) > 0:
                        logger.info("qbittorrent_found_by_tag", tag=tag, hash=torrents[0].hash)
                        return torrents[0].hash
            except Exception as e:
                logger.warning("qbittorrent_tag_lookup_failed", error=str(e))

        # If magnet link, extract hash from it
        if magnet and "btih:" in magnet.lower():
            # Extract hash from magnet link
            # Format: magnet:?xt=urn:btih:HASH&...
            try:
                hash_start = magnet.lower().find("btih:") + 5
                hash_end = magnet.find("&", hash_start)
                if hash_end == -1:
                    info_hash = magnet[hash_start:]
                else:
                    info_hash = magnet[hash_start:hash_end]

                # Validate hash (40 chars for SHA-1)
                if len(info_hash) == 40:
                    return info_hash.lower()
            except Exception:
                pass

        # Try to find by category (most recent)
        # NOTE: This can cause race conditions with concurrent downloads!
        if category:
            try:
                torrents = self.client.torrents_info(category=category, sort='added_on', reverse=True)
                if torrents:
                    logger.warning("qbittorrent_fallback_to_recent", category=category)
                    return torrents[0].hash
            except Exception:
                pass

        # Final fallback: get most recently added torrent
        try:
            torrents = self.client.torrents_info(sort='added_on', reverse=True)
            if torrents:
                logger.warning("qbittorrent_fallback_to_most_recent")
                return torrents[0].hash
        except Exception:
            pass

        return None

    def get_download_status(self, info_hash: str) -> Dict[str, Any]:
        """
        Get download status for a torrent.

        Args:
            info_hash: Torrent hash

        Returns:
            Dict with status information:
            {
                "state": DownloadState,
                "progress": 0.0-100.0,
                "download_speed": bytes/sec,
                "eta": seconds,
                "name": torrent name,
                "save_path": download path,
                "files": list of files,
            }
        """
        try:
            torrent = self.client.torrents_info(torrent_hashes=info_hash)
            if not torrent:
                logger.warning("qbittorrent_torrent_not_found", info_hash=info_hash)
                return {
                    "state": DownloadState.ERROR,
                    "progress": 0.0,
                    "message": "Torrent not found",
                }

            torrent = torrent[0]

            # Map qBittorrent state to DownloadState
            state = self._map_state(torrent.state)

            # Get file list
            files = []
            try:
                torrent_files = self.client.torrents_files(torrent_hash=info_hash)
                for f in torrent_files:
                    files.append({
                        "name": f.name,
                        "size": f.size,
                        "progress": f.progress,
                    })
            except Exception:
                pass

            return {
                "state": state,
                "progress": torrent.progress * 100,  # Convert to percentage
                "download_speed": torrent.dlspeed,
                "upload_speed": torrent.upspeed,
                "eta": torrent.eta,
                "name": torrent.name,
                "save_path": self._map_path_from_container(torrent.save_path),
                "total_size": torrent.size,
                "downloaded": torrent.downloaded,
                "seeders": torrent.num_seeds,
                "peers": torrent.num_leechs,
                "ratio": torrent.ratio,
                "files": files,
                "client_state": torrent.state,  # Raw qBittorrent state
            }

        except Exception as e:
            logger.error("qbittorrent_get_status_failed", info_hash=info_hash, error=str(e))
            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": str(e),
            }

    def _map_state(self, qb_state: str) -> DownloadState:
        """Map qBittorrent state to DownloadState"""
        state_map = {
            # Downloading states
            "downloading": DownloadState.DOWNLOADING,
            "stalledDL": DownloadState.DOWNLOADING,
            "metaDL": DownloadState.DOWNLOADING,
            "forcedDL": DownloadState.DOWNLOADING,
            "allocating": DownloadState.DOWNLOADING,

            # Complete/seeding states
            "uploading": DownloadState.SEEDING,
            "stalledUP": DownloadState.SEEDING,
            "forcedUP": DownloadState.SEEDING,

            # Paused states
            "pausedDL": DownloadState.PAUSED,
            "pausedUP": DownloadState.PAUSED,

            # Checking states
            "checkingDL": DownloadState.CHECKING,
            "checkingUP": DownloadState.CHECKING,
            "checkingResumeData": DownloadState.CHECKING,

            # Error states
            "error": DownloadState.ERROR,
            "missingFiles": DownloadState.ERROR,

            # Queued
            "queuedDL": DownloadState.QUEUED,
            "queuedUP": DownloadState.SEEDING,
        }

        return state_map.get(qb_state, DownloadState.QUEUED)

    def get_completed_download_path(self, info_hash: str) -> Optional[str]:
        """
        Get the path to completed download.

        Args:
            info_hash: Torrent hash

        Returns:
            Path to downloaded file/folder or None
        """
        try:
            torrent = self.client.torrents_info(torrent_hashes=info_hash)
            if not torrent:
                return None

            torrent = torrent[0]

            # Check if complete
            if torrent.progress < 1.0:
                logger.warning(
                    "qbittorrent_download_incomplete",
                    info_hash=info_hash,
                    progress=torrent.progress
                )
                return None

            # Get save path
            save_path = torrent.save_path
            content_path = torrent.content_path

            # Map from container path if needed
            if content_path:
                return self._map_path_from_container(content_path)
            else:
                return self._map_path_from_container(save_path)

        except Exception as e:
            logger.error(
                "qbittorrent_get_path_failed",
                info_hash=info_hash,
                error=str(e)
            )
            return None

    def remove_torrent(
        self,
        info_hash: str,
        delete_files: bool = False
    ) -> bool:
        """
        Remove torrent from qBittorrent.

        Args:
            info_hash: Torrent hash
            delete_files: Also delete downloaded files

        Returns:
            True if removed successfully
        """
        try:
            self.client.torrents_delete(
                delete_files=delete_files,
                torrent_hashes=info_hash
            )
            logger.info(
                "qbittorrent_torrent_removed",
                info_hash=info_hash,
                delete_files=delete_files
            )
            return True

        except Exception as e:
            logger.error(
                "qbittorrent_remove_failed",
                info_hash=info_hash,
                error=str(e)
            )
            return False

    def pause_torrent(self, info_hash: str) -> bool:
        """Pause a torrent"""
        try:
            self.client.torrents_pause(torrent_hashes=info_hash)
            return True
        except Exception as e:
            logger.error("qbittorrent_pause_failed", info_hash=info_hash, error=str(e))
            return False

    def resume_torrent(self, info_hash: str) -> bool:
        """Resume a paused torrent"""
        try:
            self.client.torrents_resume(torrent_hashes=info_hash)
            return True
        except Exception as e:
            logger.error("qbittorrent_resume_failed", info_hash=info_hash, error=str(e))
            return False

    def find_existing_download(
        self,
        info_hash: Optional[str] = None,
        name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find existing download by hash, name, or category.

        Args:
            info_hash: Torrent hash to search for
            name: Torrent name to search for
            category: Category to search in

        Returns:
            Info hash if found, None otherwise
        """
        try:
            # Search by hash (most specific)
            if info_hash:
                torrents = self.client.torrents_info(torrent_hashes=info_hash)
                if torrents:
                    return torrents[0].hash

            # Search by name
            if name:
                filter_params = {}
                if category:
                    filter_params['category'] = category

                torrents = self.client.torrents_info(**filter_params)
                for torrent in torrents:
                    if torrent.name == name:
                        return torrent.hash

            return None

        except Exception as e:
            logger.error("qbittorrent_find_failed", error=str(e))
            return None

    def _map_path_from_container(self, container_path: str) -> str:
        """
        Map path from Docker container to host.

        Args:
            container_path: Path inside container

        Returns:
            Mapped host path
        """
        if not self.path_mappings:
            return container_path

        # Try each mapping
        for container_prefix, host_prefix in self.path_mappings.items():
            if container_path.startswith(container_prefix):
                # Replace container prefix with host prefix
                mapped = container_path.replace(container_prefix, host_prefix, 1)
                logger.debug(
                    "qbittorrent_path_mapped",
                    container=container_path,
                    host=mapped
                )
                return mapped

        # No mapping found, return original
        return container_path

    def _map_path_to_container(self, host_path: str) -> str:
        """
        Map path from host to Docker container.

        Args:
            host_path: Path on host

        Returns:
            Mapped container path
        """
        if not self.path_mappings:
            return host_path

        # Try each mapping (reverse)
        for container_prefix, host_prefix in self.path_mappings.items():
            if host_path.startswith(host_prefix):
                # Replace host prefix with container prefix
                mapped = host_path.replace(host_prefix, container_prefix, 1)
                logger.debug(
                    "qbittorrent_path_mapped",
                    host=host_path,
                    container=mapped
                )
                return mapped

        # No mapping found, return original
        return host_path

    def get_client_info(self) -> Dict[str, Any]:
        """
        Get qBittorrent client information.

        Returns:
            Dict with client info (version, preferences, etc.)
        """
        try:
            return {
                "version": self.client.app.version,
                "api_version": self.client.app.web_api_version,
                "preferences": self.client.app.preferences,
            }
        except Exception as e:
            logger.error("qbittorrent_get_info_failed", error=str(e))
            return {}
