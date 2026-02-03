"""Core Cloudflare bypass logic using SeleniumBase with CDP mode."""

import os
import random
import threading
import time
import traceback
from threading import Event
from typing import Optional
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

# Import optional dependencies
try:
    from seleniumbase import Driver
    SELENIUMBASE_AVAILABLE = True
except ImportError:
    SELENIUMBASE_AVAILABLE = False
    Driver = None

from . import BypassCancelledException
from .cookies import (
    get_cf_cookies_for_domain,
    has_valid_cf_cookies,
    store_cookies_from_driver,
)
from .fingerprint import get_random_screen_size

# Challenge detection indicators
CLOUDFLARE_INDICATORS = [
    "just a moment",
    "verify you are human",
    "verifying you are human",
    "cloudflare.com/products/turnstile",
]

# CDP click selectors for Cloudflare challenges
CDP_CLICK_SELECTORS = [
    "#turnstile-widget div",      # Cloudflare Turnstile
    "#cf-turnstile div",          # Alternative CF Turnstile
    "iframe[src*='challenges']",  # CF challenge iframe
    "input[type='checkbox']",     # Generic checkbox
    "[class*='checkbox']",        # Class-based checkbox
    "#challenge-running",         # CF challenge indicator
]

# Global lock for driver creation (only one browser at a time)
BYPASS_LOCK = threading.Lock()

# Max retries for bypass attempts
DEFAULT_MAX_RETRIES = 3


def is_bypass_available() -> bool:
    """Check if SeleniumBase is available for bypass."""
    return SELENIUMBASE_AVAILABLE


def _get_page_info(driver) -> tuple[str, str, str]:
    """Extract page title, body text, and current URL safely."""
    try:
        title = driver.get_title().lower()
    except Exception:
        title = ""
    try:
        body = driver.get_text("body").lower()
    except Exception:
        body = ""
    try:
        current_url = driver.get_current_url()
    except Exception:
        current_url = ""
    return title, body, current_url


def _has_cloudflare_patterns(body: str, url: str) -> bool:
    """Check for Cloudflare-specific patterns in body or URL."""
    return "cf-" in body or "cloudflare" in url.lower() or "/cdn-cgi/" in url


def _detect_challenge(driver) -> str:
    """Detect if Cloudflare challenge is present. Returns 'cloudflare' or 'none'."""
    try:
        title, body, current_url = _get_page_info(driver)

        # Check for Cloudflare indicators
        for indicator in CLOUDFLARE_INDICATORS:
            if indicator in title or indicator in body:
                logger.debug("cloudflare_indicator_found", indicator=indicator)
                return "cloudflare"

        # Check URL patterns
        if _has_cloudflare_patterns(body, current_url):
            return "cloudflare"

        return "none"
    except Exception as e:
        logger.warning("challenge_detection_error", error=str(e))
        return "none"


def _is_bypassed(driver) -> bool:
    """Check if the protection has been bypassed."""
    try:
        title, body, current_url = _get_page_info(driver)
        body_len = len(body.strip())

        # Long page content = probably bypassed
        if body_len > 100000:
            logger.debug("page_content_long", length=body_len)
            return True

        # Check for protection indicators (means NOT bypassed)
        for indicator in CLOUDFLARE_INDICATORS:
            if indicator in title or indicator in body:
                return False

        # Cloudflare URL patterns
        if _has_cloudflare_patterns(body, current_url):
            logger.debug("cloudflare_patterns_detected")
            return False

        # Page too short = still loading
        if body_len < 50:
            logger.debug("page_content_short", length=body_len)
            return False

        logger.debug("bypass_check_passed", title_preview=title[:100], body_length=body_len)
        return True

    except Exception as e:
        logger.warning("bypass_check_error", error=str(e))
        return False


def _simulate_human_behavior(driver) -> None:
    """Simulate human-like behavior before bypass attempt."""
    try:
        time.sleep(random.uniform(0.5, 1.5))

        if random.random() < 0.3:
            driver.scroll_down(random.randint(20, 50))
            time.sleep(random.uniform(0.2, 0.5))
            driver.scroll_up(random.randint(10, 30))
            time.sleep(random.uniform(0.2, 0.4))
    except Exception as e:
        logger.debug("human_simulation_failed", error=str(e))


