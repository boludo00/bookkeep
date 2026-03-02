"""
Z-Library provider for direct downloads.

Z-Library is a shadow library that may require authentication.
Uses their web interface to search and download books.
"""
import re
import httpx
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus
import structlog

from .base import DirectProvider, DirectSearchResult
from ...flaresolverr import (
    FlareSolverrClient,
    FlareSolverrError,
    is_cloudflare_challenge,
    cookie_cache,
)

logger = structlog.get_logger()


class ZLibraryProvider(DirectProvider):
    """
    Z-Library provider using web scraping with optional authentication.

    Can work with or without credentials depending on mirror availability.
    Authentication tokens are cached for the session.
    """

    # Login domain for authentication
    LOGIN_DOMAIN = "singlelogin.re"

    # Known Z-Library mirrors (in order of preference)
    MIRRORS = [
        "z-lib.io",
        "z-lib.gs",
        "zlibrary-global.se",
        "zlibrary.to",
        "z-library.sk",
    ]

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

    # Extension mappings
    EBOOK_EXTENSIONS = ["epub", "mobi", "azw3", "pdf", "fb2"]
    AUDIOBOOK_EXTENSIONS = ["mp3", "m4b", "m4a"]

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        domain: Optional[str] = None,
        timeout: float = 30.0,
        flaresolverr_url: Optional[str] = None,
    ):
        """
        Initialize Z-Library provider.

        Args:
            email: Z-Library account email (optional)
            password: Z-Library account password (optional)
            domain: Custom domain to use
            timeout: Request timeout in seconds
            flaresolverr_url: Optional FlareSolverr URL for Cloudflare bypass
        """
        self.custom_domain = domain
        self.email = email
        self.password = password
        self.timeout = timeout
        self.flaresolverr_url = flaresolverr_url
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False
        self._cookies: Dict[str, str] = {}
        self._user_domain: Optional[str] = None  # Personal domain after login
        self._working_mirror: Optional[str] = None

    @property
    def name(self) -> str:
        return "zlibrary"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            # Keep headers minimal to avoid bot detection
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
        """Find a working Z-Library mirror."""
        if self._working_mirror:
            return self._working_mirror

        # If custom domain specified, try it first
        mirrors_to_try = []
        if self.custom_domain:
            mirrors_to_try.append(self.custom_domain)
        mirrors_to_try.extend(self.MIRRORS)

        client = await self._get_client()

        for mirror in mirrors_to_try:
            try:
                url = f"https://{mirror}/"
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200 and "z-library" in response.text.lower():
                    self._working_mirror = mirror
                    logger.info("zlibrary_mirror_found", mirror=mirror)
                    return mirror
            except Exception as e:
                logger.debug("zlibrary_mirror_failed", mirror=mirror, error=str(e))
                continue

        return None

    async def _authenticate(self) -> bool:
        """
        Authenticate with Z-Library.

        Returns:
            True if authentication successful or not needed
        """
        # If we already have a working mirror without auth, that's fine
        if self._working_mirror and not self.email:
            return True

        if not self.email or not self.password:
            # Try to work without authentication
            mirror = await self._find_working_mirror()
            return mirror is not None

        if self._authenticated and self._user_domain:
            return True

        client = await self._get_client()

        try:
            # Z-Library login endpoint
            login_url = f"https://{self.LOGIN_DOMAIN}/rpc.php"

            response = await client.post(
                login_url,
                data={
                    "isModal": "true",
                    "email": self.email,
                    "password": self.password,
                    "action": "login",
                    "redirectUrl": "",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": f"https://{self.LOGIN_DOMAIN}",
                    "Referer": f"https://{self.LOGIN_DOMAIN}/",
                }
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    data = {}

                if data.get("success"):
                    # Save cookies for authenticated requests
                    self._cookies = dict(response.cookies)

                    # Extract user domain from response
                    # Z-Library assigns a personal domain after login
                    if "user" in data and "personalDomains" in data["user"]:
                        domains = data["user"]["personalDomains"]
                        if domains:
                            self._user_domain = domains[0]
                            self._working_mirror = self._user_domain

                    self._authenticated = True
                    logger.info("zlibrary_auth_success", domain=self._user_domain)
                    return True
                else:
                    logger.warning("zlibrary_auth_failed", response=data)
                    # Fall back to finding a public mirror
                    mirror = await self._find_working_mirror()
                    return mirror is not None
            else:
                logger.warning("zlibrary_auth_http_error", status=response.status_code)
                # Fall back to finding a public mirror
                mirror = await self._find_working_mirror()
                return mirror is not None

        except Exception as e:
            logger.error("zlibrary_auth_error", error=str(e))
            # Fall back to finding a public mirror
            mirror = await self._find_working_mirror()
            return mirror is not None

    async def search(
        self,
        title: str,
        author: Optional[str] = None,
        isbn: Optional[str] = None,
        format_type: str = "ebook"
    ) -> List[DirectSearchResult]:
        """
        Search Z-Library for books.

        Args:
            title: Book title
            author: Author name (optional)
            isbn: ISBN (optional)
            format_type: "ebook" or "audiobook"

        Returns:
            List of search results
        """
        if not await self._authenticate():
            logger.warning("zlibrary_search_no_mirror")
            return []

        results = []
        client = await self._get_client()

        # Build search query
        if isbn:
            query = isbn
        else:
            query = title
            if author:
                query = f"{title} {author}"

        # Determine extensions to filter by
        if format_type == "audiobook":
            extensions = self.AUDIOBOOK_EXTENSIONS
        else:
            extensions = self.EBOOK_EXTENSIONS

        try:
            # Use working mirror (could be personal domain or public mirror)
            mirror = self._user_domain or self._working_mirror
            if not mirror:
                mirror = await self._find_working_mirror()
            if not mirror:
                logger.error("zlibrary_no_mirror_for_search")
                return []

            base_url = f"https://{mirror}"

            # URL encode the query for the path
            encoded_query = quote_plus(query)

            # Build search URL with extension filter
            # Z-Library uses /s/query format
            ext_params = "&".join([f"extensions[]={ext}" for ext in extensions[:3]])
            search_url = f"{base_url}/s/{encoded_query}?{ext_params}"

            logger.debug(
                "zlibrary_search_request",
                url=search_url,
                query=query,
                format_type=format_type,
                mirror=mirror
            )

            response = await client.get(
                search_url,
                cookies=self._cookies if self._cookies else None
            )

            # Check for Cloudflare or access issues
            if is_cloudflare_challenge(response.text, response.status_code):
                logger.warning("zlibrary_cloudflare_blocked", mirror=mirror)

                # Try FlareSolverr if configured
                if self.flaresolverr_url:
                    logger.info("zlibrary_trying_flaresolverr", url=search_url)
                    try:
                        fs_client = FlareSolverrClient(self.flaresolverr_url)
                        fs_result = await fs_client.solve(search_url)
                        await fs_client.close()

                        # Cache cookies for future requests
                        if mirror and fs_result.cookies:
                            cookie_cache.store(mirror, fs_result.cookies)

                        # Parse FlareSolverr HTML instead
                        results = self._parse_search_results(fs_result.html, format_type, base_url)
                        logger.info(
                            "zlibrary_search_complete",
                            query=query,
                            results_count=len(results),
                            via="flaresolverr",
                        )
                        return results
                    except FlareSolverrError as e:
                        logger.warning("zlibrary_flaresolverr_failed", error=str(e))

                self._working_mirror = None
                return []

            response.raise_for_status()

            # Parse results from HTML
            results = self._parse_search_results(response.text, format_type, base_url)

            logger.info(
                "zlibrary_search_complete",
                query=query,
                results_count=len(results)
            )

        except httpx.HTTPStatusError as e:
            logger.warning(
                "zlibrary_http_error",
                status=e.response.status_code,
                query=query
            )
        except Exception as e:
            logger.error("zlibrary_search_error", error=str(e), query=query)

        return results

    def _parse_search_results(
        self,
        html: str,
        format_type: str,
        base_url: str
    ) -> List[DirectSearchResult]:
        """
        Parse search results from HTML response.

        Z-Library uses a structured layout for search results.
        """
        results = []

        # Pattern to find book entries - Z-Library uses /book/ URLs
        # This is a simplified pattern - actual parsing may need adjustment
        book_pattern = re.compile(
            r'href="(/book/\d+/[^"]+)"[^>]*>.*?class="[^"]*bookTitle[^"]*"[^>]*>([^<]+)</a>',
            re.IGNORECASE | re.DOTALL
        )

        # Alternative pattern for simpler structures
        simple_pattern = re.compile(
            r'href="(/book/\d+/[^"]+)"[^>]*>([^<]{3,100})</a>',
            re.IGNORECASE
        )

        matches = book_pattern.findall(html) or simple_pattern.findall(html)

        seen_urls = set()
        for match in matches[:20]:  # Limit to 20 results
            book_path, title_text = match
            title_text = title_text.strip()

            if not title_text or len(title_text) < 3:
                continue

            # Skip duplicates
            if book_path in seen_urls:
                continue
            seen_urls.add(book_path)

            # Extract metadata from surrounding context
            start_idx = html.find(book_path)
            context = html[max(0, start_idx - 300):start_idx + len(book_path) + 500]

            file_format = self._extract_format_from_context(context, format_type)
            size_bytes = self._extract_size_from_context(context)
            language = self._extract_language_from_context(context)
            author = self._extract_author_from_context(context)
            year = self._extract_year_from_context(context)

            if not file_format:
                continue

            # Build URLs
            info_url = f"{base_url}{book_path}"
            # For Z-Library, we need to visit the book page to get download link
            download_url = info_url  # Will need to be resolved later

            result = DirectSearchResult(
                title=title_text,
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
            results.append(result)

        return results

    def _extract_format_from_context(self, context: str, format_type: str) -> Optional[str]:
        """Extract file format from HTML context."""
        context_lower = context.lower()

        if format_type == "audiobook":
            for ext in self.AUDIOBOOK_EXTENSIONS:
                if f".{ext}" in context_lower or f">{ext}<" in context_lower:
                    return ext
        else:
            for ext in self.EBOOK_EXTENSIONS:
                if f".{ext}" in context_lower or f">{ext}<" in context_lower:
                    return ext

        return None

    def _extract_size_from_context(self, context: str) -> int:
        """Extract file size from HTML context."""
        size_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB)', re.IGNORECASE)
        match = size_pattern.search(context)

        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
            return int(value * multipliers.get(unit, 1))

        return 0

    def _extract_language_from_context(self, context: str) -> Optional[str]:
        """Extract language from HTML context."""
        lang_patterns = [
            (r'\b(english)\b', 'en'),
            (r'\b(spanish|español)\b', 'es'),
            (r'\b(french|français)\b', 'fr'),
            (r'\b(german|deutsch)\b', 'de'),
            (r'\b(italian|italiano)\b', 'it'),
            (r'\b(portuguese)\b', 'pt'),
            (r'\b(russian)\b', 'ru'),
        ]

        context_lower = context.lower()
        for pattern, code in lang_patterns:
            if re.search(pattern, context_lower):
                return code

        return None

    def _extract_author_from_context(self, context: str) -> Optional[str]:
        """Extract author name from HTML context."""
        # Look for author patterns
        author_pattern = re.compile(r'class="[^"]*author[^"]*"[^>]*>([^<]+)</a>', re.IGNORECASE)
        match = author_pattern.search(context)
        if match:
            return match.group(1).strip()
        return None

    def _extract_year_from_context(self, context: str) -> Optional[int]:
        """Extract publication year from HTML context."""
        year_pattern = re.compile(r'\b(19\d{2}|20[0-2]\d)\b')
        match = year_pattern.search(context)
        if match:
            return int(match.group(1))
        return None

    def _calculate_quality(self, file_format: str, size_bytes: int, format_type: str) -> float:
        """Calculate quality score for ranking."""
        score = 50.0

        if format_type == "ebook":
            format_scores = {"epub": 20, "azw3": 15, "mobi": 10, "pdf": 5, "fb2": 5}
        else:
            format_scores = {"m4b": 20, "mp3": 10, "m4a": 15}

        score += format_scores.get(file_format, 0)

        # Size scoring
        if format_type == "ebook":
            if 100_000 < size_bytes < 50_000_000:
                score += 10
        else:
            if 50_000_000 < size_bytes < 2_000_000_000:
                score += 10

        return min(100, max(0, score))

    async def test_connection(self) -> bool:
        """Test if Z-Library is accessible."""
        try:
            # Try authentication first if credentials provided
            if self.email and self.password:
                if await self._authenticate():
                    logger.info("zlibrary_test_success", authenticated=True, domain=self._user_domain)
                    return True

            # Fall back to finding a public mirror
            mirror = await self._find_working_mirror()
            if mirror:
                logger.info("zlibrary_test_success", authenticated=False, mirror=mirror)
                return True

            logger.warning("zlibrary_test_failed", error="No accessible mirror found")
            return False
        except Exception as e:
            logger.warning("zlibrary_test_failed", error=str(e))
            return False

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._authenticated = False
        self._cookies = {}
        self._user_domain = None
        self._working_mirror = None
