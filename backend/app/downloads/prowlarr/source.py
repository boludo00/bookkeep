"""
Prowlarr release source implementation.

Searches for book releases via Prowlarr and returns standardized Release objects.
"""
from typing import List, Optional
import structlog

from ..import Release, ReleaseSource, register_source
from .api import ProwlarrClient
from .utils import (
    extract_format,
    extract_language,
    is_audiobook,
    build_search_queries,
    calculate_quality_score,
)

logger = structlog.get_logger()


@register_source("prowlarr")
class ProwlarrSource(ReleaseSource):
    """
    Prowlarr release source.

    Searches for books across configured indexers via Prowlarr.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
        indexer_ids: Optional[List[int]] = None
    ):
        """
        Initialize Prowlarr source.

        Args:
            base_url: Prowlarr base URL (if None, reads from env/config)
            api_key: Prowlarr API key (if None, reads from env/config)
            timeout: Request timeout in seconds
            indexer_ids: List of indexer IDs to search (None = all indexers)
        """
        # TODO: Read from database settings if not provided
        if base_url is None:
            import os
            base_url = os.getenv("PROWLARR_URL", "http://prowlarr:9696")
        if api_key is None:
            import os
            api_key = os.getenv("PROWLARR_API_KEY", "")

        self.client = ProwlarrClient(base_url, api_key, timeout)
        self.indexer_ids = indexer_ids

    @property
    def name(self) -> str:
        """Source identifier"""
        return "prowlarr"

    def test_connection(self) -> bool:
        """
        Test connection to Prowlarr.

        Returns:
            True if connection succeeds
        """
        return self.client.test_connection()

    def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"
    ) -> List[Release]:
        """
        Search for book releases.

        Args:
            title: Book title
            author: Book author (optional)
            isbn: ISBN (optional)
            format_type: "ebook" or "audiobook"

        Returns:
            List of Release objects
        """
        # Determine categories based on format type
        if format_type == "audiobook":
            categories = [ProwlarrClient.CATEGORY_AUDIOBOOK]
        else:
            categories = [ProwlarrClient.CATEGORY_EBOOK]

        # Build search queries (try ISBN first, then title variations)
        queries = build_search_queries(title, author, isbn)

        all_results = []
        seen_urls = set()  # Track unique results by download URL

        # Try multiple queries to find more results
        # Limit to first 4 queries to avoid excessive API calls
        for query in queries[:4]:
            logger.info(
                "prowlarr_search",
                query=query,
                format_type=format_type,
                categories=categories,
                indexer_ids=self.indexer_ids
            )

            # Search with auto-retry (will try without categories if no results)
            results = self.client.search_with_retry(
                query=query,
                categories=categories,
                indexer_ids=self.indexer_ids,
                limit=100
            )

            if results:
                # Add only unique results (by download URL)
                for result in results:
                    url = result.get("downloadUrl", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)

                # Stop if we have enough results
                if len(all_results) >= 50:
                    break

        if not all_results:
            logger.info(
                "prowlarr_no_results",
                title=title,
                author=author,
                isbn=isbn,
                format_type=format_type
            )
            return []

        # Convert to Release objects with author validation
        releases = []
        for result in all_results:
            release = self._convert_to_release(result, format_type, author)
            if release:
                releases.append(release)

        # Sort by quality score (highest first)
        releases.sort(key=lambda r: r.quality_score, reverse=True)

        logger.info(
            "prowlarr_search_complete",
            title=title,
            releases=len(releases),
            top_score=releases[0].quality_score if releases else 0
        )

        return releases

    def _convert_to_release(
        self,
        prowlarr_result: dict,
        format_type: str,
        expected_author: Optional[str] = None
    ) -> Optional[Release]:
        """
        Convert Prowlarr result to Release object.

        Args:
            prowlarr_result: Raw result from Prowlarr
            format_type: Expected format type ("ebook" or "audiobook")
            expected_author: Expected author name for validation (optional)

        Returns:
            Release object or None if invalid
        """
        title = prowlarr_result.get("title", "")
        if not title:
            return None

        download_url = prowlarr_result.get("downloadUrl", "")
        if not download_url:
            return None

        # Validate author if provided - helps ensure results match the intended book
        if expected_author and not self._author_matches(title, expected_author):
            logger.debug(
                "prowlarr_author_mismatch",
                release_title=title[:100],
                expected_author=expected_author
            )
            return None

        # Parse Prowlarr result
        parsed = ProwlarrClient.parse_prowlarr_result(prowlarr_result)

        # Extract metadata from title
        fmt = extract_format(title)
        language = extract_language(title)

        # Detect if audiobook (from categories or format)
        categories = prowlarr_result.get("categories", [])
        category_ids = [c.get("id") for c in categories if isinstance(c, dict)]
        is_audio = is_audiobook(title, category_ids)

        # Filter by format type
        if format_type == "audiobook" and not is_audio:
            # Skip ebooks when searching for audiobooks
            return None
        elif format_type == "ebook" and is_audio:
            # Skip audiobooks when searching for ebooks
            return None

        # Calculate quality score
        quality = calculate_quality_score(
            parsed,
            preferred_format=fmt,
            min_seeders=1
        )

        # Create Release object
        release = Release(
            source="prowlarr",
            title=title,
            download_url=download_url,
            protocol=parsed["protocol"],
            size_bytes=parsed["size_bytes"],
            seeders=parsed.get("seeders"),
            leechers=parsed.get("leechers"),
            indexer=parsed.get("indexer"),
            indexer_id=parsed.get("indexer_id"),
            category=None,  # We have category_ids in metadata
            format=fmt,
            language=language,
            quality_score=quality,
            metadata={
                **parsed,
                "is_audiobook": is_audio,
                "category_ids": category_ids,
            },
            publish_date=parsed.get("publish_date"),
            info_url=parsed.get("info_url"),
        )

        return release

    def _author_matches(self, title: str, expected_author: str) -> bool:
        """
        Check if expected author name appears in the release title.

        Uses fuzzy matching to handle variations like:
        - "Brandon Sanderson" vs "Sanderson, Brandon"
        - "J.R.R. Tolkien" vs "JRR Tolkien" vs "Tolkien"

        Args:
            title: Release title to check
            expected_author: Expected author name

        Returns:
            True if author appears to match, False otherwise
        """
        if not expected_author:
            return True  # No author to validate against

        title_lower = title.lower()
        author_lower = expected_author.lower()

        # Direct match
        if author_lower in title_lower:
            return True

        # Split author into parts and check for last name
        author_parts = author_lower.replace(",", " ").replace(".", " ").split()
        author_parts = [p.strip() for p in author_parts if p.strip() and len(p.strip()) > 1]

        if not author_parts:
            return True  # Can't validate, allow it

        # Check if last name appears (usually most distinctive)
        # Handle "First Last" and "Last, First" formats
        last_name = author_parts[-1] if len(author_parts) > 1 else author_parts[0]

        # For names like "J.R.R. Tolkien", last name is "tolkien"
        # For names like "Sanderson, Brandon", last name after split is "brandon" but we want "sanderson"
        # So also check the first part if it's longer (likely the surname)
        first_part = author_parts[0]

        # Use the longer part as likely surname (handles "Sanderson, Brandon" -> "sanderson")
        likely_surname = last_name if len(last_name) >= len(first_part) else first_part

        # Check if likely surname appears in title
        if likely_surname in title_lower:
            return True

        # Check if any substantial part of author name appears
        # (at least 4 chars to avoid false positives like "an", "the")
        for part in author_parts:
            if len(part) >= 4 and part in title_lower:
                return True

        return False

    def search_by_isbn(self, isbn: str, format_type: str = "ebook") -> List[Release]:
        """
        Search specifically by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13
            format_type: "ebook" or "audiobook"

        Returns:
            List of Release objects
        """
        return self.search(
            title="",  # Empty title, rely on ISBN
            author=None,
            isbn=isbn,
            format_type=format_type
        )

    def get_indexers(self) -> List[dict]:
        """
        Get list of configured indexers.

        Returns:
            List of indexer info dictionaries
        """
        return self.client.get_indexers()