def _safe_reconnect(driver) -> None:
    """Safely attempt to reconnect WebDriver after CDP mode."""
    try:
        driver.reconnect()
    except Exception as e:
        logger.debug("reconnect_failed", error=str(e))


def _bypass_method_cdp_solve(driver) -> bool:
    """CDP Mode with solve_captcha() - WebDriver disconnected, no PyAutoGUI.

    CDP Mode disconnects WebDriver during interaction, making detection harder.
    The solve_captcha() method auto-detects challenge type.
    """
    try:
        logger.debug("bypass_attempt_cdp_solve")
        driver.activate_cdp_mode(driver.get_current_url())
        time.sleep(random.uniform(1, 2))

        try:
            driver.cdp.solve_captcha()
            time.sleep(random.uniform(3, 5))
            driver.reconnect()
            time.sleep(random.uniform(1, 2))

            if _is_bypassed(driver):
                return True
        except Exception as e:
            logger.debug("cdp_solve_captcha_failed", error=str(e))
            _safe_reconnect(driver)

        return False
    except Exception as e:
        logger.debug("cdp_solve_failed", error=str(e))
        _safe_reconnect(driver)
        return False


def _bypass_method_cdp_click(driver) -> bool:
    """CDP Mode with native clicking - no PyAutoGUI dependency.

    Uses driver.cdp.click() which is native CDP clicking (SeleniumBase 4.45.6+).
    """
    try:
        logger.debug("bypass_attempt_cdp_click")
        driver.activate_cdp_mode(driver.get_current_url())
        time.sleep(random.uniform(1, 2))

        for selector in CDP_CLICK_SELECTORS:
            try:
                if not driver.cdp.is_element_visible(selector):
                    continue

                logger.debug("cdp_clicking", selector=selector)
                driver.cdp.click(selector)
                time.sleep(random.uniform(2, 4))

                driver.reconnect()
                time.sleep(random.uniform(1, 2))

                if _is_bypassed(driver):
                    return True

                driver.activate_cdp_mode(driver.get_current_url())
                time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                logger.debug("cdp_click_failed", selector=selector, error=str(e))

        _safe_reconnect(driver)
        return _is_bypassed(driver)
    except Exception as e:
        logger.debug("cdp_click_method_failed", error=str(e))
        _safe_reconnect(driver)
        return False


def _bypass_method_wait(driver) -> bool:
    """Simple wait method - sometimes Cloudflare auto-solves."""
    try:
        logger.debug("bypass_attempt_wait")
        _simulate_human_behavior(driver)
        time.sleep(random.uniform(5, 8))
        return _is_bypassed(driver)
    except Exception as e:
        logger.debug("wait_method_failed", error=str(e))
        return False


def _bypass_method_uc_click(driver) -> bool:
    """Use SeleniumBase's uc_click for undetected clicking (no CDP required).

    This method uses the regular Selenium WebDriver with undetected-chromedriver
    patches instead of CDP mode, which works better in headless Docker environments.
    """
    try:
        logger.debug("bypass_attempt_uc_click")

        # Try to find and click challenge elements using regular Selenium
        for selector in CDP_CLICK_SELECTORS:
            try:
                # Try to find element
                elements = driver.find_elements("css selector", selector)
                if elements:
                    for element in elements:
                        try:
                            if element.is_displayed():
                                logger.debug("uc_clicking", selector=selector)
                                # Use JavaScript click for reliability
                                driver.execute_script("arguments[0].click();", element)
                                time.sleep(random.uniform(3, 5))

                                if _is_bypassed(driver):
                                    return True
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("uc_click_selector_failed", selector=selector, error=str(e))

        # Also try iframes
        try:
            iframes = driver.find_elements("tag name", "iframe")
            for iframe in iframes:
                try:
                    src = iframe.get_attribute("src") or ""
                    if "challenge" in src.lower() or "turnstile" in src.lower():
                        driver.switch_to.frame(iframe)
                        time.sleep(random.uniform(0.5, 1))

                        # Look for checkbox or button inside
                        checkboxes = driver.find_elements("css selector", "input[type='checkbox'], button")
                        for cb in checkboxes:
                            if cb.is_displayed():
                                driver.execute_script("arguments[0].click();", cb)
                                time.sleep(random.uniform(3, 5))

                        driver.switch_to.default_content()

                        if _is_bypassed(driver):
                            return True
                except Exception as e:
                    driver.switch_to.default_content()
                    logger.debug("iframe_click_failed", error=str(e))
        except Exception as e:
            logger.debug("iframe_search_failed", error=str(e))

        return _is_bypassed(driver)
    except Exception as e:
        logger.debug("uc_click_method_failed", error=str(e))
        return False


