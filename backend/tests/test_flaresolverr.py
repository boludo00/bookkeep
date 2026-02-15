"""Tests for FlareSolverr client and cookie cache."""
import time
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
import httpx

from app.downloads.flaresolverr import (
    FlareSolverrClient,
    FlareSolverrError,
    FlareSolverrResult,
    CookieCache,
    is_cloudflare_challenge,
    solve_sync,
    cookie_cache,
)


class TestIsCloudflareChallenge:
    """Tests for Cloudflare challenge detection."""

    def test_detects_403_status(self):
        assert is_cloudflare_challenge("", 403) is True

    def test_detects_cf_browser_verification(self):
        html = '<div id="cf-browser-verification">Checking...</div>'
        assert is_cloudflare_challenge(html) is True

    def test_detects_cloudflare_text(self):
        html = "<title>Please wait... | Cloudflare</title>"
        assert is_cloudflare_challenge(html) is True

    def test_detects_checking_browser(self):
        html = "<p>Checking your browser before accessing the site.</p>"
        assert is_cloudflare_challenge(html) is True

    def test_detects_ray_id(self):
        html = '<span class="ray id">abc123</span>'
        assert is_cloudflare_challenge(html) is True

    def test_detects_enable_javascript(self):
        html = "<noscript>Please enable JavaScript to continue.</noscript>"
        assert is_cloudflare_challenge(html) is True

    def test_detects_just_a_moment(self):
        html = "<title>Just a moment...</title>"
        assert is_cloudflare_challenge(html) is True

    def test_normal_page_not_detected(self):
        html = "<html><body><h1>Welcome</h1><p>Normal content</p></body></html>"
        assert is_cloudflare_challenge(html) is False

    def test_normal_page_with_200_status(self):
        html = "<html><body>Content</body></html>"
        assert is_cloudflare_challenge(html, 200) is False

    def test_empty_html_not_detected(self):
        assert is_cloudflare_challenge("") is False


class TestCookieCache:
    """Tests for CookieCache."""

    def setup_method(self):
        """Create a fresh cache for each test."""
        self.cache = CookieCache()

    def test_store_and_get(self):
        cookies = [
            {"name": "cf_clearance", "value": "abc123"},
            {"name": "__cf_bm", "value": "xyz789"},
        ]
        self.cache.store("example.com", cookies)
        result = self.cache.get("example.com")
        assert result == {"cf_clearance": "abc123", "__cf_bm": "xyz789"}

    def test_get_empty_for_unknown_domain(self):
        result = self.cache.get("unknown.com")
        assert result == {}

    def test_has_valid(self):
        cookies = [{"name": "cf_clearance", "value": "abc"}]
        self.cache.store("example.com", cookies)
        assert self.cache.has_valid("example.com") is True
        assert self.cache.has_valid("unknown.com") is False

    def test_expiry(self):
        cookies = [{"name": "cf_clearance", "value": "abc"}]
        self.cache.store("example.com", cookies, ttl=0)  # Expire immediately
        time.sleep(0.01)
        assert self.cache.get("example.com") == {}
        assert self.cache.has_valid("example.com") is False

    def test_clear_specific_domain(self):
        self.cache.store("a.com", [{"name": "x", "value": "1"}])
        self.cache.store("b.com", [{"name": "y", "value": "2"}])
        self.cache.clear("a.com")
        assert self.cache.get("a.com") == {}
        assert self.cache.get("b.com") == {"y": "2"}

    def test_clear_all(self):
        self.cache.store("a.com", [{"name": "x", "value": "1"}])
        self.cache.store("b.com", [{"name": "y", "value": "2"}])
        self.cache.clear()
        assert self.cache.get("a.com") == {}
        assert self.cache.get("b.com") == {}

    def test_domain_isolation(self):
        self.cache.store("a.com", [{"name": "x", "value": "1"}])
        self.cache.store("b.com", [{"name": "x", "value": "2"}])
        assert self.cache.get("a.com") == {"x": "1"}
        assert self.cache.get("b.com") == {"x": "2"}

    def test_skips_empty_cookies(self):
        cookies = [
            {"name": "", "value": "abc"},
            {"name": "valid", "value": ""},
            {"name": "good", "value": "val"},
        ]
        self.cache.store("example.com", cookies)
        result = self.cache.get("example.com")
        assert result == {"good": "val"}

    def test_overwrite_existing(self):
        self.cache.store("example.com", [{"name": "x", "value": "1"}])
        self.cache.store("example.com", [{"name": "x", "value": "2"}])
        assert self.cache.get("example.com") == {"x": "2"}


