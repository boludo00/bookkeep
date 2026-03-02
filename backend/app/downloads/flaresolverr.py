"""
FlareSolverr client for Cloudflare bypass.

FlareSolverr is a proxy server that solves Cloudflare challenges.
It runs as a Docker sidecar and accepts HTTP POST requests with a target URL,
returning the solved HTML and cookies.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()

# Cloudflare challenge indicators (reused from former bypass module)
CLOUDFLARE_INDICATORS = [
    "cf-browser-verification",
    "cloudflare",
    "checking your browser",
    "please wait",
    "ray id",
    "enable javascript",
    "javascript is required",
    "just a moment",
    "verify you are human",
    "verifying you are human",
]


class FlareSolverrError(Exception):
    """Raised when FlareSolverr fails to solve a challenge."""
    pass


@dataclass
class FlareSolverrResult:
    """Result from a FlareSolverr solve request."""
    url: str
    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[Dict] = field(default_factory=list)
    html: str = ""
    user_agent: str = ""


def is_cloudflare_challenge(html: str, status_code: int = 200) -> bool:
    """
    Detect whether a response is a Cloudflare challenge page.

    Args:
        html: Response body text
        status_code: HTTP status code

    Returns:
        True if the response appears to be a Cloudflare challenge
    """
    if status_code == 403:
        return True

    html_lower = html.lower()
    return any(indicator in html_lower for indicator in CLOUDFLARE_INDICATORS)


class FlareSolverrClient:
    """
    Async client for FlareSolverr API.

    Usage:
        client = FlareSolverrClient("http://localhost:8191")
        result = await client.solve("https://example.com")
        print(result.html)
    """

    def __init__(self, base_url: str, max_timeout: int = 60000):
        """
        Initialize FlareSolverr client.

        Args:
            base_url: FlareSolverr URL (e.g., "http://localhost:8191")
            max_timeout: Maximum timeout in milliseconds for solving challenges
        """
        self.base_url = base_url.rstrip("/")
        self.max_timeout = max_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    max(self.max_timeout / 1000 + 10, 30.0),
                    connect=10.0,
                ),
            )
        return self._client

    async def solve(self, url: str) -> FlareSolverrResult:
        """
        Solve a Cloudflare challenge for the given URL.

        Args:
            url: Target URL to solve

        Returns:
            FlareSolverrResult with HTML and cookies

        Raises:
            FlareSolverrError: If solving fails
        """
        client = await self._get_client()

        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self.max_timeout,
        }

        try:
            response = await client.post(
                f"{self.base_url}/v1",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise FlareSolverrError(
                f"FlareSolverr HTTP error: {e.response.status_code}"
            ) from e
        except httpx.ConnectError as e:
            raise FlareSolverrError(
                f"Cannot connect to FlareSolverr at {self.base_url}: {e}"
            ) from e
        except Exception as e:
            raise FlareSolverrError(f"FlareSolverr request failed: {e}") from e

        status = data.get("status", "")
        if status != "ok":
            message = data.get("message", "Unknown error")
            raise FlareSolverrError(f"FlareSolverr error: {message}")

        solution = data.get("solution", {})

        return FlareSolverrResult(
            url=solution.get("url", url),
            status=solution.get("status", 0),
            headers=solution.get("headers", {}),
            cookies=solution.get("cookies", []),
            html=solution.get("response", ""),
            user_agent=solution.get("userAgent", ""),
        )

    async def test_connection(self) -> bool:
        """
        Test connectivity to FlareSolverr.

        Returns:
            True if FlareSolverr is reachable and responding
        """
        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.base_url}/v1",
                json={"cmd": "sessions.list"},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("status") == "ok"
        except Exception as e:
            logger.debug("flaresolverr_test_failed", error=str(e))
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


def solve_sync(flaresolverr_url: str, target_url: str, max_timeout: int = 60000) -> FlareSolverrResult:
    """
    Synchronous wrapper for FlareSolverr solve.

    For use in threaded contexts (e.g., DirectHandler.download).

    Args:
        flaresolverr_url: FlareSolverr base URL
        target_url: URL to solve
        max_timeout: Maximum timeout in milliseconds

    Returns:
        FlareSolverrResult with HTML and cookies

    Raises:
        FlareSolverrError: If solving fails
    """
    payload = {
        "cmd": "request.get",
        "url": target_url,
        "maxTimeout": max_timeout,
    }

    try:
        with httpx.Client(
            timeout=httpx.Timeout(
                max(max_timeout / 1000 + 10, 30.0),
                connect=10.0,
            ),
        ) as client:
            response = client.post(
                f"{flaresolverr_url.rstrip('/')}/v1",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise FlareSolverrError(
            f"FlareSolverr HTTP error: {e.response.status_code}"
        ) from e
    except httpx.ConnectError as e:
        raise FlareSolverrError(
            f"Cannot connect to FlareSolverr at {flaresolverr_url}: {e}"
        ) from e
    except Exception as e:
        raise FlareSolverrError(f"FlareSolverr request failed: {e}") from e

    status = data.get("status", "")
    if status != "ok":
        message = data.get("message", "Unknown error")
        raise FlareSolverrError(f"FlareSolverr error: {message}")

    solution = data.get("solution", {})

    return FlareSolverrResult(
        url=solution.get("url", target_url),
        status=solution.get("status", 0),
        headers=solution.get("headers", {}),
        cookies=solution.get("cookies", []),
        html=solution.get("response", ""),
        user_agent=solution.get("userAgent", ""),
    )


class CookieCache:
    """
    Thread-safe cookie cache for FlareSolverr-solved cookies.

    Stores cookies per domain with TTL-based expiry. Module-level singleton.
    """

    DEFAULT_TTL = 1800  # 30 minutes

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict] = {}  # domain -> {"cookies": {name: value}, "expires": timestamp}

    def store(self, domain: str, cookies: List[Dict], user_agent: str = "", ttl: int = DEFAULT_TTL):
        """
        Store cookies and user-agent from a FlareSolverr solution.

        Args:
            domain: Domain the cookies belong to
            cookies: List of cookie dicts from FlareSolverr (each has "name", "value", etc.)
            user_agent: The user-agent FlareSolverr used (must match on retries)
            ttl: Time-to-live in seconds
        """
        cookie_dict = {}
        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if name and value:
                cookie_dict[name] = value

        with self._lock:
            self._cache[domain] = {
                "cookies": cookie_dict,
                "user_agent": user_agent,
                "expires": time.time() + ttl,
            }

        logger.debug(
            "cookie_cache_stored",
            domain=domain,
            cookie_count=len(cookie_dict),
            cookie_names=list(cookie_dict.keys()),
            has_user_agent=bool(user_agent),
        )

    def get(self, domain: str) -> Dict[str, str]:
        """
        Get cached cookies for a domain.

        Args:
            domain: Domain to look up

        Returns:
            Dict of cookie name to value, or empty dict if not cached/expired
        """
        with self._lock:
            entry = self._cache.get(domain)
            if not entry:
                return {}
            if time.time() > entry["expires"]:
                del self._cache[domain]
                return {}
            return dict(entry["cookies"])

    def get_user_agent(self, domain: str) -> str:
        """
        Get the cached user-agent for a domain.

        DDoS-Guard/Cloudflare cookies are often bound to the user-agent
        that was used during the challenge solve. Using a different UA
        on retries causes the cookies to be rejected.

        Returns:
            The user-agent string, or empty string if not cached/expired
        """
        with self._lock:
            entry = self._cache.get(domain)
            if not entry:
                return ""
            if time.time() > entry["expires"]:
                del self._cache[domain]
                return ""
            return entry.get("user_agent", "")

    def has_valid(self, domain: str) -> bool:
        """Check if valid (non-expired) cookies exist for a domain."""
        with self._lock:
            entry = self._cache.get(domain)
            if not entry:
                return False
            if time.time() > entry["expires"]:
                del self._cache[domain]
                return False
            return True

    def clear(self, domain: Optional[str] = None):
        """
        Clear cached cookies.

        Args:
            domain: If provided, clear only for this domain. Otherwise clear all.
        """
        with self._lock:
            if domain:
                self._cache.pop(domain, None)
            else:
                self._cache.clear()


# Module-level singleton
cookie_cache = CookieCache()