def _bypass_method_refresh_wait(driver) -> bool:
    """Refresh and wait - sometimes helps after failed attempts."""
    try:
        logger.debug("bypass_attempt_refresh_wait")
        driver.refresh()
        time.sleep(random.uniform(2, 3))
        _simulate_human_behavior(driver)
        time.sleep(random.uniform(5, 10))
        return _is_bypassed(driver)
    except Exception as e:
        logger.debug("refresh_wait_failed", error=str(e))
        return False


# Bypass methods in order of preference
# Non-CDP methods first for better headless Docker compatibility
BYPASS_METHODS = [
    _bypass_method_uc_click,       # Non-CDP, works in headless
    _bypass_method_wait,           # Simple wait, no special requirements
    _bypass_method_refresh_wait,   # Refresh and wait
    _bypass_method_cdp_solve,      # CDP mode - may not work in headless Docker
    _bypass_method_cdp_click,      # CDP mode - may not work in headless Docker
]


def _check_cancellation(cancel_flag: Optional[Event], message: str) -> None:
    """Check if cancellation was requested and raise if so."""
    if cancel_flag and cancel_flag.is_set():
        logger.info("bypass_cancelled", message=message)
        raise BypassCancelledException("Bypass cancelled")


def _bypass_cloudflare(driver, max_retries: int = DEFAULT_MAX_RETRIES, cancel_flag: Optional[Event] = None) -> bool:
    """Attempt to bypass Cloudflare protection using multiple methods."""
    for try_count in range(max_retries):
        _check_cancellation(cancel_flag, "Bypass cancelled by user")

        if _is_bypassed(driver):
            if try_count == 0:
                logger.info("page_already_bypassed")
            return True

        challenge_type = _detect_challenge(driver)
        logger.debug("challenge_detected", type=challenge_type, attempt=try_count + 1)

        # No challenge detected but page doesn't look bypassed - wait and retry
        if challenge_type == "none":
            logger.info("no_challenge_waiting")
            time.sleep(random.uniform(2, 3))
            if _is_bypassed(driver):
                return True
            # Try a simple reconnect
            try:
                driver.reconnect()
                time.sleep(random.uniform(1, 2))
                if _is_bypassed(driver):
                    logger.info("bypass_after_reconnect")
                    return True
            except Exception as e:
                logger.debug("reconnect_wait_failed", error=str(e))
            continue

        method = BYPASS_METHODS[try_count % len(BYPASS_METHODS)]
        logger.info("bypass_attempt", attempt=try_count + 1, max=max_retries, method=method.__name__)

        if try_count > 0:
            wait_time = min(random.uniform(2, 4) * try_count, 12)
            logger.info("waiting_before_retry", seconds=round(wait_time, 1))
            for _ in range(int(wait_time)):
                _check_cancellation(cancel_flag, "Bypass cancelled during wait")
                time.sleep(1)
            time.sleep(wait_time - int(wait_time))

        try:
            if method(driver):
                logger.info("bypass_successful", method=method.__name__)
                return True
        except BypassCancelledException:
            raise
        except Exception as e:
            logger.warning("bypass_method_exception", method=method.__name__, error=str(e))

        logger.info("bypass_method_failed", method=method.__name__)

    logger.warning("bypass_max_retries_exceeded")
    return False


