# Cloudflare Bypass Module

This module provides Cloudflare challenge bypass functionality using SeleniumBase with Chrome in undetected mode.

## Overview

The bypass module is designed to handle Cloudflare Turnstile challenges and other bot protection systems. It uses SeleniumBase's CDP (Chrome DevTools Protocol) mode for stealthier operation.

## Architecture

```
bypass/
├── __init__.py       # Public API and graceful degradation
├── bypasser.py       # Core bypass logic with CDP mode
├── cookies.py        # Thread-safe cookie caching
└── fingerprint.py    # Browser fingerprint randomization
```

## Features

- **CDP Mode**: Uses Chrome DevTools Protocol for stealthier operation
- **Cookie Caching**: Stores Cloudflare cookies to skip bypass on subsequent requests
- **Fingerprint Randomization**: Random screen sizes for detection avoidance
- **Graceful Degradation**: Works without SeleniumBase installed (returns None)
- **Cancellation Support**: Async-friendly with threading.Event cancellation
- **Thread-Safe**: Global lock prevents multiple Chrome instances

## Installation

The module gracefully handles missing dependencies. To enable bypass functionality:

```bash
pip install seleniumbase
```

For Docker deployments, ensure Chrome/Chromium is installed:

```dockerfile
RUN apt-get update && apt-get install -y chromium chromium-driver
```

## Usage

### Basic Example

```python
from app.downloads.bypass import get_bypassed_page, is_bypass_available

if is_bypass_available():
    html = get_bypassed_page("https://example.com/protected")
    if html:
        # Process the HTML...
        pass
```

### With Cancellation

```python
import threading
from app.downloads.bypass import get_bypassed_page, BypassCancelledException

cancel_flag = threading.Event()

try:
    html = get_bypassed_page(
        "https://example.com/protected",
        cancel_flag=cancel_flag,
        max_retries=5
    )
except BypassCancelledException:
    print("Bypass cancelled")
```

### Cookie Reuse

```python
from app.downloads.bypass import has_valid_cf_cookies, get_cf_cookies_for_domain

domain = "example.com"
if has_valid_cf_cookies(domain):
    cookies = get_cf_cookies_for_domain(domain)
    # Use cookies with requests library to skip bypass
    import requests
    response = requests.get(url, cookies=cookies)
```

## API Reference

### Main Functions

#### `get_bypassed_page(url, cancel_flag=None, max_retries=3)`

Fetch a URL with Cloudflare bypass.

**Parameters:**
- `url` (str): The URL to fetch
- `cancel_flag` (Optional[Event]): Threading event for cancellation
- `max_retries` (int): Maximum bypass attempts (default: 3)

**Returns:**
- `Optional[str]`: HTML content or None if failed

**Raises:**
- `BypassCancelledException`: If cancel_flag is set during execution

#### `is_bypass_available()`

Check if SeleniumBase is available.

**Returns:**
- `bool`: True if SeleniumBase is installed

### Cookie Management

#### `has_valid_cf_cookies(domain)`

Check if valid Cloudflare cookies exist for a domain.

**Parameters:**
- `domain` (str): Domain to check

**Returns:**
- `bool`: True if valid cookies exist

#### `get_cf_cookies_for_domain(domain)`

Get stored cookies for a domain.

**Parameters:**
- `domain` (str): Domain to retrieve cookies for

**Returns:**
- `dict[str, str]`: Cookie name -> value mapping

#### `get_cf_user_agent_for_domain(domain)`

Get the User-Agent used during bypass.

**Parameters:**
- `domain` (str): Domain to retrieve UA for

**Returns:**
- `Optional[str]`: User-Agent string or None

#### `clear_cf_cookies(domain=None)`

Clear cached cookies.

**Parameters:**
- `domain` (Optional[str]): Domain to clear, or None for all domains

## Bypass Methods

The module tries multiple bypass strategies in sequence:

