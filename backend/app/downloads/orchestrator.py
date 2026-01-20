"""
Download orchestrator.

Manages the complete download workflow from search to completion.
"""
import os
import shutil
import threading
from pathlib import Path
from typing import Optional, List, Dict
from threading import Event
from datetime import datetime, timezone
import structlog
from sqlalchemy.orm import Session

from . import (
    Release,
    DownloadState,
    DownloadStatus,
    get_source,
    get_handler,
    list_sources,
    list_handlers,
)
from ..models import Book, DownloadTask, AppSettings
from ..database import SessionLocal

logger = structlog.get_logger()


class DownloadOrchestrator:
    """
    Orchestrates book downloads from search to completion.

    Workflow:
    1. Search for releases via configured sources (Prowlarr, etc.)
    2. Select best release based on quality score
    3. Create download task
    4. Execute download via appropriate handler (torrent/usenet)
    5. Monitor progress
    6. Post-process downloaded files
    7. Update book availability
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize orchestrator.

        Args:
            db_session: Database session (will create if not provided)
        """
        self.db_session = db_session
        self._active_downloads: Dict[int, Event] = {}  # task_id -> cancel_event
        self._download_threads: Dict[int, threading.Thread] = {}

    def search_releases(
        self,
        book: Book,
        format_type: str = "ebook",
        source_name: str = "prowlarr"
    ) -> List[Release]:
        """
        Search for book releases.

        Args:
            book: Book to search for
            format_type: "ebook" or "audiobook"
            source_name: Source to use (default: "prowlarr")

        Returns:
            List of Release objects sorted by quality
        """
        try:
            source = get_source(source_name)

            logger.info(
                "orchestrator_search",
                book_id=book.id,
                title=book.title,
                author=book.author,
                format_type=format_type,
                source=source_name
            )

            releases = source.search(
                title=book.title,
                author=book.author,
                isbn=book.isbn,
                format_type=format_type
            )

            logger.info(
                "orchestrator_search_complete",
                book_id=book.id,
                releases_found=len(releases),
                top_quality=releases[0].quality_score if releases else 0
            )

            return releases

        except Exception as e:
            logger.error(
                "orchestrator_search_failed",
                book_id=book.id,
                error=str(e)
            )
            return []

    def create_download_task(
        self,
        book: Book,
        release: Release,
        format_type: str
    ) -> Optional[DownloadTask]:
        """
        Create a download task from a release.

        Args:
            book: Book to download
            release: Selected release
            format_type: "ebook" or "audiobook"

        Returns:
            Created DownloadTask or None
        """
        db = self.db_session or SessionLocal()

        try:
            # Store release data as JSON
            import json
            release_data = {
                "source": release.source,
                "title": release.title,
                "download_url": release.download_url,
                "protocol": release.protocol,
                "size_bytes": release.size_bytes,
                "seeders": release.seeders,
                "leechers": release.leechers,
                "indexer": release.indexer,
                "indexer_id": release.indexer_id,
                "category": release.category,
                "format": release.format,
                "language": release.language,
                "quality_score": release.quality_score,
                "metadata": release.metadata,
            }

            # Compute hash from download URL for tracking
            import hashlib
            info_hash = hashlib.sha256(release.download_url.encode()).hexdigest()[:16]

            task = DownloadTask(
                book_id=book.id,
                format=format_type,
                source=release.source,
                release_title=release.title,
                download_url=release.download_url,
                protocol=release.protocol,
                state="queued",
                progress=0.0,
                release_data_json=json.dumps(release_data),
                info_hash=info_hash,
            )

            db.add(task)
            db.commit()
            db.refresh(task)

            logger.info(
                "orchestrator_task_created",
                task_id=task.id,
                book_id=book.id,
                format=format_type,
                protocol=release.protocol,
                quality=release.quality_score
            )

            return task

        except Exception as e:
            logger.error(
                "orchestrator_create_task_failed",
                book_id=book.id,
                error=str(e)
            )
            db.rollback()
            return None

        finally:
            if not self.db_session:
                db.close()

    def start_download(self, task_id: int) -> bool:
        """
        Start a download task in a background thread.

        Args:
            task_id: Download task ID

        Returns:
            True if download started successfully
        """
        db = self.db_session or SessionLocal()

        try:
            task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
            if not task:
                logger.error("orchestrator_task_not_found", task_id=task_id)
                return False

            # Check if already downloading
            if task_id in self._active_downloads:
                logger.warning("orchestrator_already_downloading", task_id=task_id)
                return False

            # Create cancel event
            cancel_event = Event()
            self._active_downloads[task_id] = cancel_event

            # Start download thread
            thread = threading.Thread(
                target=self._execute_download,
                args=(task_id, cancel_event),
                daemon=True
            )
            self._download_threads[task_id] = thread
            thread.start()

            logger.info("orchestrator_download_started", task_id=task_id)
            return True

        except Exception as e:
            logger.error("orchestrator_start_failed", task_id=task_id, error=str(e))
            return False

        finally:
            if not self.db_session:
                db.close()

    def _execute_download(self, task_id: int, cancel_event: Event):
        """
        Execute download in background thread.

        Args:
            task_id: Download task ID
            cancel_event: Event to signal cancellation
        """
        db = SessionLocal()

        try:
            task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
            if not task:
                logger.error("orchestrator_execute_task_not_found", task_id=task_id)
                return

            # Update state to downloading
            task.state = "downloading"
            db.commit()

            # Get appropriate handler
            handler_name = "torrent" if task.protocol == "torrent" else "usenet"
            HandlerClass = get_handler(handler_name)
            handler = HandlerClass(db_session=db)

            # Progress callback
            def progress_callback(progress: float):
                task.progress = progress
                db.commit()

            # Status callback
            def status_callback(status: DownloadStatus):
                task.state = status.state.value
                task.progress = status.progress
                if status.message:
                    task.message = status.message
                if status.client_state:
                    task.client_state = status.client_state
                db.commit()

                logger.info(
                    "orchestrator_download_progress",
                    task_id=task_id,
                    state=status.state.value,
                    progress=status.progress,
                    message=status.message,
                    client_state=status.client_state
                )

            # Execute download
            download_path = handler.download(
                task=task,
                cancel_flag=cancel_event,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )

            if download_path:
                # Success - copy/hardlink to destination
                dest_path = self._copy_to_destination(task, download_path, db)

                # Update task with final path (use dest_path if copy succeeded, otherwise source)
                final_path = dest_path if dest_path else download_path

                task.state = "complete"
                task.progress = 100.0
                task.download_path = final_path
                db.commit()

                # Cleanup
                handler.cleanup(task, success=True)

                # Update book availability
                self._update_book_availability(task, db)

                logger.info(
                    "orchestrator_download_complete",
                    task_id=task_id,
                    source_path=download_path,
                    final_path=final_path
                )

            else:
                # Failed
                if task.state != "paused":  # Don't override paused state
                    task.state = "error"
                db.commit()

                # Cleanup
                handler.cleanup(task, success=False)

                logger.error("orchestrator_download_failed", task_id=task_id)

        except Exception as e:
            logger.error("orchestrator_execute_error", task_id=task_id, error=str(e))

            # Update task state
            try:
                task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
                if task:
                    task.state = "error"
                    db.commit()
            except:
                pass

        finally:
            # Clean up
            if task_id in self._active_downloads:
                del self._active_downloads[task_id]
            if task_id in self._download_threads:
                del self._download_threads[task_id]

            db.close()

    def _copy_to_destination(self, task: DownloadTask, source_path: str, db: Session) -> Optional[str]:
        """
        Copy or hardlink downloaded files to the configured destination path.

        Args:
            task: Download task
            source_path: Path where the file was downloaded by the client
            db: Database session

        Returns:
            Destination path if successful, None otherwise
        """
        try:
            # Get configured destination path based on format
            setting_key = f"{task.format}_download_path"  # e.g., "ebook_download_path"
            setting = db.query(AppSettings).filter(AppSettings.key == setting_key).first()

            if not setting or not setting.value:
                logger.warning(
                    "orchestrator_no_destination_configured",
                    task_id=task.id,
                    format=task.format,
                    message=f"No destination path configured for {task.format}. Files will remain in download client location."
                )
                return source_path

            dest_base = setting.value
            if not os.path.exists(dest_base):
                logger.error(
                    "orchestrator_destination_not_found",
                    task_id=task.id,
                    dest_base=dest_base
                )
                return None

            # Determine source file/folder
            source = Path(source_path)
            if not source.exists():
                logger.error(
                    "orchestrator_source_not_found",
                    task_id=task.id,
                    source=source_path
                )
                return None

            # Determine destination name
            if source.is_file():
                dest_name = source.name
                dest_path = Path(dest_base) / dest_name
            else:
                # It's a directory
                dest_name = source.name
                dest_path = Path(dest_base) / dest_name

            # Check if destination already exists
            if dest_path.exists():
                logger.info(
                    "orchestrator_destination_exists",
                    task_id=task.id,
                    dest_path=str(dest_path),
                    message="Destination already exists, skipping copy"
                )
                return str(dest_path)

            # Try to hardlink first (fast, no extra space), fall back to copy
            try:
                if source.is_file():
                    # Hardlink single file
                    os.link(str(source), str(dest_path))
                    logger.info(
                        "orchestrator_hardlink_success",
                        task_id=task.id,
                        source=str(source),
                        dest=str(dest_path)
                    )
                else:
                    # For directories, try to hardlink all files
                    shutil.copytree(str(source), str(dest_path), copy_function=os.link)
                    logger.info(
                        "orchestrator_hardlink_dir_success",
                        task_id=task.id,
                        source=str(source),
                        dest=str(dest_path)
                    )
            except (OSError, PermissionError) as e:
                # Hardlink failed (maybe cross-device), fall back to copy
                logger.info(
                    "orchestrator_hardlink_failed_copying",
                    task_id=task.id,
                    error=str(e),
                    message="Hardlink failed, falling back to copy"
                )

                if source.is_file():
                    shutil.copy2(str(source), str(dest_path))
                    logger.info(
                        "orchestrator_copy_success",
                        task_id=task.id,
                        source=str(source),
                        dest=str(dest_path)
                    )
                else:
                    shutil.copytree(str(source), str(dest_path))
                    logger.info(
                        "orchestrator_copy_dir_success",
                        task_id=task.id,
                        source=str(source),
                        dest=str(dest_path)
                    )

            return str(dest_path)

        except Exception as e:
            logger.error(
                "orchestrator_copy_error",
                task_id=task.id,
                error=str(e)
            )
            return None

    def _update_book_availability(self, task: DownloadTask, db: Session):
        """
        Update book availability after successful download.

        Args:
            task: Completed download task
            db: Database session
        """
        try:
            book = db.query(Book).filter(Book.id == task.book_id).first()
            if not book:
                return

            # Update availability flags
            if task.format == "ebook":
                book.ebook_available = True
            elif task.format == "audiobook":
                book.audiobook_available = True

            # Store the download hashes for duplicate detection
            import json
            import hashlib

            try:
                hashes = json.loads(book.downloaded_release_hashes) if book.downloaded_release_hashes else []
            except (json.JSONDecodeError, TypeError):
                hashes = []

            hashes_to_add = []

            # Add torrent/NZB info hash if available
            if task.info_hash:
                hashes_to_add.append(task.info_hash)

            # Also add URL-based hash for Prowlarr duplicate detection
            if task.download_url:
                url_hash = hashlib.sha256(task.download_url.encode()).hexdigest()[:16]
                hashes_to_add.append(url_hash)

            # Add new hashes
            for hash_val in hashes_to_add:
                if hash_val not in hashes:
                    hashes.append(hash_val)

            book.downloaded_release_hashes = json.dumps(hashes)

            db.commit()

            logger.info(
                "orchestrator_book_updated",
                book_id=book.id,
                format=task.format,
                available=True,
                hash_stored=task.info_hash is not None
            )

        except Exception as e:
            logger.error(
                "orchestrator_update_book_failed",
                task_id=task.id,
                error=str(e)
            )

    def cancel_download(self, task_id: int) -> bool:
        """
        Cancel an active download.

        Args:
            task_id: Download task ID

        Returns:
            True if cancelled successfully
        """
        if task_id not in self._active_downloads:
            logger.warning("orchestrator_cancel_not_active", task_id=task_id)
            return False

        try:
            # Signal cancellation
            cancel_event = self._active_downloads[task_id]
            cancel_event.set()

            logger.info("orchestrator_download_cancelled", task_id=task_id)
            return True

        except Exception as e:
            logger.error("orchestrator_cancel_failed", task_id=task_id, error=str(e))
            return False

    def pause_download(self, task_id: int) -> bool:
        """
        Pause a download.

        Args:
            task_id: Download task ID

        Returns:
            True if paused successfully
        """
        db = self.db_session or SessionLocal()

        try:
            task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
            if not task:
                return False

            # Get handler
            handler_name = "torrent" if task.protocol == "torrent" else "usenet"
            HandlerClass = get_handler(handler_name)
            handler = HandlerClass(db_session=db)

            # Pause in client
            success = handler.pause(task)

            if success:
                task.state = "paused"
                db.commit()

                # Also cancel the monitoring thread
                if task_id in self._active_downloads:
                    self._active_downloads[task_id].set()

            return success

        except Exception as e:
            logger.error("orchestrator_pause_failed", task_id=task_id, error=str(e))
            return False

        finally:
            if not self.db_session:
                db.close()

    def resume_download(self, task_id: int) -> bool:
        """
        Resume a paused download.

        Args:
            task_id: Download task ID

        Returns:
            True if resumed successfully
        """
        db = self.db_session or SessionLocal()

        try:
            task = db.query(DownloadTask).filter(DownloadTask.id == task_id).first()
            if not task:
                return False

            # Get handler
            handler_name = "torrent" if task.protocol == "torrent" else "usenet"
            HandlerClass = get_handler(handler_name)
            handler = HandlerClass(db_session=db)

            # Resume in client
            success = handler.resume(task)

            if success:
                # Restart monitoring
                return self.start_download(task_id)

            return False

        except Exception as e:
            logger.error("orchestrator_resume_failed", task_id=task_id, error=str(e))
            return False

        finally:
            if not self.db_session:
                db.close()

    def search_and_download(
        self,
        book: Book,
        format_type: str = "ebook",
        source_name: str = "prowlarr"
    ) -> Optional[DownloadTask]:
        """
        Complete workflow: search, select best release, and start download.

        Args:
            book: Book to download
            format_type: "ebook" or "audiobook"
            source_name: Source to use (default: "prowlarr")

        Returns:
            Created DownloadTask or None
        """
        # Search for releases
        releases = self.search_releases(book, format_type, source_name)

        if not releases:
            logger.warning(
                "orchestrator_no_releases",
                book_id=book.id,
                format=format_type
            )
            return None

        # Select best release (already sorted by quality)
        best_release = releases[0]

        logger.info(
            "orchestrator_selected_release",
            book_id=book.id,
            release_title=best_release.title,
            quality=best_release.quality_score,
            protocol=best_release.protocol
        )

        # Create download task
        task = self.create_download_task(book, best_release, format_type)

        if not task:
            return None

        # Start download
        success = self.start_download(task.id)

        if not success:
            logger.error("orchestrator_start_download_failed", task_id=task.id)
            return None

        return task

    def get_active_downloads(self) -> List[int]:
        """
        Get list of active download task IDs.

        Returns:
            List of task IDs
        """
        return list(self._active_downloads.keys())

    def is_downloading(self, task_id: int) -> bool:
        """
        Check if a task is currently downloading.

        Args:
            task_id: Download task ID

        Returns:
            True if actively downloading
        """
        return task_id in self._active_downloads

    def get_download_count(self) -> int:
        """
        Get number of active downloads.

        Returns:
            Active download count
        """
        return len(self._active_downloads)
