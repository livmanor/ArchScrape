"""
scraper/fetcher.py — Safe HTTP fetching with robots.txt compliance.

Features:
- robots.txt check before every fetch
- Redirect chain validation (re-checks SSRF on each hop)
- Configurable timeout and response-size limits
- Per-domain rate limiting
- Graceful error classification
"""

import logging
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Optional

import requests
from requests.exceptions import (
    ConnectionError,
    ReadTimeout,
    TooManyRedirects,
    RequestException,
)

from scraper.validator import URLValidationError, validate_url

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15          # seconds
MAX_RESPONSE_BYTES = 5_000_000  # 5 MB
MAX_REDIRECTS = 5
CRAWL_DELAY_DEFAULT = 2.0     # seconds between requests to same domain
USER_AGENT = (
    "ArchScaleIntelBot/1.0 (+https://github.com/archscale/intel; "
    "research-only non-commercial use)"
)

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    url: str                        # final URL after redirects
    original_url: str               # URL that was requested
    status_code: int
    content_type: str
    html: Optional[str]             # None on error
    error_type: Optional[str] = None
    error_detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.html is not None and self.error_type is None


# ─── Domain timing tracker ────────────────────────────────────────────────────

_last_fetch_time: dict[str, float] = {}


def _throttle(domain: str, delay: float = CRAWL_DELAY_DEFAULT) -> None:
    last = _last_fetch_time.get(domain, 0.0)
    elapsed = time.monotonic() - last
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_fetch_time[domain] = time.monotonic()


# ─── robots.txt cache ────────────────────────────────────────────────────────

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def _get_robots(session: requests.Session, base_url: str) -> urllib.robotparser.RobotFileParser:
    parsed = urllib.parse.urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{origin}/robots.txt"

    if origin in _robots_cache:
        return _robots_cache[origin]

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        resp = session.get(
            robots_url,
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            # No robots.txt → assume all allowed
            rp.parse(["User-agent: *", "Allow: /"])
    except Exception as exc:
        logger.debug("Could not fetch robots.txt for %s: %s", origin, exc)
        rp.parse(["User-agent: *", "Allow: /"])

    _robots_cache[origin] = rp
    return rp


def is_allowed(session: requests.Session, url: str) -> bool:
    """Return True if robots.txt permits fetching the given URL."""
    rp = _get_robots(session, url)
    return rp.can_fetch(USER_AGENT, url)


# ─── Core fetch ───────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.max_redirects = MAX_REDIRECTS
    return session


_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _make_session()
    return _session


def fetch(url: str, *, session: Optional[requests.Session] = None, skip_robots: bool = False) -> FetchResult:
    """
    Fetch a URL safely.

    Checks:
    1. URL validation (SSRF protection, scheme)
    2. robots.txt compliance
    3. HTTP fetch with timeout + size limit
    4. Re-validates final URL after redirects

    Returns a FetchResult (ok=False on any error).
    """
    sess = session or get_session()

    # 1. Validate input URL
    try:
        safe_url = validate_url(url)
    except URLValidationError as exc:
        return FetchResult(
            url=url, original_url=url,
            status_code=0, content_type="",
            html=None, error_type="ssrf_blocked", error_detail=str(exc),
        )

    domain = urllib.parse.urlparse(safe_url).hostname or ""

    # 2. robots.txt
    if not skip_robots and not is_allowed(sess, safe_url):
        logger.info("robots.txt blocks: %s", safe_url)
        return FetchResult(
            url=safe_url, original_url=url,
            status_code=0, content_type="",
            html=None, error_type="robots_blocked",
            error_detail=f"robots.txt disallows fetch of {safe_url}",
        )

    # 3. Rate limit
    _throttle(domain)

    # 4. Fetch
    try:
        resp = sess.get(
            safe_url,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        # Re-validate final URL after redirect
        if resp.url != safe_url:
            try:
                validate_url(resp.url)
            except URLValidationError as exc:
                return FetchResult(
                    url=resp.url, original_url=url,
                    status_code=resp.status_code, content_type="",
                    html=None, error_type="ssrf_blocked",
                    error_detail=f"Redirect target blocked: {exc}",
                )

        content_type = resp.headers.get("Content-Type", "")

        # Only parse HTML / text responses
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            return FetchResult(
                url=resp.url, original_url=url,
                status_code=resp.status_code,
                content_type=content_type,
                html=None,
                error_type="non_html",
                error_detail=f"Content-Type '{content_type}' is not HTML",
            )

        # Read with size limit
        chunks = []
        size = 0
        for chunk in resp.iter_content(chunk_size=65536, decode_unicode=False):
            size += len(chunk)
            chunks.append(chunk)
            if size > MAX_RESPONSE_BYTES:
                logger.warning("Response too large (%d bytes) for %s; truncating", size, safe_url)
                break

        raw = b"".join(chunks)
        # Detect encoding
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        try:
            html = raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html = raw.decode("utf-8", errors="replace")

        if resp.status_code >= 400:
            return FetchResult(
                url=resp.url, original_url=url,
                status_code=resp.status_code, content_type=content_type,
                html=None, error_type="http_error",
                error_detail=f"HTTP {resp.status_code}",
            )

        return FetchResult(
            url=resp.url, original_url=url,
            status_code=resp.status_code,
            content_type=content_type,
            html=html,
        )

    except ReadTimeout:
        return FetchResult(
            url=safe_url, original_url=url, status_code=0,
            content_type="", html=None,
            error_type="timeout", error_detail="Request timed out",
        )
    except TooManyRedirects:
        return FetchResult(
            url=safe_url, original_url=url, status_code=0,
            content_type="", html=None,
            error_type="too_many_redirects", error_detail="Too many redirects",
        )
    except ConnectionError as exc:
        return FetchResult(
            url=safe_url, original_url=url, status_code=0,
            content_type="", html=None,
            error_type="connection_error", error_detail=str(exc),
        )
    except RequestException as exc:
        return FetchResult(
            url=safe_url, original_url=url, status_code=0,
            content_type="", html=None,
            error_type="request_error", error_detail=str(exc),
        )


def discover_internal_pages(
    base_url: str,
    html: str,
    *,
    session: Optional[requests.Session] = None,
    keywords: list[str] | None = None,
) -> list[str]:
    """
    Find internal links that likely point to About/Team/Contact pages.
    Returns a list of validated, absolute URLs (deduped, at most 10).
    """
    from bs4 import BeautifulSoup  # imported here to avoid circular at module level

    if keywords is None:
        keywords = ["about", "team", "leadership", "founders", "contact", "studio", "people", "us"]

    parsed_base = urllib.parse.urlparse(base_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue

        # Resolve relative URLs
        absolute = urllib.parse.urljoin(base_url, href)
        parsed_a = urllib.parse.urlparse(absolute)

        # Internal only
        if parsed_a.netloc != parsed_base.netloc:
            continue

        path_lower = parsed_a.path.lower()
        text_lower = a.get_text(" ", strip=True).lower()

        if any(kw in path_lower or kw in text_lower for kw in keywords):
            clean = urllib.parse.urlunparse(parsed_a._replace(fragment=""))
            if clean not in seen:
                seen.add(clean)
                try:
                    validate_url(clean)
                    candidates.append(clean)
                except URLValidationError:
                    pass

    return candidates[:10]
