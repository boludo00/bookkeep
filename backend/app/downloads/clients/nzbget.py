"""
NZBGet client implementation.

Provides downloading capabilities for NZB files via NZBGet RPC API.
"""
import time
import base64
from typing import Optional, Dict, Any, List
from pathlib import Path
import structlog
import requests
from xml.etree import ElementTree as ET

from ..import DownloadState

logger = structlog.get_logger()


class NZBGetClient:
    """
    NZBGet RPC API client for usenet downloads.

    Features:
    - Add NZB files via URL or file upload
    - Monitor download progress
    - Get completed file paths
    - Category management
    - Path mapping for Docker environments
    """

    def __init__(
        self,
        host: str,
        port: int = 6789,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: bool = False,
        url_base: Optional[str] = None,
        category: Optional[str] = None,
        path_mappings: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize NZBGet client.

        Args:
            host: NZBGet host (e.g., "localhost", "nzbget")
            port: NZBGet RPC port (default: 6789)
            username: NZBGet username
            password: NZBGet password
            use_ssl: Use HTTPS connection
            url_base: URL base path for reverse proxy (e.g., "/nzbget")
            category: Default category for downloads
            path_mappings: Docker path mappings {"container_path": "host_path"}
        """
        self.host = host
        self.port = port
        self.username = username or ""
        self.password = password or ""
        self.use_ssl = use_ssl
        self.url_base = url_base
        self.category = category
        self.path_mappings = path_mappings or {}

        # Build RPC URL
        protocol = "https" if use_ssl else "http"
        base_path = f"/{self.url_base.strip('/')}" if self.url_base else ""

        # URL with auth: http://username:password@host:port[/url_base]/jsonrpc
        if self.username and self.password:
            self.rpc_url = f"{protocol}://{self.username}:{self.password}@{self.host}:{self.port}{base_path}/jsonrpc"
        else:
            self.rpc_url = f"{protocol}://{self.host}:{self.port}{base_path}/jsonrpc"

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _rpc_call(self, method: str, params: Optional[List] = None) -> Any:
        """
        Make JSON-RPC call to NZBGet.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            RPC result or None on error
        """
        if params is None:
            params = []

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }

        try:
            response = self.session.post(self.rpc_url, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                logger.error(
                    "nzbget_rpc_error",
                    method=method,
                    error=result["error"]
                )
                return None

            return result.get("result")

        except requests.exceptions.RequestException as e:
            logger.error(
                "nzbget_rpc_request_failed",
                method=method,
                error=str(e)
            )
            return None
        except Exception as e:
            logger.error(
                "nzbget_rpc_failed",
                method=method,
                error=str(e)
            )
            return None

    def test_connection(self) -> bool:
        """
        Test connection to NZBGet.

        Returns:
            True if connection successful
        """
        try:
            version = self._rpc_call("version")
            if version:
                logger.info("nzbget_test_success", version=version)
                return True
            return False

        except Exception as e:
            logger.warning("nzbget_test_failed", error=str(e))
            return False

    def add_nzb(
        self,
        url: Optional[str] = None,
        nzb_file: Optional[bytes] = None,
        nzb_name: Optional[str] = None,
        category: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[int]:
        """
        Add an NZB to NZBGet.

        Args:
            url: NZB file URL
            nzb_file: NZB file bytes
            nzb_name: NZB filename (required when using nzb_file)
            category: Download category
            priority: Priority (-100 to 100, default 0)

        Returns:
            NZB ID or None if failed
        """
        if not any([url, nzb_file]):
            raise ValueError("Must provide url or nzb_file")

        if nzb_file and not nzb_name:
            raise ValueError("nzb_name required when providing nzb_file")

        # Use default category if not specified
        if category is None:
            category = self.category or ""

        try:
            if url:
                # Add by URL
                logger.info("nzbget_add_url", url=url, category=category)

                result = self._rpc_call("append", [
                    nzb_name or "download.nzb",
                    url,
                    category,
                    priority,
                    False,  # AddToTop
                    False,  # AddPaused
                    "",     # DupeKey
                    0,      # DupeScore
                    "SCORE", # DupeMode
                    True,    # AutoCategory
                    [""]      # PPParameters
                ])

            else:
                # Add by file (base64 encoded)
                logger.info("nzbget_add_file", filename=nzb_name, category=category)

                # Encode NZB content to base64
                nzb_content_b64 = base64.b64encode(nzb_file).decode('utf-8')

                result = self._rpc_call("append", [
                    nzb_name,
                    nzb_content_b64,
                    category,
                    priority,
                    False,  # AddToTop
                    False,  # AddPaused
                    "",     # DupeKey
                    0,      # DupeScore
                    "SCORE", # DupeMode
                    True,    # AutoCategory
                    [""]      # PPParameters
                ])

            if result and result > 0:
                logger.info("nzbget_nzb_added", nzb_id=result)
                return result
            else:
                logger.warning("nzbget_add_failed", result=result)
                return None

        except Exception as e:
            logger.error("nzbget_add_error", error=str(e))
            return None

    def get_download_status(self, nzb_id: int) -> Dict[str, Any]:
        """
        Get download status for an NZB.

        Args:
            nzb_id: NZB ID

        Returns:
            Dict with status information:
            {
                "state": DownloadState,
                "progress": 0.0-100.0,
                "download_speed": bytes/sec,
                "name": nzb name,
                "dest_dir": download path,
                "files": list of files,
            }
        """
        try:
            # Get queue and history
            groups = self._rpc_call("listgroups")
            if not groups:
                # Try history
                return self._get_status_from_history(nzb_id)

            # Find matching group
            for group in groups:
                if group.get("NZBID") == nzb_id or group.get("LastID") == nzb_id:
                    return self._parse_group_status(group)

            # Not in queue, check history
            return self._get_status_from_history(nzb_id)

        except Exception as e:
            logger.error("nzbget_get_status_failed", nzb_id=nzb_id, error=str(e))
            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": str(e),
            }

    def _parse_group_status(self, group: Dict) -> Dict[str, Any]:
        """Parse NZBGet group info into status dict"""
        # Calculate progress
        total_mb = group.get("FileSizeMB", 0)
        remaining_mb = group.get("RemainingSizeMB", 0)

        if total_mb > 0:
            progress = ((total_mb - remaining_mb) / total_mb) * 100
        else:
            progress = 0.0

        # Map status to DownloadState
        status = group.get("Status", "")
        state = self._map_status_to_state(status)

        return {
            "state": state,
            "progress": progress,
            "download_speed": group.get("DownloadRate", 0),
            "name": group.get("NZBName", ""),
            "dest_dir": self._map_path_from_container(group.get("DestDir", "")),
            "total_size": total_mb * 1024 * 1024,  # Convert MB to bytes
            "remaining_size": remaining_mb * 1024 * 1024,
            "category": group.get("Category", ""),
            "files": [],  # NZBGet doesn't provide file list in group info
        }

    def _get_status_from_history(self, nzb_id: int) -> Dict[str, Any]:
        """Get status from history (completed/failed downloads)"""
        try:
            history = self._rpc_call("history")
            if not history:
                return {
                    "state": DownloadState.ERROR,
                    "progress": 0.0,
                    "message": "NZB not found in queue or history",
                }

            # Find matching history item
            for item in history:
                if item.get("NZBID") == nzb_id:
                    return self._parse_history_status(item)

            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": "NZB not found",
            }

        except Exception as e:
            logger.error("nzbget_history_failed", error=str(e))
            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": str(e),
            }

    def _parse_history_status(self, item: Dict) -> Dict[str, Any]:
        """Parse NZBGet history item into status dict"""
        status = item.get("Status", "")
        par_status = item.get("ParStatus", "")
        unpack_status = item.get("UnpackStatus", "")

        # Determine final state
        if status == "SUCCESS" and unpack_status == "SUCCESS":
            state = DownloadState.COMPLETE
            progress = 100.0
        elif status == "SUCCESS":
            state = DownloadState.PROCESSING
            progress = 100.0
        elif status in ["FAILURE", "DELETED"]:
            state = DownloadState.ERROR
            progress = 0.0
        else:
            state = DownloadState.QUEUED
            progress = 0.0

        return {
            "state": state,
            "progress": progress,
            "download_speed": 0,
            "name": item.get("NZBName", ""),
            "dest_dir": self._map_path_from_container(item.get("DestDir", "")),
            "total_size": item.get("FileSizeMB", 0) * 1024 * 1024,
            "category": item.get("Category", ""),
            "status": status,
            "par_status": par_status,
            "unpack_status": unpack_status,
            "files": [],
        }

    def _map_status_to_state(self, status: str) -> DownloadState:
        """Map NZBGet status to DownloadState"""
        status_map = {
            "DOWNLOADING": DownloadState.DOWNLOADING,
            "PAUSED": DownloadState.PAUSED,
            "QUEUED": DownloadState.QUEUED,
            "FETCHING": DownloadState.DOWNLOADING,
            "PP_QUEUED": DownloadState.PROCESSING,
            "LOADING_PARS": DownloadState.PROCESSING,
            "VERIFYING_SOURCES": DownloadState.CHECKING,
            "REPAIRING": DownloadState.PROCESSING,
            "VERIFYING_REPAIRED": DownloadState.CHECKING,
            "RENAMING": DownloadState.PROCESSING,
            "UNPACKING": DownloadState.PROCESSING,
            "MOVING": DownloadState.PROCESSING,
            "EXECUTING_SCRIPT": DownloadState.PROCESSING,
            "PP_FINISHED": DownloadState.COMPLETE,
        }

        return status_map.get(status, DownloadState.QUEUED)

    def get_completed_download_path(self, nzb_id: int) -> Optional[str]:
        """
        Get the path to completed download.

        Args:
            nzb_id: NZB ID

        Returns:
            Path to downloaded folder or None
        """
        try:
            # Check history for completed download
            history = self._rpc_call("history")
            if not history:
                return None

            for item in history:
                if item.get("NZBID") == nzb_id:
                    # Check if completed successfully
                    status = item.get("Status", "")
                    unpack_status = item.get("UnpackStatus", "")

                    if status == "SUCCESS" and unpack_status in ["SUCCESS", "NONE"]:
                        dest_dir = item.get("DestDir", "")
                        if dest_dir:
                            return self._map_path_from_container(dest_dir)

                    logger.warning(
                        "nzbget_download_incomplete",
                        nzb_id=nzb_id,
                        status=status,
                        unpack_status=unpack_status
                    )
                    return None

            # Not in history
            logger.warning("nzbget_nzb_not_in_history", nzb_id=nzb_id)
            return None

        except Exception as e:
            logger.error(
                "nzbget_get_path_failed",
                nzb_id=nzb_id,
                error=str(e)
            )
            return None

    def remove_nzb(
        self,
        nzb_id: int,
        delete_files: bool = False
    ) -> bool:
        """
        Remove NZB from queue or history.

        Args:
            nzb_id: NZB ID
            delete_files: Also delete downloaded files

        Returns:
            True if removed successfully
        """
        try:
            # Try to remove from history first (includes files option)
            result = self._rpc_call("editqueue", [
                "GroupDelete",
                0,  # Offset
                "",  # Text (unused)
                [nzb_id]  # IDs
            ])

            if result:
                logger.info(
                    "nzbget_nzb_removed",
                    nzb_id=nzb_id,
                    delete_files=delete_files
                )

                # If delete_files, also delete from history
                if delete_files:
                    self._rpc_call("editqueue", [
                        "HistoryDelete",
                        0,
                        "",
                        [nzb_id]
                    ])

                return True
            else:
                logger.warning("nzbget_remove_failed", nzb_id=nzb_id)
                return False

        except Exception as e:
            logger.error(
                "nzbget_remove_error",
                nzb_id=nzb_id,
                error=str(e)
            )
            return False

    def pause_nzb(self, nzb_id: int) -> bool:
        """Pause an NZB download"""
        try:
            result = self._rpc_call("editqueue", [
                "GroupPause",
                0,
                "",
                [nzb_id]
            ])
            return bool(result)
        except Exception as e:
            logger.error("nzbget_pause_failed", nzb_id=nzb_id, error=str(e))
            return False

    def resume_nzb(self, nzb_id: int) -> bool:
        """Resume a paused NZB download"""
        try:
            result = self._rpc_call("editqueue", [
                "GroupResume",
                0,
                "",
                [nzb_id]
            ])
            return bool(result)
        except Exception as e:
            logger.error("nzbget_resume_failed", nzb_id=nzb_id, error=str(e))
            return False

    def find_existing_download(
        self,
        nzb_id: Optional[int] = None,
        name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[int]:
        """
        Find existing download by ID, name, or category.

        Args:
            nzb_id: NZB ID to search for
            name: NZB name to search for
            category: Category to search in

        Returns:
            NZB ID if found, None otherwise
        """
        try:
            # Search by ID (most specific)
            if nzb_id:
                status = self.get_download_status(nzb_id)
                if status.get("state") != DownloadState.ERROR:
                    return nzb_id

            # Search by name
            if name:
                # Check queue
                groups = self._rpc_call("listgroups")
                if groups:
                    for group in groups:
                        if group.get("NZBName") == name:
                            if category and group.get("Category") != category:
                                continue
                            return group.get("NZBID")

                # Check history
                history = self._rpc_call("history")
                if history:
                    for item in history:
                        if item.get("NZBName") == name:
                            if category and item.get("Category") != category:
                                continue
                            return item.get("NZBID")

            return None

        except Exception as e:
            logger.error("nzbget_find_failed", error=str(e))
            return None

    def _map_path_from_container(self, container_path: str) -> str:
        """
        Map path from Docker container to host.

        Args:
            container_path: Path inside container

        Returns:
            Mapped host path
        """
        if not self.path_mappings or not container_path:
            return container_path

        # Try each mapping
        for container_prefix, host_prefix in self.path_mappings.items():
            if container_path.startswith(container_prefix):
                # Replace container prefix with host prefix
                mapped = container_path.replace(container_prefix, host_prefix, 1)
                logger.debug(
                    "nzbget_path_mapped",
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
        if not self.path_mappings or not host_path:
            return host_path

        # Try each mapping (reverse)
        for container_prefix, host_prefix in self.path_mappings.items():
            if host_path.startswith(host_prefix):
                # Replace host prefix with container prefix
                mapped = host_path.replace(host_prefix, container_prefix, 1)
                logger.debug(
                    "nzbget_path_mapped",
                    host=host_path,
                    container=mapped
                )
                return mapped

        # No mapping found, return original
        return host_path

    def get_client_info(self) -> Dict[str, Any]:
        """
        Get NZBGet client information.

        Returns:
            Dict with client info (version, config, etc.)
        """
        try:
            version = self._rpc_call("version")
            config = self._rpc_call("config")

            # Extract useful config values
            config_dict = {}
            if config:
                for item in config:
                    name = item.get("Name", "")
                    value = item.get("Value", "")
                    config_dict[name] = value

            return {
                "version": version,
                "config": config_dict,
            }
        except Exception as e:
            logger.error("nzbget_get_info_failed", error=str(e))
            return {}

    def get_queue(self) -> List[Dict[str, Any]]:
        """
        Get current download queue.

        Returns:
            List of queue items
        """
        try:
            groups = self._rpc_call("listgroups")
            return groups or []
        except Exception as e:
            logger.error("nzbget_get_queue_failed", error=str(e))
            return []

    def get_history(self, hidden: bool = False) -> List[Dict[str, Any]]:
        """
        Get download history.

        Args:
            hidden: Include hidden items

        Returns:
            List of history items
        """
        try:
            history = self._rpc_call("history", [hidden])
            return history or []
        except Exception as e:
            logger.error("nzbget_get_history_failed", error=str(e))
            return []