class TestFlareSolverrClient:
    """Tests for FlareSolverrClient async methods."""

    @pytest.mark.asyncio
    async def test_solve_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "url": "https://example.com",
                "status": 200,
                "headers": {"content-type": "text/html"},
                "cookies": [{"name": "cf_clearance", "value": "abc"}],
                "response": "<html>Solved!</html>",
            }
        }

        with patch("app.downloads.flaresolverr.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            client = FlareSolverrClient("http://localhost:8191")
            client._client = mock_instance
            result = await client.solve("https://example.com")

            assert isinstance(result, FlareSolverrResult)
            assert result.html == "<html>Solved!</html>"
            assert result.status == 200
            assert len(result.cookies) == 1
            assert result.cookies[0]["name"] == "cf_clearance"

    @pytest.mark.asyncio
    async def test_solve_error_status(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Challenge not solved"
        }

        with patch("app.downloads.flaresolverr.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            client = FlareSolverrClient("http://localhost:8191")
            client._client = mock_instance

            with pytest.raises(FlareSolverrError, match="Challenge not solved"):
                await client.solve("https://example.com")

    @pytest.mark.asyncio
    async def test_solve_connection_error(self):
        with patch("app.downloads.flaresolverr.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            MockClient.return_value = mock_instance

            client = FlareSolverrClient("http://localhost:8191")
            client._client = mock_instance

            with pytest.raises(FlareSolverrError, match="Cannot connect"):
                await client.solve("https://example.com")

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ok", "sessions": []}

        with patch("app.downloads.flaresolverr.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_instance

            client = FlareSolverrClient("http://localhost:8191")
            client._client = mock_instance
            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        with patch("app.downloads.flaresolverr.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            MockClient.return_value = mock_instance

            client = FlareSolverrClient("http://localhost:8191")
            client._client = mock_instance
            result = await client.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_close(self):
        mock_instance = AsyncMock()
        mock_instance.aclose = AsyncMock()

        client = FlareSolverrClient("http://localhost:8191")
        client._client = mock_instance
        await client.close()

        mock_instance.aclose.assert_called_once()
        assert client._client is None


class TestSolveSync:
    """Tests for the synchronous solve_sync wrapper."""

    def test_solve_sync_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "solution": {
                "url": "https://example.com",
                "status": 200,
                "headers": {},
                "cookies": [{"name": "cf", "value": "123"}],
                "response": "<html>OK</html>",
            }
        }

        with patch("app.downloads.flaresolverr.httpx.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_instance

            result = solve_sync("http://localhost:8191", "https://example.com")
            assert isinstance(result, FlareSolverrResult)
            assert result.html == "<html>OK</html>"

    def test_solve_sync_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Timeout"
        }

        with patch("app.downloads.flaresolverr.httpx.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_instance

            with pytest.raises(FlareSolverrError, match="Timeout"):
                solve_sync("http://localhost:8191", "https://example.com")

    def test_solve_sync_connection_error(self):
        with patch("app.downloads.flaresolverr.httpx.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            MockClient.return_value = mock_instance

            with pytest.raises(FlareSolverrError, match="Cannot connect"):
                solve_sync("http://localhost:8191", "https://example.com")
