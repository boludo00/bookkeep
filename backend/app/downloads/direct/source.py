"""
Unified direct download source.

Aggregates results from multiple direct download providers (Anna's Archive,
Z-Library, etc.) and presents them as a single "Direct Download" source.
"""
import asyncio
import concurrent.futures
from typing import List, Optional
import structlog
from sqlalchemy.orm import Session

from .. import Release, ReleaseSource, register_source
from .providers import DirectProvider, DirectSearchResult, AnnasArchiveProvider, ZLibraryProvider
from ...models import DirectDownloadSettings

logger = structlog.get_logger()


@register_source("direct")
class DirectDownloadSource(ReleaseSource):
    """
    Unified direct download source.

    This source aggregates results from multiple providers (Anna's Archive,
    Z-Library, etc.) and returns them as a unified list. The underlying
    providers are abstracted from the user - all results appear as
    "Direct Download" with no indication of the actual source.

    Usage:
        source = DirectDownloadSource(db_session=db)
        releases = source.search(title="Project Hail Mary", author="Andy Weir")
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize direct download source.

        Loads enabled providers from DirectDownloadSettings in database.

        Args:
            db_session: Database session for loading configuration
        """
        self.db_session = db_session
        self._providers: List[DirectProvider] = []
        self._load_providers()

    def _load_providers(self):
        """Load enabled providers from database settings."""
        if not self.db_session:
            logger.warning("direct_source_no_db_session")
            return

        settings = self.db_session.query(DirectDownloadSettings).first()
        if not settings or not settings.enabled:
            logger.debug("direct_source_disabled")
            return

        # Get FlareSolverr URL if configured
        flaresolverr_url = getattr(settings, 'flaresolverr_url', None)

        # Initialize enabled providers
        if settings.annas_archive_enabled:
            self._providers.append(
                AnnasArchiveProvider(
                    mirror=settings.annas_archive_mirror,
                    language=settings.annas_archive_language,
                    flaresolverr_url=flaresolverr_url,
                )
            )
            logger.debug("direct_provider_loaded", provider="annas_archive")

        if settings.zlibrary_enabled and settings.zlibrary_email:
            self._providers.append(
                ZLibraryProvider(
                    email=settings.zlibrary_email,
                    password=settings.zlibrary_password,
                    domain=settings.zlibrary_domain,
                    flaresolverr_url=flaresolverr_url,
                )
            )
            logger.debug("direct_provider_loaded", provider="zlibrary")

        logger.info("direct_source_initialized", providers_count=len(self._providers))

    @property
    def name(self) -> str:
        return "direct"

    def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"
    ) -> List[Release]:
        """
        Search all enabled providers and return unified results.

        Results are de-duplicated by download URL and sorted by quality score.
        All results appear with source="direct" to hide provider details.

        Args:
            title: Book title to search for
            author: Author name (optional)
            isbn: ISBN (optional)
            format_type: "ebook" or "audiobook"

        Returns:
            List of Release objects with protocol="direct"
        """
        if not self._providers:
            logger.info("direct_search_no_providers")
            return []

        logger.info(
            "direct_search_start",
            title=title,
            author=author,
            isbn=isbn,
            format_type=format_type,
            providers_count=len(self._providers)
        )

        # Run provider searches concurrently using asyncio
        all_results = self._run_async_searches(title, author, isbn, format_type)

        # Flatten and convert to Release objects
        releases = []
        seen_urls = set()

        for result in all_results:
            # De-duplicate by download URL
            if result.download_url in seen_urls:
                continue
            seen_urls.add(result.download_url)

            release = self._convert_to_release(result, format_type)
            releases.append(release)

        # Sort by quality (highest first)
        releases.sort(key=lambda r: r.quality_score, reverse=True)

        logger.info(
            "direct_search_complete",
            title=title,
            total_results=len(releases)
        )

        return releases

    def _run_async_searches(
        self,
        title: str,
        author: Optional[str],
        isbn: Optional[str],
        format_type: str
    ) -> List[DirectSearchResult]:
        """
        Run async provider searches and collect results.

        Uses a thread pool to avoid conflicts with FastAPI's event loop.
        """
        async def gather_results():
            tasks = [
                provider.search(title, author, isbn, format_type)
                for provider in self._providers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        def run_in_thread():
            """Run async code in a new event loop in a separate thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(gather_results())
            finally:
                loop.close()

        # Run in thread pool to avoid event loop conflicts with FastAPI
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            results = future.result(timeout=60)  # 60 second timeout

        # Flatten results, handling exceptions
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "direct_provider_search_failed",
                    provider=self._providers[i].name,
                    error=str(result)
                )
            elif result:
                all_results.extend(result)

        return all_results

    def _convert_to_release(self, result: DirectSearchResult, format_type: str) -> Release:
        """
        Convert provider result to unified Release object.

        All results get source="direct" to hide the underlying provider.
        """
        return Release(
            source="direct",  # Always "direct" - hide provider details
            title=result.title,
            download_url=result.download_url,
            protocol="direct",  # Use "direct" protocol for DirectHandler
            size_bytes=result.size_bytes,
            format=result.format,
            language=result.language,
            quality_score=result.quality_score,
            indexer="Direct Download",  # Generic label shown to user
            info_url=result.info_url,
            metadata={
                "provider": result.provider,  # Internal tracking only
                "author": result.author,
                "year": result.year,
            }
        )

    def test_connection(self) -> bool:
        """
        Test if any provider is reachable.

        Returns True if at least one provider is accessible.
        """
        if not self._providers:
            return False

        results = self.test_providers()
        return any(results.values())

    def test_providers(self) -> dict:
        """
        Test each provider individually and return results.

        Returns:
            Dict mapping provider name to success boolean
        """
        if not self._providers:
            return {}

        async def test_all():
            tasks = [provider.test_connection() for provider in self._providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        def run_in_thread():
            """Run async code in a new event loop in a separate thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(test_all())
            finally:
                loop.close()

        # Run in thread pool to avoid event loop conflicts with FastAPI
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            results = future.result(timeout=30)  # 30 second timeout

        # Build provider status dict
        provider_status = {}
        for i, result in enumerate(results):
            provider_name = self._providers[i].name
            if isinstance(result, Exception):
                logger.warning(
                    "direct_provider_test_failed",
                    provider=provider_name,
                    error=str(result)
                )
                provider_status[provider_name] = False
            else:
                provider_status[provider_name] = bool(result)
                if result:
                    logger.info("direct_provider_test_success", provider=provider_name)

        return provider_status

    def get_provider_count(self) -> int:
        """Get number of enabled providers."""
        return len(self._providers)

    def get_provider_names(self) -> List[str]:
        """Get names of enabled providers (for internal use)."""
        return [p.name for p in self._providers]

    async def close(self):
        """Close all provider connections."""
        for provider in self._providers:
            try:
                await provider.close()
            except Exception as e:
                logger.warning("direct_provider_close_error", error=str(e))
