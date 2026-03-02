"""
Anna's Archive provider for direct downloads.

Anna's Archive is a shadow library that aggregates content from multiple sources.
This provider uses web scraping with BeautifulSoup for parsing.
"""
import httpx
from typing import List, Optional
from urllib.parse import quote_plus
import structlog
from bs4 import BeautifulSoup

from .base import DirectProvider, DirectSearchResult
from ...flaresolverr import (
    FlareSolverrClient,
    FlareSolverrError,
    is_cloudflare_challenge,
    cookie_cache,
)

logger = structlog.get_logger()


class AnnasArchiveProvider(DirectProvider):
    """
    Anna's Archive provider using web scraping with BeautifulSoup.

    Uses the table display format for structured parsing of search results.
    """

    DEFAULT_MIRROR = "https://annas-archive.li"
    # Fallback mirrors in case primary is unavailable
    FALLBACK_MIRRORS = [
        "https://annas-archive.org",
        "https://annas-archive.gs",
        "https://annas-archive.se",
    ]

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

    # Category mappings for Anna's Archive
    EBOOK_EXTENSIONS = ["epub", "pdf", "mobi", "azw3", "fb2", "djvu"]
    AUDIOBOOK_EXTENSIONS = ["mp3", "m4b", "m4a", "flac", "ogg"]

    def __init__(
        self,
        mirror: Optional[str] = None,
        timeout: float = 30.0,
        flaresolverr_url: Optional[str] = None,
    ):
        """
        Initialize Anna's Archive provider.

        Args:
            mirror: Optional custom mirror URL
            timeout: Request timeout in seconds
            flaresolverr_url: Optional FlareSolverr URL for Cloudflare bypass
        """
        self.base_url = (mirror or self.DEFAULT_MIRROR).rstrip("/")
        self.timeout = timeout
        self.flaresolverr_url = flaresolverr_url
        self._client: Optional[httpx.AsyncClient] = None
        self._working_mirror: Optional[str] = None

    @property
    def name(self) -> str:
        return "annas_archive"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
        return self._client

    async def _find_working_mirror(self) -> Optional[str]:
        """Find a working mirror from the list."""
        if self._working_mirror:
            return self._working_mirror

        mirrors = [self.base_url] + self.FALLBACK_MIRRORS
        client = await self._get_client()

        for mirror in mirrors:
            try:
                response = await client.get(f"{mirror}/", timeout=10.0)
                if response.status_code == 200:
                    self._working_mirror = mirror
                    logger.info("annas_mirror_found", mirror=mirror)
                    return mirror
            except Exception as e:
                logger.debug("annas_mirror_failed", mirror=mirror, error=str(e))
                continue

        return None

    async def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"
    ) -> List[DirectSearchResult]:
        """
        Search Anna's Archive for books.

        Args:
            title: Book title
            author: Author name (optional)
            isbn: ISBN (optional)
            format_type: "ebook" or "audiobook"

        Returns:
            List of search results
        """
        results = []
        client = await self._get_client()

        # Find a working mirror
        mirror = await self._find_working_mirror()
        if not mirror:
            logger.error("annas_no_working_mirror")
            return []

        # Build search query - prioritize ISBN if available
        if isbn:
            query = isbn
        else:
            query = title
            if author:
                query = f"{title} {author}"

        # Determine file extensions to filter by
        if format_type == "audiobook":
            extensions = self.AUDIOBOOK_EXTENSIONS
        else:
            extensions = self.EBOOK_EXTENSIONS

        try:
            # Build search URL using table display format
            ext_params = "&".join([f"ext={ext}" for ext in extensions[:4]])
            search_url = (
                f"{mirror}/search?"
                f"index=&page=1&display=table"
                f"&acc=aa_download&acc=external_download"
                f"&{ext_params}"
                f"&q={quote_plus(query)}"
            )

            logger.info(
                "annas_search_request",
                url=search_url,
                query=query,
                format_type=format_type,
            )

            # Try with cached cookies first if available
            from urllib.parse import urlparse
            hostname = urlparse(mirror).hostname
            cached_cookies = cookie_cache.get(hostname) if hostname else {}

            response = await client.get(search_url, cookies=cached_cookies or None)
            html_text = response.text

            logger.info(
                "annas_search_response",
                status=response.status_code,
                content_length=len(html_text),
                has_table=("<table" in html_text.lower()),
                has_tbody=("<tbody" in html_text.lower()),
                url=search_url,
            )

            # Check for Cloudflare challenge
            cf_solved = False
            if is_cloudflare_challenge(html_text, response.status_code):
                logger.warning(
                    "annas_cloudflare_blocked",
                    mirror=mirror,
                    status=response.status_code,
                )

                # Try FlareSolverr if configured
                if self.flaresolverr_url:
                    logger.info("annas_trying_flaresolverr", url=search_url)
                    try:
                        fs_client = FlareSolverrClient(self.flaresolverr_url)
                        fs_result = await fs_client.solve(search_url)
                        await fs_client.close()

                        html_text = fs_result.html
                        cf_solved = True

                        # Cache the cookies for future requests
                        if hostname and fs_result.cookies:
                            cookie_cache.store(hostname, fs_result.cookies)

                        logger.info("annas_flaresolverr_success", url=search_url)
                    except FlareSolverrError as e:
                        logger.warning("annas_flaresolverr_failed", error=str(e))
                        self._working_mirror = None
                        return []
                else:
                    self._working_mirror = None
                    return []

            if not cf_solved:
                response.raise_for_status()

            # Parse results from HTML using BeautifulSoup
            results = self._parse_search_results(html_text, format_type, mirror)

            logger.info(
                "annas_search_complete",
                query=query,
                results_count=len(results),
                mirror=mirror
            )

        except httpx.HTTPStatusError as e:
            logger.warning(
                "annas_http_error",
                status=e.response.status_code,
                query=query
            )
        except Exception as e:
            logger.error("annas_search_error", error=str(e), query=query)

        return results

    def _parse_search_results(
        self,
        html: str,
        format_type: str,
        base_url: str
    ) -> List[DirectSearchResult]:
        """
        Parse search results from HTML response using BeautifulSoup.

        Uses the table display format which has structured data in table rows.
        Note: Anna's Archive tables don't have <tbody>, just <table><tr> directly.
        """
        results = []

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            # Fall back to html.parser if lxml not available
            soup = BeautifulSoup(html, "html.parser")

        # Find all table rows - Anna's Archive doesn't use <tbody>
        rows = soup.select("table tr")

        logger.debug("annas_parse_rows_found", count=len(rows))

        if not rows:
            tables = soup.find_all("table")
            logger.debug("annas_tables_found", count=len(tables))
            return results

        seen_ids = set()
        for row in rows[:50]:  # Process up to 50 rows
            # Skip header rows (rows with <th> cells)
            if row.find("th"):
                continue

            cells = row.find_all("td")
            if len(cells) < 10:
                continue

            try:
                result = self._parse_table_row(row, cells, format_type, base_url)
                if result and result.info_url not in seen_ids:
                    seen_ids.add(result.info_url)
                    results.append(result)
                    if len(results) >= 20:
                        break
            except Exception as e:
                logger.debug("annas_row_parse_error", error=str(e))
                continue

        return results

    def _parse_table_row(
        self,
        row,
        cells,
        format_type: str,
        base_url: str
    ) -> Optional[DirectSearchResult]:
        """
        Parse a single table row into a DirectSearchResult.

        Anna's Archive table display structure (12 cells):
        - cells[0]: Thumbnail (empty)
        - cells[1]: Title
        - cells[2]: Author
        - cells[3]: Publisher/Series info
        - cells[4]: Year
        - cells[5]: File path
        - cells[6]: Source badges
        - cells[7]: Language (e.g., "en")
        - cells[8]: Content type (e.g., "Book (fiction)")
        - cells[9]: Format (e.g., "epub", "pdf")
        - cells[10]: Size (e.g., "0.6MB")
        - cells[11]: Empty
        """
        # Get the MD5 link from the row
        md5_link = row.select_one('a[href*="/md5/"]')
        if not md5_link:
            return None

        link_href = md5_link.get("href", "")
        if not link_href:
            return None

        # Extract MD5 hash from the link
        md5_hash = link_href.split("/")[-1]

        # Extract title from cells[1] - get first span's text to avoid concatenation
        title = ""
        if len(cells) > 1:
            title_span = cells[1].find("span")
            if title_span:
                # Get the first text node directly (before any nested elements)
                title = title_span.find(string=True, recursive=False)
                if title:
                    title = title.strip()
                else:
                    title = title_span.get_text(strip=True)
            else:
                title = cells[1].get_text(strip=True)
        if not title or len(title) < 2:
            return None

        # Extract author from cells[2] - get last span to avoid duplicates
        author = None
        if len(cells) > 2:
            author_spans = cells[2].find_all("span")
            if author_spans:
                # Last span usually has the clean author name
                author = author_spans[-1].get_text(strip=True)
            else:
                author = cells[2].get_text(strip=True)
            if author and len(author) < 2:
                author = None

        # Extract year from cells[4]
        year = None
        if len(cells) > 4:
            year_text = cells[4].get_text(strip=True)
            if year_text and year_text.isdigit() and len(year_text) == 4:
                year = int(year_text)

        # Extract language from cells[7]
        language = None
        if len(cells) > 7:
            language = cells[7].get_text(strip=True)
            language = self._normalize_language(language)

        # Extract format from cells[9]
        file_format = None
        if len(cells) > 9:
            file_format = cells[9].get_text(strip=True).lower()

        # Extract size from cells[10]
        size_bytes = 0
        if len(cells) > 10:
            size_text = cells[10].get_text(strip=True)
            size_bytes = self._parse_size(size_text)

        # Validate format against expected types
        if format_type == "ebook":
            valid_formats = self.EBOOK_EXTENSIONS
        else:
            valid_formats = self.AUDIOBOOK_EXTENSIONS

        if not file_format or file_format not in valid_formats:
            # Skip results that don't match the requested format type
            return None

        # Build URLs
        info_url = f"{base_url}/md5/{md5_hash}"
        download_url = info_url  # Will need to fetch the actual download link from the page

        return DirectSearchResult(
            title=title,
            download_url=download_url,
            format=file_format,
            size_bytes=size_bytes,
            author=author,
            language=language,
            year=year,
            quality_score=self._calculate_quality(file_format, size_bytes, format_type),
            provider=self.name,
            info_url=info_url,
        )

    def _normalize_language(self, lang: Optional[str]) -> Optional[str]:
        """Normalize language name to code."""
        if not lang:
            return None

        lang_lower = lang.lower().strip()
        lang_map = {
            "english": "en",
            "en": "en",
            "spanish": "es",
            "es": "es",
            "french": "fr",
            "fr": "fr",
            "german": "de",
            "deutsch": "de",
            "de": "de",
            "italian": "it",
            "italiano": "it",
            "it": "it",
            "portuguese": "pt",
            "pt": "pt",
            "russian": "ru",
            "ru": "ru",
            "chinese": "zh",
            "zh": "zh",
            "japanese": "ja",
            "ja": "ja",
        }
        return lang_map.get(lang_lower, lang_lower[:2] if len(lang_lower) >= 2 else None)

    def _parse_size(self, size_text: str) -> int:
        """Parse size string like '2.5 MB' to bytes."""
        if not size_text:
            return 0

        import re
        size_pattern = re.compile(r'([\d.]+)\s*(KB|MB|GB|B)', re.IGNORECASE)
        match = size_pattern.search(size_text)

        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
            return int(value * multipliers.get(unit, 1))

        return 0

    def _calculate_quality(self, file_format: str, size_bytes: int, format_type: str) -> float:
        """Calculate quality score for ranking."""
        score = 50.0  # Base score

        # Format preferences
        if format_type == "ebook":
            format_scores = {"epub": 20, "azw3": 15, "mobi": 10, "pdf": 5, "fb2": 5}
        else:
            format_scores = {"m4b": 20, "mp3": 10, "m4a": 15, "flac": 18}

        score += format_scores.get(file_format, 0)

        # Size scoring (prefer reasonable sizes)
        if format_type == "ebook":
            # Ebooks: 100KB - 50MB is good
            if 100_000 < size_bytes < 50_000_000:
                score += 10
            elif size_bytes > 100_000_000:  # Over 100MB probably wrong
                score -= 10
        else:
            # Audiobooks: 50MB - 2GB is good
            if 50_000_000 < size_bytes < 2_000_000_000:
                score += 10

        return min(100, max(0, score))

    async def test_connection(self) -> bool:
        """Test if Anna's Archive is accessible."""
        try:
            mirror = await self._find_working_mirror()
            if mirror:
                logger.info("annas_test_success", mirror=mirror)
                return True
            logger.warning("annas_test_failed", error="No working mirror found")
            return False
        except Exception as e:
            logger.warning("annas_test_failed", error=str(e))
            return False

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