def _create_driver() -> Driver:
    """Create a fresh Chrome driver instance for bypass."""
    if not SELENIUMBASE_AVAILABLE:
        raise ImportError("SeleniumBase not installed - bypass unavailable")

    screen_width, screen_height = get_random_screen_size()

    # Check if we have a display (Xvfb or real display)
    display = os.environ.get("DISPLAY")
    use_headless = display is None

    # Docker-compatible Chrome args - extensive list for container environments
    chromium_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--ignore-certificate-errors",
        "--ignore-ssl-errors",
        "--allow-running-insecure-content",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        f"--window-size={screen_width},{screen_height}",
    ]

    logger.debug(
        "creating_chrome_driver",
        screen=f"{screen_width}x{screen_height}",
        display=display,
        headless=use_headless
    )

    if use_headless:
        # No display available - use headless mode
        try:
            driver = Driver(
                uc=True,
                headless2=True,       # New headless mode (Chrome 109+)
                incognito=True,
                locale="en",
                ad_block=True,
                chromium_arg=chromium_args,
            )
        except Exception as e:
            logger.warning("headless2_failed_trying_headless", error=str(e))
            driver = Driver(
                uc=True,
                headless=True,
                incognito=True,
                locale="en",
                ad_block=True,
                chromium_arg=chromium_args,
            )
    else:
        # Display available (Xvfb or real) - use non-headless for CDP support
        logger.info("using_xvfb_display", display=display)
        driver = Driver(
            uc=True,
            headless=False,       # Non-headless with virtual display
            incognito=True,
            locale="en",
            ad_block=True,
            size=f"{screen_width},{screen_height}",
            chromium_arg=chromium_args,
        )

    driver.set_page_load_timeout(60)
    time.sleep(1)
    logger.info("chrome_driver_ready", headless=use_headless)
    return driver


def _quit_driver(driver) -> None:
    """Quit Chrome driver and clean up resources."""
    if driver is None:
        return

    logger.debug("quitting_chrome_driver")

    # Stop CDP browser if in CDP mode
    try:
        if hasattr(driver, 'cdp') and driver.cdp and hasattr(driver.cdp, 'driver'):
            driver.cdp.driver.stop()
            logger.debug("stopped_cdp_browser")
            time.sleep(0.3)
    except Exception as e:
        logger.debug("cdp_stop_failed", error=str(e))

    # Reconnect to re-establish WebDriver control
    try:
        driver.reconnect()
        time.sleep(0.2)
    except Exception as e:
        logger.debug("reconnect_failed", error=str(e))

    # Close window
    try:
        driver.close()
        time.sleep(0.2)
    except Exception as e:
        logger.debug("close_window_failed", error=str(e))

    # Quit driver
    try:
        driver.quit()
    except Exception as e:
        logger.debug("quit_failed", error=str(e))

    logger.debug("chrome_driver_quit")


def get_bypassed_page(url: str, cancel_flag: Optional[Event] = None, max_retries: int = DEFAULT_MAX_RETRIES) -> Optional[str]:
    """Fetch a URL with Cloudflare bypass. Creates fresh Chrome instance for each bypass.

    Args:
        url: The URL to fetch
        cancel_flag: Optional threading.Event to signal cancellation
        max_retries: Maximum number of bypass attempts (default: 3)

    Returns:
        HTML content as string, or None if bypass failed

    Raises:
        BypassCancelledException: If cancel_flag is set during execution
    """
    if not SELENIUMBASE_AVAILABLE:
        logger.error("seleniumbase_not_available")
        return None

    with BYPASS_LOCK:
        hostname = urlparse(url).hostname or ""

        # Check for cached cookies first
        if has_valid_cf_cookies(hostname):
            logger.debug("valid_cookies_exist", domain=hostname)

        driver = None
        try:
            driver = _create_driver()

            logger.debug("opening_url", url=url)
            driver.uc_open_with_reconnect(url, 1.0)

            _check_cancellation(cancel_flag, "Bypass cancelled after page load")

            try:
                logger.debug("page_loaded", url=driver.get_current_url(), title=driver.get_title()[:100])
            except Exception as e:
                logger.debug("page_info_unavailable", error=str(e))

            logger.debug("starting_bypass")
            if _bypass_cloudflare(driver, max_retries=max_retries, cancel_flag=cancel_flag):
                store_cookies_from_driver(driver, url)
                return driver.page_source

            logger.warning("bypass_failed_still_protected")
            try:
                body = driver.get_text("body")
                logger.debug("page_content_preview", preview=body[:500])
            except Exception:
                pass

            return None

        except BypassCancelledException:
            raise
        except Exception as e:
            logger.error("bypass_exception", error=str(e), traceback=traceback.format_exc())
            return None
        finally:
            if driver:
                _quit_driver(driver)
