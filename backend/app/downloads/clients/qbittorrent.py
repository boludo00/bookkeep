"""
qBittorrent client implementation.

Provides downloading capabilities for torrent files via qBittorrent Web API.
"""
import time
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import structlog
import requests

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


def _bdecode(data: bytes, index: int = 0) -> Tuple[Any, int]:
    """
    Decode bencoded data.

    Args:
        data: Bencoded bytes
        index: Starting index

    Returns:
        Tuple of (decoded value, next index)
    """
    if data[index:index+1] == b'i':
        # Integer: i<number>e
        end = data.index(b'e', index)
        return int(data[index+1:end]), end + 1
    elif data[index:index+1] == b'l':
        # List: l<items>e
        index += 1
        result = []
        while data[index:index+1] != b'e':
            item, index = _bdecode(data, index)
            result.append(item)
        return result, index + 1
    elif data[index:index+1] == b'd':
        # Dictionary: d<key><value>...e
        index += 1
        result = {}
        while data[index:index+1] != b'e':
            key, index = _bdecode(data, index)
            if isinstance(key, bytes):
                key = key.decode('utf-8', errors='replace')
            value, index = _bdecode(data, index)
            result[key] = value
        return result, index + 1
    elif data[index:index+1].isdigit():
        # String: <length>:<content>
        colon = data.index(b':', index)
        length = int(data[index:colon])
        start = colon + 1
        return data[start:start+length], start + length
    else:
        raise ValueError(f"Invalid bencode at index {index}: {data[index:index+10]}")


def _bencode(data: Any) -> bytes:
    """
    Encode data to bencode format.

    Args:
        data: Data to encode (dict, list, int, bytes, or str)

    Returns:
        Bencoded bytes
    """
    if isinstance(data, int):
        return f"i{data}e".encode()
    elif isinstance(data, bytes):
        return f"{len(data)}:".encode() + data
    elif isinstance(data, str):
        encoded = data.encode('utf-8')
        return f"{len(encoded)}:".encode() + encoded
    elif isinstance(data, list):
        return b'l' + b''.join(_bencode(item) for item in data) + b'e'
    elif isinstance(data, dict):
        # Keys must be sorted
        result = b'd'
        for key in sorted(data.keys()):
            if isinstance(key, str):
                key_bytes = key.encode('utf-8')
            else:
                key_bytes = key
            result += f"{len(key_bytes)}:".encode() + key_bytes
            result += _bencode(data[key])
        result += b'e'
        return result
    else:
        raise ValueError(f"Cannot bencode type: {type(data)}")


