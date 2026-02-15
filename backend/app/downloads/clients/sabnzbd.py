"""
Sabnzbd client implementation.

Provides downloading capabilities for NZB files via Sabnzbd API.
"""
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
import structlog
import requests

from ..import DownloadState

logger = structlog.get_logger()


class SabnzbdClient:
    """
    Sabnzbd API client for usenet downloads.

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
        port: int = 8080,
        api_key: Optional[str] = None,
        use_ssl: bool = False,
        url_base: Optional[str] = None,
        category: Optional[str] = None,
        path_mappings: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize Sabnzbd client.

        Args:
            host: Sabnzbd host (e.g., "localhost", "sabnzbd")
            port: Sabnzbd port (default: 8080)
            api_key: Sabnzbd API key
            use_ssl: Use HTTPS connection
            url_base: URL base path for reverse proxy (e.g., "/sabnzbd")
            category: Default category for downloads
            path_mappings: Docker path mappings {"container_path": "host_path"}
        """
        self.host = host
        self.port = port
        self.api_key = api_key or ""
        self.use_ssl = use_ssl
        self.url_base = url_base
        self.category = category
        self.path_mappings = path_mappings or {}

        # Build base URL
        protocol = "https" if use_ssl else "http"
        base_path = f"/{self.url_base.strip('/')}" if self.url_base else ""
        self.base_url = f"{protocol}://{self.host}:{self.port}{base_path}/api"

        self.session = requests.Session()

    def _api_call(
        self,
        mode: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Make API call to Sabnzbd.

        Args:
            mode: API mode (e.g., "addurl", "queue", "history")
            params: Additional parameters
            files: Files to upload

        Returns:
            API response or None on error
        """
        if params is None:
            params = {}

        # Add API key and mode
        params["apikey"] = self.api_key
        params["mode"] = mode
        params["output"] = "json"

        try:
            if files:
                response = self.session.post(
                    self.base_url,
                    params=params,
                    files=files,
                    timeout=30,
                    verify=False  # Disable SSL verification for self-signed certs
                )
            else:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=30,
                    verify=False
                )

            response.raise_for_status()
            result = response.json()

            # Check for errors in response
            if isinstance(result, dict):
                if result.get("status") is False:
                    error = result.get("error", "Unknown error")
                    logger.error(
                        "sabnzbd_api_error",
                        mode=mode,
                        error=error
                    )
                    return None

            return result

        except requests.exceptions.RequestException as e:
            logger.error(
                "sabnzbd_api_request_failed",
                mode=mode,
                error=str(e)
            )
            return None
        except Exception as e:
            logger.error(
                "sabnzbd_api_failed",
                mode=mode,
                error=str(e)
            )
            return None

    def test_connection(self) -> bool:
        """
        Test connection to Sabnzbd.

        Returns:
            True if connection successful
        """
        try:
            result = self._api_call("version")
            if result and "version" in result:
                logger.info("sabnzbd_test_success", version=result.get("version"))
                return True
            return False

        except Exception as e:
            logger.warning("sabnzbd_test_failed", error=str(e))
            return False

    def add_nzb(
        self,
        url: Optional[str] = None,
        nzb_file: Optional[bytes] = None,
        nzb_name: Optional[str] = None,
        category: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[str]:
        """
        Add an NZB to Sabnzbd.

        Args:
            url: NZB file URL
            nzb_file: NZB file bytes
            nzb_name: NZB filename (required when using nzb_file)
            category: Download category
            priority: Priority (-100 to 100, default 0)

        Returns:
            NZO ID (job ID) or None if failed
        """
        if not any([url, nzb_file]):
            raise ValueError("Must provide url or nzb_file")

        if nzb_file and not nzb_name:
            raise ValueError("nzb_name required when providing nzb_file")

        # Use default category if not specified
        if category is None:
            category = self.category or ""

        try:
            params = {
                "cat": category,
                "priority": priority,
            }

            if nzb_name:
                params["nzbname"] = nzb_name

            if url:
                # Add by URL
                logger.info("sabnzbd_add_url", url=url, category=category)
                params["name"] = url
                result = self._api_call("addurl", params)
            else:
                # Add by file upload
                logger.info("sabnzbd_add_file", filename=nzb_name, category=category)
                files = {"nzbfile": (nzb_name, nzb_file, "application/x-nzb")}
                result = self._api_call("addfile", params, files=files)

            if result:
                # Sabnzbd returns {"status": True, "nzo_ids": ["SABnzbd_nzo_xxxxx"]}
                if isinstance(result, dict) and result.get("status") is True:
                    nzo_ids = result.get("nzo_ids", [])
                    if nzo_ids and len(nzo_ids) > 0:
                        nzo_id = nzo_ids[0]
                        logger.info("sabnzbd_nzb_added", nzo_id=nzo_id)
                        return nzo_id

            logger.warning("sabnzbd_add_failed", result=result)
            return None

        except Exception as e:
            logger.error("sabnzbd_add_error", error=str(e))
            return None

    def get_download_status(self, nzo_id: str) -> Dict[str, Any]:
        """
        Get download status for an NZB.

        Args:
            nzo_id: NZO ID (job ID)

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
            # First check queue
            queue = self._api_call("queue")
            if queue and "queue" in queue:
                slots = queue["queue"].get("slots", [])
                for slot in slots:
                    if slot.get("nzo_id") == nzo_id:
                        return self._parse_queue_slot(slot)

            # Not in queue, check history
            return self._get_status_from_history(nzo_id)

        except Exception as e:
            logger.error("sabnzbd_get_status_failed", nzo_id=nzo_id, error=str(e))
            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": str(e),
            }

    def _parse_queue_slot(self, slot: Dict) -> Dict[str, Any]:
        """Parse Sabnzbd queue slot into status dict"""
        # Calculate progress
        mb_left = float(slot.get("mbleft", 0))
        mb_total = float(slot.get("mb", 0))

        if mb_total > 0:
            progress = ((mb_total - mb_left) / mb_total) * 100
        else:
            progress = 0.0

        # Map status to DownloadState
        status = slot.get("status", "")
        state = self._map_status_to_state(status)

        # Convert speed from KB/s to bytes/s
        speed_kbps = slot.get("kbpersec", "0")
        try:
            download_speed = float(speed_kbps) * 1024
        except:
            download_speed = 0

        return {
            "state": state,
            "progress": progress,
            "download_speed": download_speed,
            "name": slot.get("filename", ""),
            "dest_dir": "",  # Not available in queue
            "total_size": mb_total * 1024 * 1024,
            "remaining_size": mb_left * 1024 * 1024,
            "category": slot.get("cat", ""),
            "files": [],
        }

    def _get_status_from_history(self, nzo_id: str) -> Dict[str, Any]:
        """Get status from history (completed/failed downloads)"""
        try:
            history = self._api_call("history")
            if not history or "history" not in history:
                return {
                    "state": DownloadState.ERROR,
                    "progress": 0.0,
                    "message": "NZO not found in queue or history",
                }

            # Find matching history item
            slots = history["history"].get("slots", [])
            for slot in slots:
                if slot.get("nzo_id") == nzo_id:
                    return self._parse_history_slot(slot)

            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": "NZO not found",
            }

        except Exception as e:
            logger.error("sabnzbd_history_failed", error=str(e))
            return {
                "state": DownloadState.ERROR,
                "progress": 0.0,
                "message": str(e),
            }

    def _parse_history_slot(self, slot: Dict) -> Dict[str, Any]:
        """Parse Sabnzbd history slot into status dict"""
        status = slot.get("status", "")
        fail_message = slot.get("fail_message", "")

        # Determine final state
        if status == "Completed":
            state = DownloadState.COMPLETE
            progress = 100.0
        elif status == "Failed":
            state = DownloadState.ERROR
            progress = 0.0
        else:
            state = DownloadState.QUEUED
            progress = 0.0

        storage = slot.get("storage", "")
        path = self._map_path_from_container(storage) if storage else ""

        return {
            "state": state,
            "progress": progress,
            "download_speed": 0,
            "name": slot.get("name", ""),
            "dest_dir": path,
            "total_size": float(slot.get("bytes", 0)),
            "category": slot.get("category", ""),
            "status": status,
            "fail_message": fail_message,
            "files": [],
        }

    def _map_status_to_state(self, status: str) -> DownloadState:
        """Map Sabnzbd status to DownloadState"""
        status_lower = status.lower()

        if "download" in status_lower or "fetching" in status_lower:
            return DownloadState.DOWNLOADING
        elif "paused" in status_lower:
            return DownloadState.PAUSED
        elif "queued" in status_lower:
            return DownloadState.QUEUED
        elif "extract" in status_lower or "unpack" in status_lower:
            return DownloadState.PROCESSING
        elif "verif" in status_lower or "repair" in status_lower:
            return DownloadState.CHECKING
        elif "completed" in status_lower:
            return DownloadState.COMPLETE
        elif "failed" in status_lower:
            return DownloadState.ERROR
        else:
            return DownloadState.QUEUED

    def get_completed_download_path(self, nzo_id: str) -> Optional[str]:
        """
        Get the path to completed download.

        Args:
            nzo_id: NZO ID

        Returns:
            Path to downloaded folder or None
        """
        try:
            # Check history for completed download
            history = self._api_call("history")
            if not history or "history" not in history:
                return None

            slots = history["history"].get("slots", [])
            for slot in slots:
                if slot.get("nzo_id") == nzo_id:
                    status = slot.get("status", "")

                    if status == "Completed":
                        storage = slot.get("storage", "")
                        if storage:
                            return self._map_path_from_container(storage)

                    logger.warning(
                        "sabnzbd_download_incomplete",
                        nzo_id=nzo_id,
                        status=status,
                        fail_message=slot.get("fail_message", "")
                    )
                    return None

            # Not in history
            logger.warning("sabnzbd_nzo_not_in_history", nzo_id=nzo_id)
            return None

        except Exception as e:
            logger.error(
                "sabnzbd_get_path_failed",
                nzo_id=nzo_id,
                error=str(e)
            )
            return None

    def remove_nzb(
        self,
        nzo_id: str,
        delete_files: bool = False
    ) -> bool:
        """
        Remove NZO from queue or history.

        Args:
            nzo_id: NZO ID
            delete_files: Also delete downloaded files

        Returns:
            True if removed successfully
        """
        try:
            # Try queue first
            result = self._api_call("queue", {
                "name": "delete",
                "value": nzo_id,
                "del_files": "1" if delete_files else "0"
            })

            if result:
                logger.info(
                    "sabnzbd_nzo_removed",
                    nzo_id=nzo_id,
                    delete_files=delete_files
                )
                return True

            # Try history
            result = self._api_call("history", {
                "name": "delete",
                "value": nzo_id,
                "del_files": "1" if delete_files else "0"
            })

            if result:
                logger.info(
                    "sabnzbd_nzo_removed_from_history",
                    nzo_id=nzo_id,
                    delete_files=delete_files
                )
                return True

            logger.warning("sabnzbd_remove_failed", nzo_id=nzo_id)
            return False

        except Exception as e:
            logger.error(
                "sabnzbd_remove_error",
                nzo_id=nzo_id,
                error=str(e)
            )
            return False

    def pause_nzb(self, nzo_id: str) -> bool:
        """Pause an NZO download"""
        try:
            result = self._api_call("queue", {
                "name": "pause",
                "value": nzo_id
            })
            return bool(result)
        except Exception as e:
            logger.error("sabnzbd_pause_failed", nzo_id=nzo_id, error=str(e))
            return False

    def resume_nzb(self, nzo_id: str) -> bool:
        """Resume a paused NZO download"""
        try:
            result = self._api_call("queue", {
                "name": "resume",
                "value": nzo_id
            })
            return bool(result)
        except Exception as e:
            logger.error("sabnzbd_resume_failed", nzo_id=nzo_id, error=str(e))
            return False

    def find_existing_download(
        self,
        nzo_id: Optional[str] = None,
        name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find existing download by ID, name, or category.

        Args:
            nzo_id: NZO ID to search for
            name: NZB name to search for
            category: Category to search in

        Returns:
            NZO ID if found, None otherwise
        """
        try:
            # Search by ID (most specific)
            if nzo_id:
                status = self.get_download_status(nzo_id)
                if status.get("state") != DownloadState.ERROR:
                    return nzo_id

            # Search by name
            if name:
                # Check queue
                queue = self._api_call("queue")
                if queue and "queue" in queue:
                    slots = queue["queue"].get("slots", [])
                    for slot in slots:
                        if slot.get("filename") == name:
                            if category and slot.get("cat") != category:
                                continue
                            return slot.get("nzo_id")

                # Check history
                history = self._api_call("history")
                if history and "history" in history:
                    slots = history["history"].get("slots", [])
                    for slot in slots:
                        if slot.get("name") == name:
                            if category and slot.get("category") != category:
                                continue
                            return slot.get("nzo_id")

            return None

        except Exception as e:
            logger.error("sabnzbd_find_failed", error=str(e))
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
                    "sabnzbd_path_mapped",
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
                    "sabnzbd_path_mapped",
                    host=host_path,
                    container=mapped
                )
                return mapped

        # No mapping found, return original
        return host_path

    def get_client_info(self) -> Dict[str, Any]:
        """
        Get Sabnzbd client information.

        Returns:
            Dict with client info (version, config, etc.)
        """
        try:
            version_result = self._api_call("version")
            version = version_result.get("version") if version_result else None

            return {
                "version": version,
            }
        except Exception as e:
            logger.error("sabnzbd_get_info_failed", error=str(e))
            return {}

    def get_queue(self) -> List[Dict[str, Any]]:
        """
        Get current download queue.

        Returns:
            List of queue items
        """
        try:
            queue = self._api_call("queue")
            if queue and "queue" in queue:
                return queue["queue"].get("slots", [])
            return []
        except Exception as e:
            logger.error("sabnzbd_get_queue_failed", error=str(e))
            return []

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get download history.

        Args:
            limit: Maximum number of history items

        Returns:
            List of history items
        """
        try:
            history = self._api_call("history", {"limit": limit})
            if history and "history" in history:
                return history["history"].get("slots", [])
            return []
        except Exception as e:
            logger.error("sabnzbd_get_history_failed", error=str(e))
            return []
