"""
Base interface for direct download providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DirectSearchResult:
    """
    Result from a direct download provider.

    This is an internal structure - results are converted to Release
    objects before being returned to the user.
    """
    title: str
    download_url: str
    format: str  # epub, pdf, mobi, m4b, mp3, etc.
    size_bytes: int

    # Optional metadata
    author: Optional[str] = None
    language: Optional[str] = None
    year: Optional[int] = None
    quality_score: float = 50.0  # Base score, 0-100

    # Internal tracking (not shown to user)
    provider: str = ""  # Which provider this came from
    info_url: Optional[str] = None  # Link to source page


class DirectProvider(ABC):
    """
    Abstract base for direct download providers.

    Each provider (Anna's Archive, Z-Library, etc.) implements this
    interface to search their source for books.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider identifier (internal use only).

        This is NOT shown to users - all results appear as "Direct Download".
        """
        pass

    @abstractmethod
    async def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"  # "ebook" or "audiobook"
    ) -> List[DirectSearchResult]:
        """
        Search for books matching the query.

        Args:
            title: Book title to search for
            author: Author name (optional, improves matching)
            isbn: ISBN-10 or ISBN-13 (optional, best match)
            format_type: "ebook" or "audiobook"

        Returns:
            List of search results from this provider
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test if the provider is accessible.

        Returns:
            True if provider is reachable and working
        """
        pass

    async def close(self):
        """
        Clean up resources (HTTP clients, etc.).

        Called when provider is no longer needed.
        """
        pass
