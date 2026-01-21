#!/usr/bin/env python3
"""
Script to manually refresh download task states from the download clients.
Useful after backend restarts when orphaned downloads exist.
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import DownloadTask
from app.downloads.clients.qbittorrent import QBittorrentClient
from app.downloads.clients.nzbget import NZBGetClient
from app.config import settings
import structlog

logger = structlog.get_logger()


def refresh_torrent_states(db: Session):
    """Refresh states for torrent downloads."""
    try:
        client = QBittorrentClient(
            base_url=settings.QBITTORRENT_URL,
            username=settings.QBITTORRENT_USERNAME,
            password=settings.QBITTORRENT_PASSWORD
        )

        if not client.test_connection():
            logger.error("Failed to connect to qBittorrent")
            return 0

        # Get all torrents from client
        all_torrents = client.get_all_torrents()
        torrent_map = {t['hash'].lower(): t for t in all_torrents}

        # Find tasks that need updating
        tasks = db.query(DownloadTask).filter(
            DownloadTask.protocol == 'torrent',
            DownloadTask.state.in_(['downloading', 'queued', 'checking', 'paused'])
        ).all()

        updated = 0
        for task in tasks:
            if not task.info_hash:
                continue

            torrent_hash = task.info_hash.lower()
            if torrent_hash in torrent_map:
                torrent = torrent_map[torrent_hash]

                # Update state
                old_state = task.state
                old_client_state = task.client_state

                # Map qBittorrent state to our state
                qb_state = torrent['state'].lower()
                if 'error' in qb_state or 'missing' in qb_state:
                    task.state = 'error'
                elif qb_state in ['pauseddl', 'pausedup']:
                    task.state = 'paused'
                elif qb_state in ['queueddl', 'queuedup']:
                    task.state = 'queued'
                elif qb_state in ['checkingdl', 'checkingup', 'checkingresumedata']:
                    task.state = 'checking'
                elif qb_state in ['downloading', 'metadl', 'forceddl']:
                    task.state = 'downloading'
                elif qb_state in ['uploading', 'forcedup', 'stalledup']:
                    task.state = 'seeding'
                elif torrent['progress'] >= 1.0:
                    task.state = 'complete'

                # Update client_state and progress
                task.client_state = torrent['state']
                task.progress = torrent['progress'] * 100

                if old_state != task.state or old_client_state != task.client_state:
                    logger.info(
                        "Updated task state",
                        task_id=task.id,
                        old_state=old_state,
                        new_state=task.state,
                        old_client_state=old_client_state,
                        new_client_state=task.client_state,
                        progress=task.progress
                    )
                    updated += 1

        db.commit()
        return updated

    except Exception as e:
        logger.error("Error refreshing torrent states", error=str(e))
        return 0


def refresh_usenet_states(db: Session):
    """Refresh states for usenet downloads."""
    try:
        client = NZBGetClient(
            base_url=settings.NZBGET_URL,
            username=settings.NZBGET_USERNAME,
            password=settings.NZBGET_PASSWORD
        )

        if not client.test_connection():
            logger.error("Failed to connect to NZBGet")
            return 0

        # Get all downloads from client
        all_downloads = client.get_all_downloads()
        download_map = {d['nzb_id']: d for d in all_downloads}

        # Find tasks that need updating
        tasks = db.query(DownloadTask).filter(
            DownloadTask.protocol == 'usenet',
            DownloadTask.state.in_(['downloading', 'queued', 'checking', 'paused'])
        ).all()

        updated = 0
        for task in tasks:
            if not task.info_hash:
                continue

            if task.info_hash in download_map:
                download = download_map[task.info_hash]

                # Update state
                old_state = task.state
                old_client_state = task.client_state

                # Map NZBGet state to our state
                nzbget_state = download['state']
                if nzbget_state in ['ERROR', 'FAILED']:
                    task.state = 'error'
                elif nzbget_state == 'PAUSED':
                    task.state = 'paused'
                elif nzbget_state == 'QUEUED':
                    task.state = 'queued'
                elif nzbget_state == 'DOWNLOADING':
                    task.state = 'downloading'
                elif nzbget_state in ['POST_PROCESSING', 'EXTRACTING']:
                    task.state = 'checking'
                elif nzbget_state == 'SUCCESS':
                    task.state = 'complete'

                # Update client_state and progress
                task.client_state = nzbget_state
                task.progress = download['progress']

                if old_state != task.state or old_client_state != task.client_state:
                    logger.info(
                        "Updated task state",
                        task_id=task.id,
                        old_state=old_state,
                        new_state=task.state,
                        old_client_state=old_client_state,
                        new_client_state=task.client_state,
                        progress=task.progress
                    )
                    updated += 1

        db.commit()
        return updated

    except Exception as e:
        logger.error("Error refreshing usenet states", error=str(e))
        return 0


def main():
    """Main entry point."""
    db = SessionLocal()
    try:
        logger.info("Starting download state refresh")

        torrent_updated = refresh_torrent_states(db)
        usenet_updated = refresh_usenet_states(db)

        total_updated = torrent_updated + usenet_updated
        logger.info(
            "Download state refresh complete",
            torrent_updated=torrent_updated,
            usenet_updated=usenet_updated,
            total_updated=total_updated
        )

        print(f"✅ Updated {total_updated} download task(s)")
        print(f"   - Torrents: {torrent_updated}")
        print(f"   - Usenet: {usenet_updated}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