def extract_info_hash_from_torrent(torrent_data: bytes) -> Optional[str]:
    """
    Extract info_hash from torrent file bytes.

    The info_hash is the SHA1 hash of the bencoded 'info' dictionary.

    Args:
        torrent_data: Raw torrent file bytes

    Returns:
        40-character lowercase hex hash, or None if extraction fails
    """
    try:
        decoded, _ = _bdecode(torrent_data)
        if not isinstance(decoded, dict) or 'info' not in decoded:
            logger.warning("torrent_missing_info_dict")
            return None

        # Re-encode the info dict and hash it
        info_dict = decoded['info']
        info_bencoded = _bencode(info_dict)
        info_hash = hashlib.sha1(info_bencoded).hexdigest().lower()

        logger.debug("torrent_info_hash_extracted", hash=info_hash)
        return info_hash

    except Exception as e:
        logger.warning("torrent_hash_extraction_failed", error=str(e))
        return None


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
        url_base: Optional[str] = None,
        category: Optional[str] = None,
        ebook_category: Optional[str] = None,
        audiobook_category: Optional[str] = None,
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
            url_base: URL base path for reverse proxy (e.g., "/qbittorrent")
            category: Default/fallback category for downloads
            ebook_category: Category for ebook downloads (falls back to category)
            audiobook_category: Category for audiobook downloads (falls back to category)
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
        self.url_base = url_base
        self.category = category
        self.ebook_category = ebook_category
        self.audiobook_category = audiobook_category
        self.path_mappings = path_mappings or {}

        # Initialize client
        self.client: Optional[QBClient] = None
        self._connect()

    def get_category_for_format(self, format_type: Optional[str] = None) -> Optional[str]:
        """
        Get the appropriate category based on download format.

        Args:
            format_type: "ebook", "audiobook", or None

        Returns:
            The format-specific category, or the default category as fallback
        """
        if format_type == "ebook" and self.ebook_category:
            return self.ebook_category
        elif format_type == "audiobook" and self.audiobook_category:
            return self.audiobook_category
        return self.category

    def _connect(self):
        """Establish connection to qBittorrent"""
        try:
            # Build the full URL with protocol
            protocol = "https" if self.use_ssl else "http"
            url = f"{protocol}://{self.host}:{self.port}"
            if self.url_base:
                url = f"{url}/{self.url_base.strip('/')}"

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

    def _download_torrent_file(self, url: str, timeout: int = 30) -> Optional[bytes]:
        """
        Download a .torrent file from a URL.

        Args:
            url: URL to the torrent file (e.g., Prowlarr download URL)
            timeout: Request timeout in seconds

        Returns:
            Torrent file bytes, or None if download fails
        """
        try:
            logger.info("downloading_torrent_file", url=url[:100])

            response = requests.get(
                url,
                timeout=timeout,
                headers={
                    'User-Agent': 'Bookkeep/1.0',
                    'Accept': 'application/x-bittorrent, */*',
                },
                allow_redirects=True,
            )
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            content = response.content

            # Verify this looks like a torrent file (starts with 'd' for bencoded dict)
            if not content or content[0:1] != b'd':
                logger.warning(
                    "torrent_file_invalid_content",
                    content_type=content_type,
                    first_bytes=content[:20] if content else None
                )
                return None

            logger.info(
                "torrent_file_downloaded",
                size=len(content),
                content_type=content_type
            )
            return content

        except requests.RequestException as e:
            logger.error("torrent_file_download_failed", url=url[:100], error=str(e))
            return None
        except Exception as e:
            logger.error("torrent_file_download_error", url=url[:100], error=str(e))
            return None

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

        This method extracts the info_hash BEFORE adding the torrent to qBittorrent,
        following the approach used by Readarr/Sonarr. This ensures reliable tracking
        of torrents without relying on tag-based lookups.

        For URL downloads:
        1. Download the .torrent file
        2. Extract info_hash from the file
        3. Add torrent file bytes to qBittorrent
        4. Verify torrent appears with known hash

        For magnet links:
        1. Extract info_hash from magnet link
        2. Add magnet to qBittorrent
        3. Verify torrent appears with known hash

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

        # --- Phase 1: Extract hash BEFORE adding ---
        info_hash = None
        torrent_data = torrent_file  # May be provided directly

        if magnet:
            # Extract hash from magnet link
            info_hash = self._extract_hash_from_magnet(magnet)
            if info_hash:
                logger.info("qbittorrent_hash_from_magnet", hash=info_hash)
            else:
                logger.warning("qbittorrent_magnet_hash_extraction_failed")

        elif url:
            # Download the .torrent file and extract hash
            torrent_data = self._download_torrent_file(url)
            if torrent_data:
                info_hash = extract_info_hash_from_torrent(torrent_data)
                if info_hash:
                    logger.info("qbittorrent_hash_from_torrent_file", hash=info_hash, url=url[:100])
                else:
                    logger.warning("qbittorrent_torrent_file_hash_extraction_failed", url=url[:100])
            else:
                logger.error("qbittorrent_torrent_file_download_failed", url=url[:100])
                # Fall back to passing URL directly to qBittorrent (legacy behavior)
                logger.info("qbittorrent_falling_back_to_url_add", url=url[:100])

        elif torrent_file:
            # Extract hash from provided torrent file bytes
            info_hash = extract_info_hash_from_torrent(torrent_file)
            if info_hash:
                logger.info("qbittorrent_hash_from_torrent_bytes", hash=info_hash)
            else:
                logger.warning("qbittorrent_torrent_bytes_hash_extraction_failed")

        # --- Phase 2: Add torrent to qBittorrent ---
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

            # Add torrent - prefer torrent file bytes over URL when available
            if magnet:
                logger.info("qbittorrent_add_magnet", category=category, hash=info_hash)
                result = self.client.torrents_add(urls=magnet, **add_params)
            elif torrent_data:
                # We have torrent file bytes (either downloaded or provided)
                logger.info("qbittorrent_add_file", category=category, hash=info_hash)
                result = self.client.torrents_add(torrent_files=torrent_data, **add_params)
            elif url:
                # Fallback: pass URL directly (less reliable for tracking)
                logger.info("qbittorrent_add_url", url=url[:100], category=category)
                result = self.client.torrents_add(urls=url, **add_params)
            else:
                logger.error("qbittorrent_no_torrent_source")
                return None

            # Older qBittorrent/qbittorrent-api versions return the plain
            # string "Ok." on success. Newer qBittorrent servers (5.1+, this
            # instance runs 5.2.3) return a structured TorrentsAddedMetadata
            # object instead - checking only for the literal string silently
            # treated every genuine success as a failure once the server was
            # upgraded.
            if result == "Ok.":
                pass  # legacy success response
            elif hasattr(result, "success_count"):
                added_ok = (getattr(result, "success_count", 0) or 0) > 0
                if info_hash and getattr(result, "added_torrent_ids", None):
                    added_ok = added_ok or info_hash in result.added_torrent_ids
                if not added_ok:
                    logger.warning("qbittorrent_add_unexpected_response", result=result)
                    return None
            else:
                logger.warning("qbittorrent_add_unexpected_response", result=result)
                return None

            # --- Phase 3: Verify torrent was added ---
            if info_hash:
                # We know the hash - verify it appears in qBittorrent
                if self._wait_for_torrent(info_hash):
                    logger.info("qbittorrent_torrent_added", info_hash=info_hash)
                    return info_hash
                else:
                    # Torrent may still have been added, return the hash anyway
                    # (following Readarr's optimistic approach)
                    logger.warning(
                        "qbittorrent_torrent_not_verified",
                        info_hash=info_hash,
                        message="Torrent may have been added but could not be verified"
                    )
                    return info_hash
            else:
                # No hash available - fall back to tag-based lookup (legacy)
                logger.warning("qbittorrent_no_precomputed_hash_falling_back_to_tags")
                time.sleep(0.5)
                info_hash = self._get_torrent_hash(url, magnet, torrent_file, category, tags)
                if info_hash:
                    logger.info("qbittorrent_torrent_added", info_hash=info_hash)
                else:
                    logger.warning("qbittorrent_torrent_hash_not_found")
                return info_hash

        except Conflict409Error:
            # Torrent already exists
            logger.info("qbittorrent_torrent_exists", info_hash=info_hash)
            if info_hash:
                return info_hash
            # Fall back to tag-based lookup
            return self._get_torrent_hash(url, magnet, torrent_file, category, tags)

        except Exception as e:
            logger.error("qbittorrent_add_failed", error=str(e))
            return None

    def _wait_for_torrent(self, info_hash: str, max_attempts: int = 10, delay: float = 0.1) -> bool:
        """
        Wait for a torrent to appear in qBittorrent.

        This follows the Readarr/Sonarr pattern of polling for the torrent
        with the known hash after adding it.

        Args:
            info_hash: Expected torrent hash
            max_attempts: Maximum number of polling attempts
            delay: Delay between attempts in seconds

        Returns:
            True if torrent was found, False if timeout
        """
        for attempt in range(max_attempts):
            try:
                torrents = self.client.torrents_info(torrent_hashes=info_hash.lower())
                if torrents:
                    logger.debug(
                        "qbittorrent_torrent_verified",
                        hash=info_hash,
                        attempt=attempt + 1
                    )
                    return True
            except Exception as e:
                logger.debug(
                    "qbittorrent_verification_attempt_failed",
                    hash=info_hash,
                    attempt=attempt + 1,
                    error=str(e)
                )

            if attempt < max_attempts - 1:
                time.sleep(delay)

        logger.warning(
            "qbittorrent_torrent_verification_timeout",
            hash=info_hash,
            max_attempts=max_attempts
        )
        return False

    def _ensure_category(self, category: str):
        """Ensure category exists, create if not"""
        try:
            categories = self.client.torrents_categories()
            if category not in categories:
                logger.info("qbittorrent_create_category", category=category)
                self.client.torrents_create_category(name=category)
        except Exception as e:
            logger.warning("qbittorrent_category_error", error=str(e))

    def _extract_hash_from_magnet(self, magnet: str) -> Optional[str]:
        """
        Extract info_hash from a magnet link.

        Format: magnet:?xt=urn:btih:HASH&...

        Returns:
            40-character lowercase SHA-1 hash, or None if extraction fails
        """
        if not magnet or "btih:" not in magnet.lower():
            return None

        try:
            hash_start = magnet.lower().find("btih:") + 5
            hash_end = magnet.find("&", hash_start)
            if hash_end == -1:
                info_hash = magnet[hash_start:]
            else:
                info_hash = magnet[hash_start:hash_end]

            # Handle base32 encoded hashes (32 chars) - convert to hex
            if len(info_hash) == 32:
                import base64
                try:
                    decoded = base64.b32decode(info_hash.upper())
                    info_hash = decoded.hex()
                except Exception:
                    pass

            # Validate hash (40 chars for SHA-1 hex)
            if len(info_hash) == 40:
                return info_hash.lower()
        except Exception as e:
            logger.warning("qbittorrent_magnet_hash_extraction_failed", error=str(e))

        return None

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

        Priority order:
        1. Extract hash from magnet link (most reliable for magnets)
        2. Tag-based lookup with retries (reliable for all types)

        NOTE: We deliberately DO NOT fall back to category or "most recent" lookups
        as those cause race conditions where the wrong torrent can be returned.
        """
        # Priority 1: Extract hash from magnet link (this is deterministic and reliable)
        if magnet:
            extracted_hash = self._extract_hash_from_magnet(magnet)
            if extracted_hash:
                # Verify the torrent exists in qBittorrent with this hash
                try:
                    torrents = self.client.torrents_info(torrent_hashes=extracted_hash)
                    if torrents:
                        logger.info("qbittorrent_found_by_magnet_hash", hash=extracted_hash)
                        return extracted_hash
                    else:
                        # Torrent not yet indexed, wait and retry
                        logger.debug("qbittorrent_magnet_hash_not_found_yet", hash=extracted_hash)
                except Exception as e:
                    logger.warning("qbittorrent_magnet_hash_verify_failed", error=str(e))

        # Priority 2: Tag-based lookup with retries (most reliable for URLs and files)
        if tags:
            max_retries = 10
            retry_delay = 0.5  # Start with 0.5 seconds

            for attempt in range(max_retries):
                try:
                    for tag in tags:
                        torrents = self.client.torrents_info(tag=tag)
                        if torrents and len(torrents) > 0:
                            logger.info(
                                "qbittorrent_found_by_tag",
                                tag=tag,
                                hash=torrents[0].hash,
                                attempt=attempt + 1
                            )
                            return torrents[0].hash

                    # If we extracted a hash from magnet, check if it's available now
                    if magnet:
                        extracted_hash = self._extract_hash_from_magnet(magnet)
                        if extracted_hash:
                            torrents = self.client.torrents_info(torrent_hashes=extracted_hash)
                            if torrents:
                                logger.info(
                                    "qbittorrent_found_by_magnet_hash_retry",
                                    hash=extracted_hash,
                                    attempt=attempt + 1
                                )
                                return extracted_hash

                except Exception as e:
                    logger.warning(
                        "qbittorrent_tag_lookup_failed",
                        error=str(e),
                        attempt=attempt + 1
                    )

                # Wait before retry (exponential backoff capped at 2 seconds)
                if attempt < max_retries - 1:
                    time.sleep(min(retry_delay, 2.0))
                    retry_delay *= 1.5

            logger.error(
                "qbittorrent_hash_lookup_exhausted",
                tags=tags,
                has_magnet=bool(magnet),
                max_retries=max_retries
            )

        # DO NOT use category-based or "most recent" fallbacks!
        # These cause race conditions where we track the wrong torrent.
        # It's better to fail and let the user retry than to track wrong content.

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
