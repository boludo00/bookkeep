"""
Direct HTTP download handler.

Downloads files directly via HTTP/HTTPS without requiring external download clients.
Used for direct download sources like Anna's Archive and Z-Library.
"""
import os
import re
import time
import httpx
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict
from threading import Event
from urllib.parse import urlparse, unquote
import structlog
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    cf_requests = None

from .. import DownloadHandler, DownloadStatus, DownloadState, register_handler
from ...models import DownloadTask as DownloadTaskModel, AppSettings
from sqlalchemy.orm import Session

from ..bypass import (
    get_bypassed_page,
    get_cf_cookies_for_domain,
    get_cf_user_agent_for_domain,
    has_valid_cf_cookies,
    is_bypass_available,
    BypassCancelledException,
    BYPASS_AVAILABLE,
)

logger = structlog.get_logger()


@dataclass
class DownloadSource:
    """Represents a download source with URL and metadata."""
    url: str
    name: str
    source_type: str  # aa-slow-nowait, aa-slow-wait, libgen, zlib, etc.
    priority: int = 50  # Lower is better


@dataclass
class DownloadAttempt:
    """Record of a download attempt for logging."""
    source_name: str
    source_type: str
    url: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    bytes_downloaded: int = 0


@dataclass
class DownloadLog:
    """Complete log of download attempts for a task."""
    task_id: int
    attempts: List[DownloadAttempt] = field(default_factory=list)
    final_result: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def add_attempt(self, source_name: str, source_type: str, url: str) -> DownloadAttempt:
        """Start a new download attempt."""
        attempt = DownloadAttempt(
            source_name=source_name,
            source_type=source_type,
            url=url,
            started_at=datetime.utcnow()
        )
        self.attempts.append(attempt)
        return attempt

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "final_result": self.final_result,
            "attempts": [
                {
                    "source_name": a.source_name,
                    "source_type": a.source_type,
                    "url": a.url[:100] + "..." if len(a.url) > 100 else a.url,
                    "started_at": a.started_at.isoformat(),
                    "ended_at": a.ended_at.isoformat() if a.ended_at else None,
                    "success": a.success,
                    "error": a.error,
                    "bytes_downloaded": a.bytes_downloaded,
                }
                for a in self.attempts
            ]
        }


# Global storage for download logs (in production, this should be in database)
_download_logs: Dict[int, DownloadLog] = {}


def get_download_log(task_id: int) -> Optional[DownloadLog]:
    """Get download log for a task."""
    return _download_logs.get(task_id)


def clear_download_log(task_id: int):
    """Clear download log for a task."""
    _download_logs.pop(task_id, None)


