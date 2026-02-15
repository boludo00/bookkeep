"""
Example usage of the download system.

This demonstrates how to use the download orchestrator to search for
and download books without Readarr.
"""
import time
from app.downloads import DownloadOrchestrator
from app.models import Book
from app.database import SessionLocal


def main():
    """Example download workflow"""

    # Initialize database session
    db = SessionLocal()

    # Initialize orchestrator
    orchestrator = DownloadOrchestrator(db_session=db)

    print("=" * 60)
    print("Book Hound Download System - Example Usage")
    print("=" * 60)
    print()

    # Example 1: Complete workflow (search + download)
    print("Example 1: Complete Workflow (search and download)")
    print("-" * 60)

    # Get a book (replace with actual book ID from your database)
    book = db.query(Book).first()

    if not book:
        print("No books found in database. Please add a book first.")
        db.close()
        return

    print(f"Book: {book.title}")
    print(f"Author: {book.author}")
    print(f"ISBN: {book.isbn or 'N/A'}")
    print()

    # Search and download in one call
    print("Searching for ebook releases and starting download...")
    task = orchestrator.search_and_download(
        book=book,
        format_type="ebook",
        source_name="prowlarr"
    )

    if task:
        print(f"✓ Download started: Task #{task.id}")
        print(f"  Release: {task.release_title}")
        print(f"  Protocol: {task.protocol}")
        print(f"  Source: {task.source}")
        print()

        # Monitor progress
        print("Monitoring download progress...")
        last_progress = -1

        while orchestrator.is_downloading(task.id):
            db.refresh(task)

            if task.progress != last_progress:
                print(f"  [{task.state}] {task.progress:.1f}%")
                last_progress = task.progress

            time.sleep(2)

        # Check final status
        db.refresh(task)
        print()
        if task.state == "complete":
            print(f"✓ Download complete!")
            print(f"  Path: {task.download_path}")
        else:
            print(f"✗ Download failed: {task.state}")
    else:
        print("✗ Failed to start download (no releases found or error)")

    print()
    print()

    # Example 2: Manual workflow (search, select, download separately)
    print("Example 2: Manual Workflow (separate steps)")
    print("-" * 60)

    # Search for releases
    print("Searching for audiobook releases...")
    releases = orchestrator.search_releases(
        book=book,
        format_type="audiobook",
        source_name="prowlarr"
    )

    if releases:
        print(f"✓ Found {len(releases)} releases")
        print()

        # Show top 5 releases
        print("Top releases by quality:")
        for i, release in enumerate(releases[:5], 1):
            size_mb = release.size_bytes / (1024 * 1024)
            print(f"  {i}. {release.title}")
            print(f"     Quality: {release.quality_score:.1f}")
            print(f"     Protocol: {release.protocol}")
            print(f"     Size: {size_mb:.1f} MB")
            print(f"     Format: {release.format or 'unknown'}")
            if release.seeders:
                print(f"     Seeders: {release.seeders}")
            print()

        # Select best release
        best_release = releases[0]
        print(f"Selected: {best_release.title} (quality: {best_release.quality_score:.1f})")
        print()

        # Create download task
        print("Creating download task...")
        task = orchestrator.create_download_task(book, best_release, "audiobook")

        if task:
            print(f"✓ Task created: #{task.id}")
            print()

            # Start download
            print("Starting download...")
            success = orchestrator.start_download(task.id)

            if success:
                print(f"✓ Download started")
                print()

                # You can pause/resume
                print("Demonstrating pause/resume...")
                time.sleep(5)

                print("  Pausing download...")
                orchestrator.pause_download(task.id)
                time.sleep(2)

                db.refresh(task)
                print(f"  State: {task.state}")
                print()

                print("  Resuming download...")
                orchestrator.resume_download(task.id)
                print()

                # Monitor again
                print("Monitoring resumed download...")
                while orchestrator.is_downloading(task.id):
                    db.refresh(task)
                    print(f"  [{task.state}] {task.progress:.1f}%")
                    time.sleep(5)

                db.refresh(task)
                if task.state == "complete":
                    print(f"✓ Download complete: {task.download_path}")
                else:
                    print(f"✗ Download ended: {task.state}")
            else:
                print("✗ Failed to start download")
        else:
            print("✗ Failed to create task")
    else:
        print("✗ No releases found")

    print()
    print()

    # Example 3: Check active downloads
    print("Example 3: Active Downloads")
    print("-" * 60)

    active = orchestrator.get_active_downloads()
    count = orchestrator.get_download_count()

    print(f"Active downloads: {count}")

    if active:
        print("Task IDs:")
        for task_id in active:
            print(f"  - Task #{task_id}")
    else:
        print("  (none)")

    print()
    print("=" * 60)
    print("Examples complete")
    print("=" * 60)

    # Cleanup
    db.close()


if __name__ == "__main__":
    main()