1. **CDP solve_captcha()**: Auto-detects and solves challenges
2. **CDP native click**: Clicks challenge elements via CDP
3. **Wait method**: Sometimes Cloudflare auto-solves

Each method uses:
- Random delays to simulate human behavior
- Screen scrolling for interaction simulation
- WebDriver reconnection to avoid detection

## Challenge Detection

The module detects Cloudflare challenges by looking for:

- Text indicators: "just a moment", "verify you are human"
- URL patterns: `/cdn-cgi/`, `cloudflare.com/products/turnstile`
- DOM patterns: `cf-` prefixed elements

## Cookie Storage

Cookies are stored in-memory with thread-safe access:

```python
{
    "example.com": {
        "cf_clearance": {
            "value": "...",
            "domain": ".example.com",
            "expiry": 1234567890,
            ...
        },
        "__cf_bm": {...},
    }
}
```

Protected cookie names:
- `cf_clearance`: Main bypass token
- `__cf_bm`: Bot management
- `cf_chl_2`: Challenge token
- `cf_chl_prog`: Progress token

## Configuration

The module uses sensible defaults and requires minimal configuration:

- **Max Retries**: 3 attempts (configurable per call)
- **Screen Sizes**: Weighted random selection from common resolutions
- **Chrome Args**: Docker-compatible flags (`--no-sandbox`, `--disable-dev-shm-usage`)
- **Timeout**: 60 seconds page load timeout

## Logging

The module uses `structlog` for structured logging:

```python
logger.info("bypass_successful", method="cdp_solve")
logger.debug("cloudflare_indicator_found", indicator="just a moment")
logger.warning("bypass_max_retries_exceeded")
```

## Performance

- **First Request**: 10-30 seconds (Chrome startup + bypass)
- **Cached Cookies**: Instant (direct requests library call)
- **Cookie TTL**: Until expiry (typically 30-60 minutes)

## Limitations

- **Sequential Only**: Global lock prevents parallel bypass attempts
- **Memory Only**: Cookies cleared on app restart
- **Headless Mode**: Always runs in headless mode (no GUI)
- **No Proxy Support**: Currently doesn't support proxy configuration

## Troubleshooting

### "SeleniumBase not installed"

Install the optional dependency:

```bash
pip install seleniumbase
```

### "Chrome not found"

For Docker:

```dockerfile
RUN apt-get update && apt-get install -y chromium chromium-driver
```

### "Bypass max retries exceeded"

- Increase `max_retries` parameter
- Check if site has advanced protection (Kasada, DataDome)
- Verify Chrome/ChromeDriver versions are compatible

### Memory Issues

The module automatically quits Chrome after each bypass to prevent memory leaks. If you see orphan Chrome processes:

```bash
pkill -9 chrome
```

## Comparison with Shelfmark

This is a **simplified** version of shelfmark's bypass module:

**Removed:**
- DDoS-Guard support
- PyAutoGUI methods (uc_gui_handle_captcha, uc_gui_click_captcha)
- Virtual display management (Xvfb)
- FFmpeg screen recording
- DNS pre-resolution
- Proxy support
- 6 bypass methods reduced to 3

**Kept:**
- CDP mode (primary method)
- Cookie caching
- Fingerprint randomization
- Cancellation support
- Docker-compatible Chrome args
- Cloudflare challenge detection

## Future Enhancements

Potential improvements:

- [ ] Add proxy support
- [ ] Persistent cookie storage (Redis)
- [ ] Retry with different fingerprints
- [ ] DDoS-Guard support
- [ ] Parallel bypass queue
- [ ] Metrics/success rate tracking

## References

- [SeleniumBase CDP Mode](https://github.com/seleniumbase/SeleniumBase/tree/master/examples/cdp_mode)
- [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/)
- [Shelfmark Bypasser](https://github.com/yourusername/shelfmark/blob/main/shelfmark/bypass/internal_bypasser.py)
