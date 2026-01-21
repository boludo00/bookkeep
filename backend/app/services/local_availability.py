"""
Local file-based availability checker.

Replaces Readarr availability checking by scanning local filesystem
for downloaded books and audiobooks.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session
import structlog

from ..models import AppSettings, Book

logger = structlog.get_logger()


class LocalAvailabilityChecker:
    """Check book availability by scanning local filesystem."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_download_paths(self) -> Dict[str, Optional[str]]:
        """
        Get configured download paths from settings.

        Returns:
            Dict with 'ebook' and 'audiobook' keys
        """
        ebook_setting = self.db.query(AppSettings).filter(
            AppSettings.key == "ebook_download_path"
        ).first()

        audiobook_setting = self.db.query(AppSettings).filter(
            AppSettings.key == "audiobook_download_path"
        ).first()

        return {
            "ebook": ebook_setting.value if ebook_setting else None,
            "audiobook": audiobook_setting.value if audiobook_setting else None,
        }

    def scan_directory(self, path: str) -> Set[str]:
        """
        Scan directory for book files.

        Returns:
            Set of normalized filenames (lowercase, no extension)
        """
        if not path or not os.path.exists(path):
            return set()

        found_files = set()
        ebook_extensions = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbz', '.cbr'}
        audiobook_extensions = {'.m4b', '.mp3', '.m4a', '.flac', '.ogg', '.aac'}
        all_extensions = ebook_extensions | audiobook_extensions

        try:
            for root, dirs, files in os.walk(path):
                for filename in files:
                    file_path = Path(filename)
                    if file_path.suffix.lower() in all_extensions:
                        # Normalize filename: lowercase, no extension
                        normalized = file_path.stem.lower()
                        found_files.add(normalized)
                        logger.debug(
                            "found_file",
                            path=os.path.join(root, filename),
                            normalized=normalized
                        )
        except Exception as e:
            logger.error("scan_directory_error", path=path, error=str(e))

        return found_files

    def normalize_title(self, title: str, author: str = "") -> str:
        """
        Normalize book title for matching.

        Creates a searchable string from title and author.
        """
        # Combine title and author, lowercase, remove special chars
        combined = f"{title} {author}".lower()

        # Remove common punctuation and extra spaces
        for char in [',', '.', ':', ';', '!', '?', "'", '"', '(', ')', '[', ']', '{', '}']:
            combined = combined.replace(char, ' ')

        # Remove extra whitespace
        combined = ' '.join(combined.split())

        return combined

    def check_book_availability(
        self,
        book: Book,
        ebook_files: Optional[Set[str]] = None,
        audiobook_files: Optional[Set[str]] = None
    ) -> Dict[str, bool]:
        """
        Check if a specific book is available locally.

        Args:
            book: Book to check
            ebook_files: Pre-scanned ebook files (optional, will scan if not provided)
            audiobook_files: Pre-scanned audiobook files (optional, will scan if not provided)

        Returns:
            Dict with 'ebook' and 'audiobook' boolean flags
        """
        paths = self.get_download_paths()

        # Scan directories if not provided
        if ebook_files is None and paths['ebook']:
            ebook_files = self.scan_directory(paths['ebook'])
        elif ebook_files is None:
            ebook_files = set()

        if audiobook_files is None and paths['audiobook']:
            audiobook_files = self.scan_directory(paths['audiobook'])
        elif audiobook_files is None:
            audiobook_files = set()

        # Create search strings
        normalized_title = self.normalize_title(book.title, book.author or "")
        title_words = set(normalized_title.split())

        # Check ebook availability
        ebook_available = False
        for file_name in ebook_files:
            file_words = set(file_name.split())
            # If most title words are in filename, consider it a match
            matches = len(title_words & file_words)
            if matches >= min(3, len(title_words)):
                ebook_available = True
                logger.debug(
                    "ebook_match",
                    book_id=book.id,
                    title=book.title,
                    matched_file=file_name
                )
                break

        # Check audiobook availability
        audiobook_available = False
        for file_name in audiobook_files:
            file_words = set(file_name.split())
            matches = len(title_words & file_words)
            if matches >= min(3, len(title_words)):
                audiobook_available = True
                logger.debug(
                    "audiobook_match",
                    book_id=book.id,
                    title=book.title,
                    matched_file=file_name
                )
                break

        return {
            "ebook": ebook_available,
            "audiobook": audiobook_available
        }

    def check_batch_availability(
        self,
        books: List[Book]
    ) -> Dict[int, Dict[str, bool]]:
        """
        Check availability for multiple books efficiently.

        Scans directories once and checks all books against the results.

        Args:
            books: List of books to check

        Returns:
            Dict mapping book_id to availability dict
        """
        paths = self.get_download_paths()

        # Scan directories once
        ebook_files = self.scan_directory(paths['ebook']) if paths['ebook'] else set()
        audiobook_files = self.scan_directory(paths['audiobook']) if paths['audiobook'] else set()

        logger.info(
            "batch_scan_complete",
            ebook_count=len(ebook_files),
            audiobook_count=len(audiobook_files),
            book_count=len(books)
        )

        # Check each book
        results = {}
        for book in books:
            results[book.id] = self.check_book_availability(
                book,
                ebook_files=ebook_files,
                audiobook_files=audiobook_files
            )

        return results

    def update_book_availability(self, book: Book) -> None:
        """
        Update a book's availability flags in the database.

        Args:
            book: Book to update
        """
        availability = self.check_book_availability(book)

        book.ebook_available = availability['ebook']
        book.audiobook_available = availability['audiobook']

        self.db.commit()

        logger.info(
            "book_availability_updated",
            book_id=book.id,
            ebook=availability['ebook'],
            audiobook=availability['audiobook']
        )

    def update_all_availability(self) -> int:
        """
        Update availability for all books in the database.

        Returns:
            Number of books updated
        """
        books = self.db.query(Book).all()
        availability_map = self.check_batch_availability(books)

        updated = 0
        for book in books:
            if book.id in availability_map:
                avail = availability_map[book.id]
                book.ebook_available = avail['ebook']
                book.audiobook_available = avail['audiobook']
                updated += 1

        self.db.commit()

        logger.info("batch_availability_updated", count=updated)

        return updated
