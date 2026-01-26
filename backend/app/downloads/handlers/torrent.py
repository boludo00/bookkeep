"""
Torrent download handler.

Handles torrent downloads using configured torrent clients (qBittorrent, etc.).
"""
import time
from typing import Optional, Callable
from threading import Event
import structlog

from .. import DownloadHandler, DownloadStatus, DownloadState, register_handler
from ..clients import QBittorrentClient
from ...models import DownloadTask, DownloadClient
from sqlalchemy.orm import Session

logger = structlog.get_logger()


@register_handler("torrent")
class TorrentHandler(DownloadHandler):
    """
    Torrent download handler using qBittorrent.

    Manages the download lifecycle:
    1. Add torrent to client
    2. Monitor progress
    3. Wait for completion
    4. Return download path
    """

    @property
    def source_name(self) -> str:
        return "torrent"

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize torrent handler.

        Args:
            db_session: Database session for looking up download clients
        """
        self.db_session = db_session
        self._clients = {}  # Cache of initialized clients

    def _get_client(self, task: DownloadTask) -> Optional[QBittorrentClient]:
        """
        Get or create a torrent client for the task.

        Args:
            task: Download task

        Returns:
            QBittorrentClient instance or None
        """
        # If task has a specific client, use it
        if task.client_download_id and task.client_type:
            client_type = task.client_type
        else:
            client_type = "qbittorrent"  # Default

        # Check cache
        if client_type in self._clients:
            return self._clients[client_type]

        # Get client config from database
        if self.db_session:
            try:
                client_config = self.db_session.query(DownloadClient).filter(
                    DownloadClient.type == client_type,
                    DownloadClient.protocol == "torrent",
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

                    # Initialize client with format-specific categories
                    client = QBittorrentClient(
                        host=client_config.host,
                        port=client_config.port,
                        username=client_config.username,
                        password=client_config.password,
                        use_ssl=client_config.use_ssl,
                        category=client_config.category,
                        ebook_category=client_config.ebook_category,
                        audiobook_category=client_config.audiobook_category,
                        path_mappings=path_mappings,
                    )

                    # Cache it
                    self._clients[client_type] = client
                    return client

            except Exception as e:
                logger.error("torrent_get_client_failed", error=str(e))

        # Fallback: try environment variables
        try:
            import os
            client = QBittorrentClient(
                host=os.getenv("QBITTORRENT_HOST", "qbittorrent"),
                port=int(os.getenv("QBITTORRENT_PORT", "8080")),
                username=os.getenv("QBITTORRENT_USERNAME", "admin"),
                password=os.getenv("QBITTORRENT_PASSWORD", "adminadmin"),
                use_ssl=os.getenv("QBITTORRENT_SSL", "false").lower() == "true",
                category=os.getenv("QBITTORRENT_CATEGORY", "books"),
            )

            self._clients[client_type] = client
            return client

        except Exception as e:
            logger.error("torrent_fallback_client_failed", error=str(e))
            return None

    def download(
        self,
        task: DownloadTask,
        cancel_flag: Event,
        progress_callback: Optional[Callable[[float], None]] = None,
        status_callback: Optional[Callable[[DownloadStatus], None]] = None,
    ) -> Optional[str]:
        """
        Execute torrent download.

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
            logger.error("torrent_no_client", task_id=task.id)
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.ERROR,
                    progress=0.0,
                    message="No torrent client available"
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
            info_hash = task.client_download_id
            if info_hash:
                # Already added, just monitor
                logger.info("torrent_resuming", task_id=task.id, info_hash=info_hash)
            else:
                # Add torrent to client
                logger.info(
                    "torrent_adding",
                    task_id=task.id,
                    url=task.download_url,
                    format=task.format
                )

                if status_callback:
                    status_callback(DownloadStatus(
                        state=DownloadState.QUEUED,
                        progress=0.0,
                        message="Adding torrent to client"
                    ))

                # Select category based on format (ebook/audiobook) with fallback to default
                # This respects the user's format-specific qBittorrent category configuration
                category = client.get_category_for_format(task.format)

                # Add torrent with unique tag to identify it later
                # Use task_id as unique identifier to avoid race conditions
                unique_tag = f"bookkeep-{task.id}"

                if task.download_url.startswith("magnet:"):
                    info_hash = client.add_torrent(magnet=task.download_url, category=category, tags=[unique_tag])
                else:
                    info_hash = client.add_torrent(url=task.download_url, category=category, tags=[unique_tag])

                if not info_hash:
                    logger.error(
                        "torrent_add_failed",
                        task_id=task.id,
                        url=task.download_url[:100] if task.download_url else None
                    )
                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.ERROR,
                            progress=0.0,
                            message="Failed to add torrent - could not determine torrent hash. The torrent may have been added but cannot be tracked."
                        ))
                    return None

                # Check if this info_hash is already assigned to an ACTIVE task
                # We only block if another task is actively downloading/queued
                # Allow re-downloading if previous task failed/errored
                db = self.db_session or SessionLocal()
                try:
                    from ...models import DownloadTask as DownloadTaskModel

                    # States that indicate the task is actively in progress
                    active_states = ['queued', 'downloading', 'seeding', 'checking', 'paused']

                    existing_task = db.query(DownloadTaskModel).filter(
                        DownloadTaskModel.client_download_id == info_hash,
                        DownloadTaskModel.id != task.id,
                        DownloadTaskModel.state.in_(active_states)
                    ).first()

                    if existing_task:
                        logger.error(
                            "torrent_duplicate_detected",
                            task_id=task.id,
                            info_hash=info_hash,
                            existing_task_id=existing_task.id,
                            existing_task_state=existing_task.state,
                            existing_book_id=existing_task.book_id
                        )
                        if status_callback:
                            status_callback(DownloadStatus(
                                state=DownloadState.ERROR,
                                progress=0.0,
                                message=f"This release is already being downloaded for another book (task {existing_task.id}, state: {existing_task.state})"
                            ))
                        # Remove the duplicate torrent we just added
                        try:
                            client.remove_torrent(info_hash, delete_files=False)
                        except:
                            pass
                        return None
                finally:
                    if not self.db_session:
                        db.close()

                # Store client info in task
                task.client_type = "qbittorrent"
                task.client_download_id = info_hash

                logger.info("torrent_added", task_id=task.id, info_hash=info_hash)

            # Monitor download progress
            last_progress = -1
            poll_interval = 2  # seconds

            while not cancel_flag.is_set():
                # Get status from client
                status = client.get_download_status(info_hash)

                state = status.get("state", DownloadState.QUEUED)
                progress = status.get("progress", 0.0)

                # Update callbacks
                if progress != last_progress and progress_callback:
                    progress_callback(progress)
                    last_progress = progress

                if status_callback:
                    status_callback(DownloadStatus(
                        state=state,
                        progress=progress,
                        download_speed=status.get("download_speed"),
                        message=f"{status.get('name', 'Downloading')} - {progress:.1f}%",
                        client_state=status.get("client_state")
                    ))

                # Check for completion
                if state == DownloadState.COMPLETE or state == DownloadState.SEEDING:
                    logger.info(
                        "torrent_complete",
                        task_id=task.id,
                        info_hash=info_hash,
                        progress=progress
                    )

                    # Get download path
                    download_path = client.get_completed_download_path(info_hash)

                    if download_path:
                        logger.info(
                            "torrent_download_path",
                            task_id=task.id,
                            path=download_path
                        )
                        return download_path
                    else:
                        logger.warning(
                            "torrent_no_path",
                            task_id=task.id,
                            info_hash=info_hash
                        )
                        # Still return success, path might be determined later
                        return status.get("save_path", "")

                # Check for errors
                if state == DownloadState.ERROR:
                    error_msg = status.get("message", "Download error")
                    logger.error(
                        "torrent_download_error",
                        task_id=task.id,
                        info_hash=info_hash,
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
            logger.info("torrent_cancelled", task_id=task.id, info_hash=info_hash)

            # Optionally pause the torrent
            try:
                client.pause_torrent(info_hash)
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
            logger.error("torrent_download_exception", task_id=task.id, error=str(e))
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

            info_hash = task.client_download_id

            if success:
                # Keep seeding for a while, don't remove immediately
                logger.info("torrent_cleanup_success", task_id=task.id, info_hash=info_hash)
                # Could optionally stop seeding after ratio/time limits
                # client.pause_torrent(info_hash)
            else:
                # Failed download, remove it
                logger.info("torrent_cleanup_failure", task_id=task.id, info_hash=info_hash)
                client.remove_torrent(info_hash, delete_files=True)

        except Exception as e:
            logger.error("torrent_cleanup_error", task_id=task.id, error=str(e))

    def pause(self, task: DownloadTask) -> bool:
        """
        Pause a torrent download.

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

            return client.pause_torrent(task.client_download_id)

        except Exception as e:
            logger.error("torrent_pause_error", task_id=task.id, error=str(e))
            return False

    def resume(self, task: DownloadTask) -> bool:
        """
        Resume a paused torrent download.

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

            return client.resume_torrent(task.client_download_id)

        except Exception as e:
            logger.error("torrent_resume_error", task_id=task.id, error=str(e))
            return False

    def cancel(self, task: DownloadTask) -> bool:
        """
        Cancel a torrent download and remove it.

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

            # Remove torrent and files
            return client.remove_torrent(task.client_download_id, delete_files=True)

        except Exception as e:
            logger.error("torrent_cancel_error", task_id=task.id, error=str(e))
            return False
