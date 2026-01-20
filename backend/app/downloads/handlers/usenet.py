"""
Usenet download handler.

Handles usenet downloads using configured usenet clients (NZBGet, SABnzbd, etc.).
"""
import time
from typing import Optional, Callable, Union
from threading import Event
import structlog

from .. import DownloadHandler, DownloadStatus, DownloadState, register_handler
from ..clients import NZBGetClient, SabnzbdClient
from ...models import DownloadTask, DownloadClient
from sqlalchemy.orm import Session

logger = structlog.get_logger()


@register_handler("usenet")
class UsenetHandler(DownloadHandler):
    """
    Usenet download handler using NZBGet or Sabnzbd.

    Manages the download lifecycle:
    1. Add NZB to client
    2. Monitor progress through download and post-processing
    3. Wait for completion
    4. Return download path
    """

    @property
    def source_name(self) -> str:
        return "usenet"

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize usenet handler.

        Args:
            db_session: Database session for looking up download clients
        """
        self.db_session = db_session
        self._clients = {}  # Cache of initialized clients

    def _get_client(self, task: DownloadTask) -> Optional[Union[NZBGetClient, SabnzbdClient]]:
        """
        Get or create a usenet client for the task.

        Args:
            task: Download task

        Returns:
            NZBGetClient or SabnzbdClient instance or None
        """
        # If task has a specific client, use it
        if task.client_download_id and task.client_type:
            client_type = task.client_type
        else:
            # Try to find any enabled usenet client
            if self.db_session:
                try:
                    client_config = self.db_session.query(DownloadClient).filter(
                        DownloadClient.protocol == "usenet",
                        DownloadClient.enabled == True
                    ).order_by(DownloadClient.priority.desc()).first()

                    if client_config:
                        client_type = client_config.type
                    else:
                        client_type = "nzbget"  # Default fallback
                except:
                    client_type = "nzbget"  # Default fallback
            else:
                client_type = "nzbget"  # Default fallback

        # Check cache
        if client_type in self._clients:
            return self._clients[client_type]

        # Get client config from database
        if self.db_session:
            try:
                client_config = self.db_session.query(DownloadClient).filter(
                    DownloadClient.type == client_type,
                    DownloadClient.protocol == "usenet",
                    DownloadClient.enabled == True
                ).order_by(DownloadClient.priority.desc()).first()

                if client_config:
                    # Parse path mappings
                    import json
                    path_mappings = {}
                    if client_config.path_mappings_json:
                        try:
                            path_mappings = json.loads(client_config.path_mappings_json)
                        except:
                            pass

                    # Initialize appropriate client based on type
                    if client_type == "sabnzbd":
                        client = SabnzbdClient(
                            host=client_config.host,
                            port=client_config.port,
                            api_key=client_config.api_key,
                            use_ssl=client_config.use_ssl,
                            category=client_config.category,
                            path_mappings=path_mappings,
                        )
                    else:  # nzbget
                        client = NZBGetClient(
                            host=client_config.host,
                            port=client_config.port,
                            username=client_config.username,
                            password=client_config.password,
                            use_ssl=client_config.use_ssl,
                            category=client_config.category,
                            path_mappings=path_mappings,
                        )

                    # Cache it
                    self._clients[client_type] = client
                    return client

            except Exception as e:
                logger.error("usenet_get_client_failed", error=str(e))

        # No client configured - log clear error
        logger.error(
            "usenet_no_client_configured",
            message="No usenet download client configured. Please add a client in Settings → Download Clients",
            client_type=client_type
        )
        return None

    def download(
        self,
        task: DownloadTask,
        cancel_flag: Event,
        progress_callback: Optional[Callable[[float], None]] = None,
        status_callback: Optional[Callable[[DownloadStatus], None]] = None,
    ) -> Optional[str]:
        """
        Execute usenet download.

        Args:
            task: Download task with release info
            cancel_flag: Event to signal cancellation
            progress_callback: Called with progress percentage (0-100)
            status_callback: Called with status updates

        Returns:
            Path to downloaded file/folder or None on failure
        """
        client = self._get_client(task)
        if not client:
            logger.error("usenet_no_client", task_id=task.id)
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.ERROR,
                    progress=0.0,
                    message="No usenet client available"
                ))
            return None

        try:
            # Parse release data
            import json
            release_data = {}
            if task.release_data_json:
                try:
                    release_data = json.loads(task.release_data_json)
                except:
                    pass

            # Check if already downloading
            nzb_id = None
            if task.client_download_id:
                try:
                    nzb_id = int(task.client_download_id)
                    logger.info("usenet_resuming", task_id=task.id, nzb_id=nzb_id)
                except:
                    pass

            if not nzb_id:
                # Add NZB to client
                logger.info(
                    "usenet_adding",
                    task_id=task.id,
                    url=task.download_url,
                    format=task.format
                )

                if status_callback:
                    status_callback(DownloadStatus(
                        state=DownloadState.QUEUED,
                        progress=0.0,
                        message="Adding NZB to client"
                    ))

                # Use the client's configured category (from download client settings)
                # This respects the user's NZBGet category configuration
                category = client.category

                # Generate NZB name from release title
                nzb_name = f"{task.release_title or 'download'}.nzb"

                # Add NZB (by URL)
                nzb_id = client.add_nzb(
                    url=task.download_url,
                    nzb_name=nzb_name,
                    category=category
                )

                if not nzb_id:
                    logger.error("usenet_add_failed", task_id=task.id)
                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.ERROR,
                            progress=0.0,
                            message="Failed to add NZB"
                        ))
                    return None

                # Store client info in task - determine client type from client instance
                if isinstance(client, SabnzbdClient):
                    task.client_type = "sabnzbd"
                else:
                    task.client_type = "nzbget"
                task.client_download_id = str(nzb_id)

                logger.info("usenet_added", task_id=task.id, nzb_id=nzb_id, client_type=task.client_type)

            # Monitor download progress
            last_progress = -1
            last_state = None
            poll_interval = 3  # seconds (usenet downloads can be slower)

            while not cancel_flag.is_set():
                # Get status from client
                status = client.get_download_status(nzb_id)

                state = status.get("state", DownloadState.QUEUED)
                progress = status.get("progress", 0.0)

                # Update callbacks
                if progress != last_progress and progress_callback:
                    progress_callback(progress)
                    last_progress = progress

                # Generate status message
                message = status.get("name", "Downloading")
                if state == DownloadState.DOWNLOADING:
                    message = f"{message} - {progress:.1f}%"
                elif state == DownloadState.PROCESSING:
                    # Get post-processing status
                    pp_status = status.get("unpack_status", "processing")
                    message = f"{message} - Post-processing ({pp_status})"
                elif state == DownloadState.CHECKING:
                    message = f"{message} - Verifying"

                if status_callback and (state != last_state or progress != last_progress):
                    status_callback(DownloadStatus(
                        state=state,
                        progress=progress,
                        download_speed=status.get("download_speed"),
                        message=message
                    ))
                    last_state = state

                # Check for completion
                if state == DownloadState.COMPLETE:
                    logger.info(
                        "usenet_complete",
                        task_id=task.id,
                        nzb_id=nzb_id,
                        progress=progress
                    )

                    # Get download path
                    download_path = client.get_completed_download_path(nzb_id)

                    if download_path:
                        logger.info(
                            "usenet_download_path",
                            task_id=task.id,
                            path=download_path
                        )
                        return download_path
                    else:
                        logger.warning(
                            "usenet_no_path",
                            task_id=task.id,
                            nzb_id=nzb_id
                        )
                        # Still return success with dest_dir from status
                        return status.get("dest_dir", "")

                # Check for errors
                if state == DownloadState.ERROR:
                    error_msg = status.get("message", "Download error")

                    # Try to get more details from status
                    if "status" in status:
                        error_msg = f"{error_msg} (Status: {status['status']})"
                    if "par_status" in status and status["par_status"] != "SUCCESS":
                        error_msg = f"{error_msg} (PAR: {status['par_status']})"
                    if "unpack_status" in status and status["unpack_status"] != "SUCCESS":
                        error_msg = f"{error_msg} (Unpack: {status['unpack_status']})"

                    logger.error(
                        "usenet_download_error",
                        task_id=task.id,
                        nzb_id=nzb_id,
                        error=error_msg
                    )

                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.ERROR,
                            progress=progress,
                            message=error_msg
                        ))
                    return None

                # Wait before next poll
                time.sleep(poll_interval)

            # Cancelled
            logger.info("usenet_cancelled", task_id=task.id, nzb_id=nzb_id)

            # Optionally pause the download
            try:
                client.pause_nzb(nzb_id)
            except:
                pass

            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.PAUSED,
                    progress=last_progress if last_progress >= 0 else 0.0,
                    message="Download cancelled"
                ))

            return None

        except Exception as e:
            logger.error("usenet_download_exception", task_id=task.id, error=str(e))
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.ERROR,
                    progress=0.0,
                    message=f"Exception: {str(e)}"
                ))
            return None

    def cleanup(self, task: DownloadTask, success: bool):
        """
        Clean up after download.

        Args:
            task: Download task
            success: Whether download was successful
        """
        if not task.client_download_id:
            return

        try:
            client = self._get_client(task)
            if not client:
                return

            nzb_id = int(task.client_download_id)

            if success:
                # Keep in history for a while, don't remove immediately
                logger.info("usenet_cleanup_success", task_id=task.id, nzb_id=nzb_id)
                # Could optionally remove from history after some time
            else:
                # Failed download, remove it
                logger.info("usenet_cleanup_failure", task_id=task.id, nzb_id=nzb_id)
                client.remove_nzb(nzb_id, delete_files=True)

        except Exception as e:
            logger.error("usenet_cleanup_error", task_id=task.id, error=str(e))

    def pause(self, task: DownloadTask) -> bool:
        """
        Pause a usenet download.

        Args:
            task: Download task

        Returns:
            True if paused successfully
        """
        if not task.client_download_id:
            return False

        try:
            client = self._get_client(task)
            if not client:
                return False

            nzb_id = int(task.client_download_id)
            return client.pause_nzb(nzb_id)

        except Exception as e:
            logger.error("usenet_pause_error", task_id=task.id, error=str(e))
            return False

    def resume(self, task: DownloadTask) -> bool:
        """
        Resume a paused usenet download.

        Args:
            task: Download task

        Returns:
            True if resumed successfully
        """
        if not task.client_download_id:
            return False

        try:
            client = self._get_client(task)
            if not client:
                return False

            nzb_id = int(task.client_download_id)
            return client.resume_nzb(nzb_id)

        except Exception as e:
            logger.error("usenet_resume_error", task_id=task.id, error=str(e))
            return False

    def cancel(self, task: DownloadTask) -> bool:
        """
        Cancel a usenet download and remove it.

        Args:
            task: Download task

        Returns:
            True if cancelled successfully
        """
        if not task.client_download_id:
            return False

        try:
            client = self._get_client(task)
            if not client:
                return False

            nzb_id = int(task.client_download_id)
            # Remove NZB and files
            return client.remove_nzb(nzb_id, delete_files=True)

        except Exception as e:
            logger.error("usenet_cancel_error", task_id=task.id, error=str(e))
            return False
