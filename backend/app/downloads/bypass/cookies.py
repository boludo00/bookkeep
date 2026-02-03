"""Cloudflare cookie caching and management."""

import threading
import time
from typing import Optional
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

# Cookie storage - shared across bypass attempts
# Structure: {domain: {cookie_name: {value, expiry, ...}}}
_cf_cookies: dict[str, dict] = {}
_cf_cookies_lock = threading.Lock()

# User-Agent storage - Cloudflare ties cf_clearance to the UA that solved the challenge
_cf_user_agents: dict[str, str] = {}

# Protection cookie names we care about (Cloudflare)
CF_COOKIE_NAMES = {'cf_clearance', '__cf_bm', 'cf_chl_2', 'cf_chl_prog'}


def _get_base_domain(domain: str) -> str:
    """Extract base domain from hostname (e.g., 'www.example.com' -> 'example.com')."""
    return '.'.join(domain.split('.')[-2:]) if '.' in domain else domain


def store_cookies_from_driver(driver, url: str) -> None:
    """Extract and store Cloudflare cookies from Chrome after successful bypass."""
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if not domain:
            return

        base_domain = _get_base_domain(domain)
        cookies_found = {}

        for cookie in driver.get_cookies():
            name = cookie.get('name', '')
            # Only extract Cloudflare protection cookies
            if name in CF_COOKIE_NAMES or name.startswith('cf_'):
                cookies_found[name] = {
                    'value': cookie.get('value', ''),
                    'domain': cookie.get('domain', domain),
                    'path': cookie.get('path', '/'),
                    'expiry': cookie.get('expiry'),
                    'secure': cookie.get('secure', True),
                    'httpOnly': cookie.get('httpOnly', True),
                }

        if not cookies_found:
            return

        # Try to capture User-Agent
        try:
            user_agent = driver.execute_script("return navigator.userAgent")
        except Exception:
            user_agent = None

        with _cf_cookies_lock:
            _cf_cookies[base_domain] = cookies_found
            if user_agent:
                _cf_user_agents[base_domain] = user_agent
                logger.debug("stored_user_agent", domain=base_domain, ua_preview=user_agent[:60])
            else:
                logger.debug("no_user_agent_captured", domain=base_domain)

        logger.debug("extracted_cookies", domain=base_domain, count=len(cookies_found))

    except Exception as e:
        logger.debug("cookie_extraction_failed", error=str(e))


def get_cf_cookies_for_domain(domain: str) -> dict[str, str]:
    """Get stored cookies for a domain. Returns empty dict if none available."""
    if not domain:
        return {}

    base_domain = _get_base_domain(domain)

    with _cf_cookies_lock:
        cookies = _cf_cookies.get(base_domain, {})
        if not cookies:
            return {}

        # Check if cf_clearance has expired
        cf_clearance = cookies.get('cf_clearance', {})
        if cf_clearance:
            expiry = cf_clearance.get('expiry')
            if expiry and time.time() > expiry:
                logger.debug("cf_cookies_expired", domain=base_domain)
                _cf_cookies.pop(base_domain, None)
                _cf_user_agents.pop(base_domain, None)
                return {}

        # Return cookie name -> value dict
        return {name: c['value'] for name, c in cookies.items()}


def has_valid_cf_cookies(domain: str) -> bool:
    """Check if we have valid Cloudflare cookies for a domain."""
    return bool(get_cf_cookies_for_domain(domain))


def get_cf_user_agent_for_domain(domain: str) -> Optional[str]:
    """Get the User-Agent that was used during bypass for a domain."""
    if not domain:
        return None
    with _cf_cookies_lock:
        return _cf_user_agents.get(_get_base_domain(domain))


def clear_cf_cookies(domain: str = None) -> None:
    """Clear stored Cloudflare cookies and User-Agent. If domain is None, clear all."""
    with _cf_cookies_lock:
        if domain:
            base_domain = _get_base_domain(domain)
            _cf_cookies.pop(base_domain, None)
            _cf_user_agents.pop(base_domain, None)
            logger.debug("cleared_cookies", domain=base_domain)
        else:
            _cf_cookies.clear()
            _cf_user_agents.clear()
            logger.debug("cleared_all_cookies")
