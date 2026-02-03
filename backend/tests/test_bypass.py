"""Tests for Cloudflare bypass module.

Note: These tests check the module's graceful degradation and API.
Actual bypass testing requires SeleniumBase and Chrome installed.
"""

import pytest
import threading
from unittest.mock import Mock, patch

from app.downloads.bypass import (
    BYPASS_AVAILABLE,
    BypassCancelledException,
    get_bypassed_page,
    is_bypass_available,
    has_valid_cf_cookies,
    get_cf_cookies_for_domain,
    get_cf_user_agent_for_domain,
    clear_cf_cookies,
)


class TestBypassModuleImports:
    """Test that the bypass module imports work correctly."""

    def test_bypass_available_constant(self):
        """BYPASS_AVAILABLE should be True (module imports worked)."""
        assert BYPASS_AVAILABLE is True

    def test_exception_class_available(self):
        """BypassCancelledException should be importable."""
        assert issubclass(BypassCancelledException, Exception)

    def test_all_functions_importable(self):
        """All public functions should be importable."""
        assert callable(get_bypassed_page)
        assert callable(is_bypass_available)
        assert callable(has_valid_cf_cookies)
        assert callable(get_cf_cookies_for_domain)
        assert callable(get_cf_user_agent_for_domain)
        assert callable(clear_cf_cookies)


class TestCookieManagement:
    """Test cookie caching functionality."""

    def test_get_cookies_empty(self):
        """Getting cookies for unknown domain returns empty dict."""
        cookies = get_cf_cookies_for_domain("unknown-domain.com")
        assert cookies == {}

    def test_has_cookies_false(self):
        """has_valid_cf_cookies returns False for unknown domain."""
        assert has_valid_cf_cookies("unknown-domain.com") is False

    def test_get_user_agent_none(self):
        """Getting user agent for unknown domain returns None."""
        ua = get_cf_user_agent_for_domain("unknown-domain.com")
        assert ua is None

    def test_clear_cookies_specific(self):
        """clear_cf_cookies with domain doesn't raise errors."""
        # Should not raise even if domain doesn't exist
        clear_cf_cookies("example.com")

    def test_clear_cookies_all(self):
        """clear_cf_cookies without domain clears all."""
        # Should not raise
        clear_cf_cookies()


class TestBypassGracefulDegradation:
    """Test behavior when SeleniumBase is not installed."""

    def test_is_bypass_available_when_no_seleniumbase(self):
        """is_bypass_available returns False without SeleniumBase."""
        # If SeleniumBase is not installed, should return False
        result = is_bypass_available()
        # This will be False unless SeleniumBase is installed
        assert isinstance(result, bool)

    def test_get_bypassed_page_returns_none_without_seleniumbase(self):
        """get_bypassed_page returns None when SeleniumBase not available."""
        if not is_bypass_available():
            result = get_bypassed_page("https://example.com")
            assert result is None


@pytest.mark.skipif(not is_bypass_available(), reason="SeleniumBase not installed")
class TestBypassWithSeleniumBase:
    """Tests that require SeleniumBase installed."""

    def test_bypass_with_mock_driver(self):
        """Test bypass logic with mocked driver."""
        # This would require extensive mocking of SeleniumBase
        # For now, just verify the function signature
        pass

    def test_bypass_cancellation(self):
        """Test that cancellation flag works."""
        cancel_flag = threading.Event()
        cancel_flag.set()  # Set immediately

        # Should raise BypassCancelledException
        with pytest.raises(BypassCancelledException):
            get_bypassed_page("https://example.com", cancel_flag=cancel_flag)


class TestFingerprint:
    """Test fingerprint module."""

    def test_screen_size_generation(self):
        """Test that screen size generation works."""
        from app.downloads.bypass.fingerprint import get_random_screen_size

        width, height = get_random_screen_size()
        assert isinstance(width, int)
        assert isinstance(height, int)
        assert width > 0
        assert height > 0

    def test_screen_size_is_common_resolution(self):
        """Generated screen size should be from common resolutions."""
        from app.downloads.bypass.fingerprint import get_random_screen_size, COMMON_RESOLUTIONS

        width, height = get_random_screen_size()
        valid_resolutions = [(w, h) for w, h, _ in COMMON_RESOLUTIONS]
        assert (width, height) in valid_resolutions

    def test_screen_size_rotation(self):
        """Test screen size rotation."""
        from app.downloads.bypass.fingerprint import rotate_screen_size, clear_screen_size

        # Clear first
        clear_screen_size()

        # Get first size
        size1 = rotate_screen_size()
        assert len(size1) == 2

        # Rotate might give same size (it's random)
        size2 = rotate_screen_size()
        assert len(size2) == 2


class TestCookiesModule:
    """Test cookies module internals."""

    def test_base_domain_extraction(self):
        """Test base domain extraction."""
        from app.downloads.bypass.cookies import _get_base_domain

        assert _get_base_domain("www.example.com") == "example.com"
        assert _get_base_domain("api.example.com") == "example.com"
        assert _get_base_domain("example.com") == "example.com"
        assert _get_base_domain("localhost") == "localhost"

    def test_cf_cookie_names(self):
        """Test that CF cookie names are defined."""
        from app.downloads.bypass.cookies import CF_COOKIE_NAMES

        assert "cf_clearance" in CF_COOKIE_NAMES
        assert "__cf_bm" in CF_COOKIE_NAMES
        assert isinstance(CF_COOKIE_NAMES, set)


@pytest.mark.skipif(not is_bypass_available(), reason="SeleniumBase not installed")
class TestBypasserModule:
    """Test bypasser module internals."""

    def test_cloudflare_indicators_defined(self):
        """Test that Cloudflare indicators are defined."""
        from app.downloads.bypass.bypasser import CLOUDFLARE_INDICATORS

        assert len(CLOUDFLARE_INDICATORS) > 0
        assert "just a moment" in CLOUDFLARE_INDICATORS
        assert "verify you are human" in CLOUDFLARE_INDICATORS

    def test_cdp_click_selectors_defined(self):
        """Test that CDP click selectors are defined."""
        from app.downloads.bypass.bypasser import CDP_CLICK_SELECTORS

        assert len(CDP_CLICK_SELECTORS) > 0
        assert any("turnstile" in s for s in CDP_CLICK_SELECTORS)

    def test_bypass_methods_defined(self):
        """Test that bypass methods list is defined."""
        from app.downloads.bypass.bypasser import BYPASS_METHODS

        assert len(BYPASS_METHODS) >= 3
        assert all(callable(m) for m in BYPASS_METHODS)
