"""
scraper/fetcher.py — Safe HTTP fetching with robots.txt compliance.

Features:
- Firecrawl-powered fetch (primary, when API key is set) for JS-heavy sites,
  bot-protected pages, and cleaner markdown extraction
- robots.txt check before every classic fetch
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
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
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    session.max_redirects = MAX_REDIRECTS
    return session


_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _make_session()
    return _session


def _has_almost_no_visible_text(html: str, min_chars: int = 150) -> bool:
    """Return True if the HTML has fewer than min_chars of visible text (e.g. SPA shells)."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        visible = soup.get_text(separator=" ", strip=True)
        return len(visible) < min_chars
    except Exception:
        return False


def _fetch_playwright(url: str, timeout_ms: int = 25000) -> Optional[str]:
    """Fetch and render page HTML using Playwright headless Chromium for SPAs."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            content = page.content()
            browser.close()
            return content
    except Exception as exc:
        logger.warning("Playwright render error for %s: %s", url, exc)
        return None


def _firecrawl_fetch_result(url: str) -> Optional["FetchResult"]:
    """
    Attempt to fetch `url` via Firecrawl.
    Returns a populated FetchResult on success, None if Firecrawl is unavailable
    or the fetch fails (allowing the caller to fall back to classic fetch).
    """
    try:
        from scraper.firecrawl_client import is_available, firecrawl_fetch
        if not is_available():
            return None
        logger.info("[Firecrawl] Fetching %s", url)
        fc = firecrawl_fetch(url)
        if fc["ok"]:
            html = fc["html"] or ""
            meta_title = fc.get("metadata", {}).get("title") or fc.get("metadata", {}).get("ogTitle") or ""
            if meta_title and "<title" not in html.lower():
                html = f"<head><title>{meta_title}</title></head>" + html
            elif not html and fc.get("markdown"):
                html = f"<html><head><title>{meta_title}</title></head><body>{fc['markdown']}</body></html>"
            return FetchResult(
                url=fc["url"],
                original_url=url,
                status_code=200,
                content_type="text/html",
                html=html,
            )
        else:
            logger.warning("[Firecrawl] Failed for %s: %s", url, fc.get("error"))
            return None
    except Exception as exc:
        logger.warning("[Firecrawl] Unexpected error for %s: %s", url, exc)
        return None


def fetch(url: str, *, session: Optional[requests.Session] = None, skip_robots: bool = False) -> FetchResult:
    """
    Fetch a URL safely.

    When a Firecrawl API key is configured, Firecrawl is tried first because it
    handles JS rendering, bot-protection, and returns clean content.  The classic
    requests+playwright pipeline is used as a fallback.

    Checks (classic path):
    1. URL validation (SSRF protection, scheme)
    2. robots.txt compliance
    3. HTTP fetch with timeout + size limit
    4. Re-validates final URL after redirects

    Returns a FetchResult (ok=False on any error).
    """
    # ── Try Firecrawl first ──────────────────────────────────────────────────
    fc_result = _firecrawl_fetch_result(url)
    if fc_result is not None:
        return fc_result

    # ── Classic requests-based fetch (fallback) ──────────────────────────────
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
        # Detect encoding: prefer UTF-8 over RFC default ISO-8859-1 for HTML5
        enc = resp.encoding
        if not enc or enc.lower() in ("iso-8859-1", "latin-1"):
            encoding = "utf-8"
        else:
            encoding = enc or resp.apparent_encoding or "utf-8"
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

        # Check if static HTML has almost no visible text (e.g. Single-Page Applications)
        if html and _has_almost_no_visible_text(html, min_chars=150):
            logger.info("Playwright fallback triggered: static HTML for %s has almost no visible text (<150 chars).", safe_url)
            rendered_html = _fetch_playwright(resp.url or safe_url)
            if rendered_html and not _has_almost_no_visible_text(rendered_html, min_chars=150):
                logger.info("Playwright fallback used for %s: rendered %d characters of HTML.", safe_url, len(rendered_html))
                html = rendered_html
            elif rendered_html:
                logger.info("Playwright fallback used for %s: rendered %d characters of HTML.", safe_url, len(rendered_html))
                html = rendered_html

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
        keywords = [
            "about", "team", "leadership", "founders", "contact", "studio",
            "people", "us", "services", "work", "projects", "portfolio", "news"
        ]

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