@register_handler("direct")
class DirectHandler(DownloadHandler):
    """
    Direct HTTP download handler with multi-source fallback.

    Downloads files via HTTP/HTTPS streaming with progress tracking.
    Parses download pages to find multiple sources and tries them in order.

    Source Priority (lower is better):
    1. Anna's Archive slow download (no waitlist) - 10
    2. Anna's Archive slow download (with waitlist) - 20
    3. Libgen.li - 30
    4. Z-Library - 40
    5. External/other - 50
    """

    CHUNK_SIZE = 1024 * 64  # 64KB chunks for smoother progress
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    DEFAULT_TIMEOUT = 120.0  # Longer timeout for slow servers
    CONNECT_TIMEOUT = 30.0

    # Source priorities (lower is better)
    SOURCE_PRIORITIES = {
        "aa-slow-nowait": 10,
        "aa-slow-wait": 20,
        "libgen": 30,
        "zlib": 40,
        "aa-fast": 100,  # Requires membership
        "external": 50,
    }

    @property
    def source_name(self) -> str:
        return "direct"

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize direct download handler.

        Args:
            db_session: Database session for looking up download paths
        """
        self.db_session = db_session

    def _get_download_path(self, task: DownloadTaskModel) -> Optional[Path]:
        """Get configured download directory for format type."""
        if not self.db_session:
            logger.warning("direct_no_db_session")
            return None

        setting_key = f"{task.format}_download_path"
        setting = self.db_session.query(AppSettings).filter(
            AppSettings.key == setting_key
        ).first()

        if setting and setting.value:
            path = Path(setting.value)
            if path.exists() and path.is_dir():
                return path
            else:
                logger.warning(
                    "direct_download_path_invalid",
                    path=setting.value,
                    exists=path.exists(),
                    is_dir=path.is_dir() if path.exists() else False
                )

        # Check environment variable fallback
        env_key = setting_key.upper()
        env_value = os.getenv(env_key)
        if env_value:
            path = Path(env_value)
            if path.exists() and path.is_dir():
                return path

        return None

    def _create_client(self):
        """
        Create HTTP client with browser impersonation if available.

        Returns curl_cffi session if available, falls back to httpx.
        """
        if CURL_CFFI_AVAILABLE:
            try:
                # Create curl_cffi session with Chrome browser impersonation
                session = cf_requests.Session(impersonate="chrome")
                session.timeout = self.DEFAULT_TIMEOUT
                session.headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                })
                logger.info("direct_using_curl_cffi", impersonate="chrome")
                return session
            except Exception as e:
                logger.warning("direct_curl_cffi_init_failed", error=str(e), fallback="httpx")
        else:
            logger.info("direct_using_httpx", reason="curl_cffi_unavailable")

        # Fallback to httpx
        return httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(self.DEFAULT_TIMEOUT, connect=self.CONNECT_TIMEOUT),
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _extract_filename(self, url: str, response, task: DownloadTaskModel) -> str:
        """Extract filename from response or generate from task info."""
        # Try Content-Disposition header first
        # Handle both httpx and curl_cffi response headers
        if hasattr(response, "headers"):
            if hasattr(response.headers, "get"):
                content_disp = response.headers.get("content-disposition", "")
            else:
                # curl_cffi uses dict-like access
                content_disp = response.headers.get("content-disposition", "")
        else:
            content_disp = ""
        if "filename=" in content_disp:
            if "filename*=" in content_disp:
                parts = content_disp.split("filename*=")
                if len(parts) > 1:
                    encoded = parts[1].split(";")[0].strip()
                    if "''" in encoded:
                        filename = unquote(encoded.split("''")[1])
                        if filename:
                            return self._sanitize_filename(filename)
            else:
                parts = content_disp.split("filename=")
                if len(parts) > 1:
                    filename = parts[1].split(";")[0].strip().strip('"\'')
                    if filename:
                        return self._sanitize_filename(filename)

        # Fall back to URL path
        path = urlparse(url).path
        filename = unquote(path.split("/")[-1])

        # If no useful filename, generate from task info
        if not filename or filename == "/" or len(filename) < 3 or "." not in filename:
            # Use book title from task
            if task.book and task.book.title:
                base_name = self._sanitize_filename(task.book.title)
            else:
                base_name = f"download_{task.id}"

            # Determine extension from content-type
            if hasattr(response, "headers"):
                content_type = response.headers.get("content-type", "")
            else:
                content_type = ""
            ext = self._get_extension_from_content_type(content_type) or f".{task.format}"
            filename = f"{base_name}{ext}"

        return self._sanitize_filename(filename)

    def _sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
        return filename.strip()

    def _get_extension_from_content_type(self, content_type: str) -> Optional[str]:
        """Map content-type to file extension."""
        mappings = {
            "application/epub+zip": ".epub",
            "application/pdf": ".pdf",
            "application/x-mobipocket-ebook": ".mobi",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4b",
            "audio/x-m4b": ".m4b",
        }
        for mime, ext in mappings.items():
            if mime in content_type.lower():
                return ext
        return None

    def _get_unique_path(self, dest_path: Path) -> Path:
        """Ensure unique filename by appending counter if needed."""
        if not dest_path.exists():
            return dest_path

        counter = 1
        stem = dest_path.stem
        suffix = dest_path.suffix
        parent = dest_path.parent

        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
            if counter > 1000:
                raise ValueError("Could not find unique filename")

    def _parse_annas_archive_sources(self, url: str, client) -> List[DownloadSource]:
        """
        Parse Anna's Archive MD5 page and extract all download sources.

        Returns sources sorted by priority.
        """
        sources: List[DownloadSource] = []

        try:
            logger.info("annas_parsing_md5_page", url=url)

            html = None

            # Make request with browser impersonation if using curl_cffi
            if CURL_CFFI_AVAILABLE and isinstance(client, cf_requests.Session):
                try:
                    response = client.get(
                        url,
                        headers={
                            "Referer": "https://annas-archive.org/",
                        }
                    )
                    html = response.text
                except Exception as e:
                    # Check if it's a 403 error
                    if "403" in str(e) or (hasattr(e, "status_code") and e.status_code == 403):
                        # Try bypass if available
                        if BYPASS_AVAILABLE and is_bypass_available():
                            logger.info("annas_md5_403_attempting_bypass", url=url)
                            try:
                                html = get_bypassed_page(url)
                                if not html:
                                    logger.warning("annas_md5_bypass_failed", url=url)
                            except BypassCancelledException:
                                raise
                            except Exception as bypass_err:
                                logger.warning("annas_md5_bypass_error", url=url, error=str(bypass_err))
                        if not html:
                            raise
                    else:
                        raise
            else:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    html = response.text
                except Exception as e:
                    # Check if it's a 403 error
                    if hasattr(e, "response") and e.response.status_code == 403:
                        # Try bypass if available
                        if BYPASS_AVAILABLE and is_bypass_available():
                            logger.info("annas_md5_403_attempting_bypass", url=url)
                            try:
                                html = get_bypassed_page(url)
                                if not html:
                                    logger.warning("annas_md5_bypass_failed", url=url)
                            except BypassCancelledException:
                                raise
                            except Exception as bypass_err:
                                logger.warning("annas_md5_bypass_error", url=url, error=str(bypass_err))
                        if not html:
                            raise
                    else:
                        raise

            if not html:
                logger.error("annas_md5_no_html", url=url)
                return sources

            soup = BeautifulSoup(html, "lxml")
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # Find all anchor tags and categorize them
            for anchor in soup.find_all("a"):
                href = anchor.get("href", "")
                if not href:
                    continue

                text = anchor.get_text(strip=True).lower()

                # Get the text following the link for waitlist detection
                next_text = ""
                if anchor.next_sibling:
                    next_text = str(anchor.next_sibling).strip().lower()

                # Categorize the link
                source = None

                # Slow download links
                if "/slow_download/" in href:
                    if "slow partner server" in text:
                        if "no waitlist" in next_text or "nowait" in next_text:
                            source = DownloadSource(
                                url=self._make_absolute_url(href, base_url),
                                name=f"Anna's Archive ({text})",
                                source_type="aa-slow-nowait",
                                priority=self.SOURCE_PRIORITIES["aa-slow-nowait"]
                            )
                        elif "waitlist" in next_text:
                            source = DownloadSource(
                                url=self._make_absolute_url(href, base_url),
                                name=f"Anna's Archive ({text})",
                                source_type="aa-slow-wait",
                                priority=self.SOURCE_PRIORITIES["aa-slow-wait"]
                            )
                        else:
                            # Default slow download
                            source = DownloadSource(
                                url=self._make_absolute_url(href, base_url),
                                name=f"Anna's Archive ({text})",
                                source_type="aa-slow-nowait",
                                priority=self.SOURCE_PRIORITIES["aa-slow-nowait"] + 5
                            )

                # Libgen links
                elif "libgen" in href.lower():
                    if "ads.php" in href or "file.php" in href:
                        source = DownloadSource(
                            url=href,
                            name="Libgen.li",
                            source_type="libgen",
                            priority=self.SOURCE_PRIORITIES["libgen"]
                        )

                # Z-Library links
                elif "z-lib" in href.lower() or "zlibrary" in href.lower():
                    if ".onion" not in href:  # Skip Tor links
                        source = DownloadSource(
                            url=href,
                            name="Z-Library",
                            source_type="zlib",
                            priority=self.SOURCE_PRIORITIES["zlib"]
                        )

                # Fast download links (require membership)
                elif "/fast_download/" in href:
                    # Skip fast downloads - they require membership
                    pass

                if source and source.url not in [s.url for s in sources]:
                    sources.append(source)

            # Sort by priority
            sources.sort(key=lambda s: s.priority)

            logger.info(
                "annas_sources_found",
                url=url,
                total=len(sources),
                types={s.source_type for s in sources}
            )

        except Exception as e:
            logger.error("annas_parse_error", url=url, error=str(e))

        return sources

    def _make_absolute_url(self, url: str, base_url: str) -> str:
        """Convert relative URL to absolute."""
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return f"{base_url}{url}"
        return f"{base_url}/{url}"

    def _resolve_libgen_url(self, url: str, client) -> Optional[str]:
        """
        Resolve Libgen.li ads.php page to get actual download link.
        """
        try:
            logger.debug("libgen_resolving", url=url)

            # Make request with browser impersonation if using curl_cffi
            if CURL_CFFI_AVAILABLE and isinstance(client, cf_requests.Session):
                response = client.get(url)
                html = response.text
            else:
                response = client.get(url)
                response.raise_for_status()
                html = response.text

            soup = BeautifulSoup(html, "lxml")
            get_link = soup.select_one('a[href*="get.php"]')

            if get_link:
                href = get_link.get("href", "")
                if href:
                    parsed = urlparse(url)
                    if not href.startswith("http"):
                        href = f"{parsed.scheme}://{parsed.netloc}/{href}"
                    logger.debug("libgen_resolved", url=href)
                    return href

            logger.warning("libgen_no_download_link", url=url)
            return None

        except Exception as e:
            logger.error("libgen_resolve_error", url=url, error=str(e))
            return None

    def _try_download_from_source(
        self,
        source: DownloadSource,
        client,
        dest_dir: Path,
        task: DownloadTaskModel,
        cancel_flag: Event,
        progress_callback: Optional[Callable[[float], None]],
        status_callback: Optional[Callable[[DownloadStatus], None]],
        attempt: DownloadAttempt,
    ) -> Optional[str]:
        """
        Attempt to download from a single source.

        Returns path to downloaded file or None if failed.
        """
        url = source.url

        try:
            # Resolve intermediary pages
            if source.source_type == "libgen":
                if "ads.php" in url:
                    resolved = self._resolve_libgen_url(url, client)
                    if not resolved:
                        attempt.error = "Could not resolve Libgen download link"
                        return None
                    url = resolved

            # Update status - use short source type label for UI
            source_labels = {
                "aa-slow-nowait": "Fast",
                "aa-slow-wait": "Waitlist",
                "libgen": "Libgen",
                "zlib": "Z-Library",
            }
            short_label = source_labels.get(source.source_type, source.source_type)
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.DOWNLOADING,
                    progress=0.0,
                    message=short_label
                ))

            logger.info("direct_trying_source", source=source.name, type=source.source_type, url=url[:80])

            # Determine if we're using curl_cffi or httpx
            is_curl_cffi = CURL_CFFI_AVAILABLE and isinstance(client, cf_requests.Session)

            # Start the download with browser impersonation
            if is_curl_cffi:
                # curl_cffi streaming approach
                response = client.get(
                    url,
                    stream=True,
                    headers={
                        "Referer": "https://annas-archive.org/",
                    },
                    timeout=self.DEFAULT_TIMEOUT,
                )
                # Note: curl_cffi does NOT auto-raise, we check status below
            else:
                # httpx streaming approach
                response = client.stream("GET", url)
                response.__enter__()

            try:
                # Check for HTTP errors - both clients need explicit checking
                status_code = response.status_code
                if status_code == 403:
                    # Try bypass if available
                    if BYPASS_AVAILABLE and is_bypass_available():
                        logger.info("direct_403_attempting_bypass", source=source.name, url=url[:80])

                        if status_callback:
                            status_callback(DownloadStatus(
                                state=DownloadState.QUEUED,
                                progress=0.0,
                                message="Bypassing..."
                            ))

                        try:
                            bypassed_html = get_bypassed_page(url, cancel_flag=cancel_flag)
                            if bypassed_html:
                                # Get cached cookies and user-agent
                                hostname = urlparse(url).hostname
                                cookies = get_cf_cookies_for_domain(hostname)
                                ua = get_cf_user_agent_for_domain(hostname)

                                if cookies:
                                    logger.info("direct_bypass_success", source=source.name, cookies=len(cookies))

                                    # Update client with bypass cookies
                                    if is_curl_cffi:
                                        # For curl_cffi, update session cookies
                                        for cookie_name, cookie_value in cookies.items():
                                            client.cookies.set(cookie_name, cookie_value, domain=hostname)
                                        if ua:
                                            client.headers['User-Agent'] = ua
                                    else:
                                        # For httpx, create new cookies dict
                                        if hasattr(client, 'cookies'):
                                            client.cookies.update(cookies)
                                        if ua and hasattr(client, 'headers'):
                                            client.headers['User-Agent'] = ua

                                    # Close the 403 response and retry the request
                                    if not is_curl_cffi and hasattr(response, "__exit__"):
                                        response.__exit__(None, None, None)

                                    logger.debug("retrying_with_bypass_cookies", source=source.name)

                                    # Retry the download with new cookies
                                    if is_curl_cffi:
                                        response = client.get(
                                            url,
                                            stream=True,
                                            headers={
                                                "Referer": "https://annas-archive.org/",
                                            },
                                            timeout=self.DEFAULT_TIMEOUT,
                                        )
                                    else:
                                        response = client.stream("GET", url)
                                        response.__enter__()

                                    # Check new status
                                    status_code = response.status_code
                                    if status_code >= 400:
                                        attempt.error = f"Still blocked after bypass (HTTP {status_code})"
                                        logger.warning("direct_bypass_retry_failed", source=source.name, status=status_code)
                                        return None

                                    # Continue with normal download flow (don't return, let it fall through)
                                    logger.info("direct_bypass_retry_success", source=source.name)
                                else:
                                    attempt.error = "Bypass succeeded but no cookies extracted"
                                    logger.warning("direct_bypass_no_cookies", source=source.name)
                                    return None
                            else:
                                attempt.error = "Bypass failed to retrieve page"
                                logger.warning("direct_bypass_failed", source=source.name)
                                return None
                        except BypassCancelledException:
                            attempt.error = "Bypass cancelled"
                            return None
                        except Exception as e:
                            attempt.error = f"Bypass error: {str(e)[:50]}"
                            logger.warning("direct_bypass_exception", source=source.name, error=str(e))
                            return None
                    else:
                        attempt.error = "Access denied (403)"
                        logger.warning("direct_source_403", source=source.name, url=url[:80])
                        return None

                if status_code == 429:
                    attempt.error = "Rate limited (429)"
                    logger.warning("direct_source_429", source=source.name, url=url[:80])
                    return None

                if status_code >= 400:
                    attempt.error = f"HTTP {status_code}"
                    logger.warning("direct_source_http_error", source=source.name, status=status_code)
                    return None

                # Check if we got HTML instead of a file
                content_type = response.headers.get("content-type", "") if hasattr(response.headers, "get") else ""
                first_chunk = None  # Store first chunk to not lose data

                if "text/html" in content_type:
                    # Read a bit to check
                    if is_curl_cffi:
                        for chunk in response.iter_content(chunk_size=1024):
                            first_chunk = chunk
                            break
                    else:
                        for chunk in response.iter_bytes(1024):
                            first_chunk = chunk
                            break

                    if first_chunk and (b"<html" in first_chunk.lower() or b"<!doctype" in first_chunk.lower()):
                        attempt.error = "Received HTML instead of file"
                        logger.warning("direct_source_html", source=source.name, url=url[:80])
                        return None

                # Get file info - handle both response types
                if is_curl_cffi:
                    total_size = int(response.headers.get("content-length", 0))
                else:
                    total_size = int(response.headers.get("content-length", 0))

                filename = self._extract_filename(url, response, task)
                dest_path = self._get_unique_path(dest_dir / filename)

                logger.info(
                    "direct_download_starting",
                    source=source.name,
                    filename=filename,
                    size=total_size
                )

                if status_callback:
                    status_callback(DownloadStatus(
                        state=DownloadState.DOWNLOADING,
                        progress=0.0,
                        message=short_label
                    ))

                # Download with progress tracking
                downloaded = 0
                last_progress_update = time.time()
                start_time = time.time()

                with open(dest_path, "wb") as f:
                    # Write first chunk if we read it during HTML detection
                    if first_chunk:
                        f.write(first_chunk)
                        downloaded += len(first_chunk)
                        attempt.bytes_downloaded = downloaded

                    # Use appropriate iterator based on client type
                    if is_curl_cffi:
                        chunk_iterator = response.iter_content(chunk_size=self.CHUNK_SIZE)
                    else:
                        chunk_iterator = response.iter_bytes(self.CHUNK_SIZE)

                    for chunk in chunk_iterator:
                        if cancel_flag.is_set():
                            f.close()
                            if dest_path.exists():
                                dest_path.unlink()
                            attempt.error = "Cancelled"
                            return None

                        f.write(chunk)
                        downloaded += len(chunk)
                        attempt.bytes_downloaded = downloaded

                        # Calculate progress
                        progress = (downloaded / total_size * 100) if total_size > 0 else 0

                        # Throttle progress updates
                        current_time = time.time()
                        if current_time - last_progress_update > 0.5:
                            elapsed = current_time - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0

                            if progress_callback:
                                progress_callback(progress)

                            if status_callback:
                                status_callback(DownloadStatus(
                                    state=DownloadState.DOWNLOADING,
                                    progress=progress,
                                    download_speed=speed,
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_size if total_size > 0 else None,
                                    message=f"Downloading from {source.name}"
                                ))

                            last_progress_update = current_time

                # Verify download
                if dest_path.exists():
                    final_size = dest_path.stat().st_size
                    if total_size > 0 and final_size < total_size * 0.9:
                        attempt.error = f"Incomplete download ({final_size}/{total_size} bytes)"
                        dest_path.unlink()
                        return None

                attempt.success = True
                attempt.ended_at = datetime.utcnow()
                return str(dest_path)

            finally:
                # Close response if using httpx
                if not is_curl_cffi and hasattr(response, "__exit__"):
                    response.__exit__(None, None, None)

        except Exception as e:
            # Handle both httpx and curl_cffi errors
            error_type = type(e).__name__

            # Check for specific HTTP errors
            if "403" in str(e) or (hasattr(e, "response") and hasattr(e.response, "status_code") and e.response.status_code == 403):
                # Try bypass if available and we haven't already tried
                if BYPASS_AVAILABLE and is_bypass_available():
                    logger.info("direct_403_exception_attempting_bypass", source=source.name, url=url[:80])

                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.QUEUED,
                            progress=0.0,
                            message="Bypassing..."
                        ))

                    try:
                        bypassed_html = get_bypassed_page(url, cancel_flag=cancel_flag)
                        if bypassed_html:
                            # Get cached cookies and user-agent
                            hostname = urlparse(url).hostname
                            cookies = get_cf_cookies_for_domain(hostname)
                            ua = get_cf_user_agent_for_domain(hostname)

                            if cookies:
                                logger.info("direct_bypass_success_retry", source=source.name, cookies=len(cookies))
                                # Update client
                                if is_curl_cffi:
                                    for cookie_name, cookie_value in cookies.items():
                                        client.cookies.set(cookie_name, cookie_value, domain=hostname)
                                    if ua:
                                        client.headers['User-Agent'] = ua
                                else:
                                    if hasattr(client, 'cookies'):
                                        client.cookies.update(cookies)
                                    if ua and hasattr(client, 'headers'):
                                        client.headers['User-Agent'] = ua

                                # Recursively retry the download with updated client
                                logger.debug("recursively_retrying_with_bypass", source=source.name)
                                return self._try_download_from_source(
                                    source=source,
                                    client=client,
                                    dest_dir=dest_dir,
                                    task=task,
                                    cancel_flag=cancel_flag,
                                    progress_callback=progress_callback,
                                    status_callback=status_callback,
                                    attempt=attempt,
                                )
                    except BypassCancelledException:
                        attempt.error = "Bypass cancelled"
                        return None
                    except Exception as bypass_err:
                        logger.warning("direct_bypass_exception_retry_failed", source=source.name, error=str(bypass_err))

                attempt.error = "Access denied (403)"
                logger.warning("direct_source_403", source=source.name, url=url[:80])
                return None

            if "429" in str(e) or (hasattr(e, "response") and hasattr(e.response, "status_code") and e.response.status_code == 429):
                attempt.error = "Rate limited (429)"
                logger.warning("direct_source_429", source=source.name, url=url[:80])
                return None

            # Handle timeout errors
            if "timeout" in error_type.lower() or "timeout" in str(e).lower():
                attempt.error = "Timeout"
                logger.warning("direct_source_timeout", source=source.name)
                return None

            # Handle connection errors
            if "connect" in error_type.lower() or "connection" in str(e).lower():
                attempt.error = f"Connection error: {str(e)[:50]}"
                logger.warning("direct_source_connect_error", source=source.name, error=str(e))
                return None

            # Generic HTTP status error from exception
            if hasattr(e, "response") and hasattr(e.response, "status_code"):
                attempt.error = f"HTTP {e.response.status_code}"
                logger.warning("direct_source_http_error", source=source.name, status=e.response.status_code)
                return None

            # Generic fallback for unknown errors
            attempt.error = str(e)[:100]
            logger.error("direct_source_error", source=source.name, error=str(e))
            return None

        finally:
            if not attempt.ended_at:
                attempt.ended_at = datetime.utcnow()

    def download(
        self,
        task: DownloadTaskModel,
        cancel_flag: Event,
        progress_callback: Optional[Callable[[float], None]] = None,
        status_callback: Optional[Callable[[DownloadStatus], None]] = None,
    ) -> Optional[str]:
        """
        Execute direct HTTP download with multi-source fallback.

        Parses the info page to find all available download sources,
        then tries each one in priority order until successful.

        Args:
            task: Download task with URL and metadata
            cancel_flag: Event to check for cancellation
            progress_callback: Call with progress 0.0-100.0
            status_callback: Call with (state, message) updates

        Returns:
            Path to downloaded file, or None if failed/cancelled
        """
        # Initialize download log
        download_log = DownloadLog(task_id=task.id, started_at=datetime.utcnow())
        _download_logs[task.id] = download_log

        download_dir = self._get_download_path(task)
        if not download_dir:
            logger.error("direct_no_download_path", task_id=task.id, format=task.format)
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.ERROR,
                    progress=0.0,
                    message="No path set"
                ))
            download_log.final_result = "error: no download path configured"
            return None

        try:
            with self._create_client() as client:
                # Update status
                if status_callback:
                    status_callback(DownloadStatus(
                        state=DownloadState.QUEUED,
                        progress=0.0,
                        message="Finding sources"
                    ))

                # Parse the info page to get all download sources
                sources = self._parse_annas_archive_sources(task.download_url, client)

                if not sources:
                    logger.warning("direct_no_sources_found", task_id=task.id, url=task.download_url)
                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.ERROR,
                            progress=0.0,
                            message="No sources"
                        ))
                    download_log.final_result = "error: no download sources found"
                    return None

                logger.info(
                    "direct_sources_found",
                    task_id=task.id,
                    count=len(sources),
                    sources=[s.name for s in sources[:5]]
                )

                # Try each source in order
                for i, source in enumerate(sources):
                    if cancel_flag.is_set():
                        download_log.final_result = "cancelled"
                        return None

                    # Create attempt record
                    attempt = download_log.add_attempt(
                        source_name=source.name,
                        source_type=source.source_type,
                        url=source.url
                    )

                    if status_callback:
                        status_callback(DownloadStatus(
                            state=DownloadState.QUEUED,
                            progress=0.0,
                            message=f"Source {i+1}/{len(sources)}"
                        ))

                    # Attempt download
                    result = self._try_download_from_source(
                        source=source,
                        client=client,
                        dest_dir=download_dir,
                        task=task,
                        cancel_flag=cancel_flag,
                        progress_callback=progress_callback,
                        status_callback=status_callback,
                        attempt=attempt,
                    )

                    if result:
                        # Success!
                        download_log.final_result = "success"
                        download_log.completed_at = datetime.utcnow()

                        # Update task
                        task.client_type = "direct"
                        task.client_download_id = result
                        if self.db_session:
                            self.db_session.commit()

                        logger.info(
                            "direct_download_success",
                            task_id=task.id,
                            source=source.name,
                            path=result,
                            attempts=len(download_log.attempts)
                        )

                        if status_callback:
                            status_callback(DownloadStatus(
                                state=DownloadState.COMPLETE,
                                progress=100.0,
                                message="Complete"
                            ))

                        return result

                    # Log the failure and continue to next source
                    logger.info(
                        "direct_source_failed",
                        task_id=task.id,
                        source=source.name,
                        error=attempt.error,
                        remaining=len(sources) - i - 1
                    )

                    # Small delay between attempts
                    time.sleep(1)

                # All sources failed
                download_log.final_result = "error: all sources failed"
                download_log.completed_at = datetime.utcnow()

                if status_callback:
                    status_callback(DownloadStatus(
                        state=DownloadState.ERROR,
                        progress=0.0,
                        message="All sources failed"
                    ))

                logger.error(
                    "direct_all_sources_failed",
                    task_id=task.id,
                    attempts=len(download_log.attempts),
                    errors=[a.error for a in download_log.attempts]
                )

                return None

        except Exception as e:
            download_log.final_result = f"error: {str(e)}"
            download_log.completed_at = datetime.utcnow()
            logger.error("direct_download_error", task_id=task.id, error=str(e))
            if status_callback:
                status_callback(DownloadStatus(
                    state=DownloadState.ERROR,
                    progress=0.0,
                    message="Failed"
                ))
            return None

    def cleanup(self, task: DownloadTaskModel, success: bool):
        """Clean up after download."""
        if not success and task.client_download_id:
            try:
                path = Path(task.client_download_id)
                if path.exists():
                    path.unlink()
                    logger.info("direct_cleanup_removed", task_id=task.id, path=str(path))
            except Exception as e:
                logger.warning("direct_cleanup_error", task_id=task.id, error=str(e))

        # Keep log for a bit for debugging
        # clear_download_log(task.id)

    def pause(self, task: DownloadTaskModel) -> bool:
        """Direct downloads cannot be paused."""
        return False

    def resume(self, task: DownloadTaskModel) -> bool:
        """Direct downloads cannot be resumed."""
        return False

    def cancel(self, task: DownloadTaskModel) -> bool:
        """Cancel is handled via cancel_flag in download()."""
        return True
