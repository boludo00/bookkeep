"""Cloudflare bypass module using SeleniumBase."""


class BypassCancelledException(Exception):
    """Raised when bypass operation is cancelled."""
    pass


try:
    from .bypasser import get_bypassed_page, is_bypass_available
    from .cookies import (
        get_cf_cookies_for_domain,
        get_cf_user_agent_for_domain,
        has_valid_cf_cookies,
        clear_cf_cookies,
    )
    BYPASS_AVAILABLE = True
except ImportError:
    BYPASS_AVAILABLE = False
    # Stub functions when SeleniumBase not installed
    def get_bypassed_page(*args, **kwargs):
        return None

    def is_bypass_available():
        return False

    def get_cf_cookies_for_domain(*args, **kwargs):
        return {}

    def get_cf_user_agent_for_domain(*args, **kwargs):
        return None

    def has_valid_cf_cookies(*args, **kwargs):
        return False

    def clear_cf_cookies(*args, **kwargs):
        pass


__all__ = [
    'BypassCancelledException',
    'get_bypassed_page',
    'is_bypass_available',
    'get_cf_cookies_for_domain',
    'get_cf_user_agent_for_domain',
    'has_valid_cf_cookies',
    'clear_cf_cookies',
    'BYPASS_AVAILABLE',
]
