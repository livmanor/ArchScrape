"""
scraper/firecrawl_client.py — Firecrawl-powered web fetching and AI search.

Provides:
  - firecrawl_fetch(url)  → FetchResult  (replaces requests+playwright)
  - firecrawl_search(query, limit) → list of SearchHit dicts
  - is_available() → bool  (True if API key is configured)

The Firecrawl API key is read from (in priority order):
  1. Streamlit session state: st.session_state["firecrawl_api_key"]
  2. Environment variable: FIRECRAWL_API_KEY

If no key is set, is_available() returns False and the caller should
fall back to the classic requests-based fetcher.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Firecrawl SDK lazy import ────────────────────────────────────────────────

def _get_sdk():
    """Lazy-import firecrawl-py to avoid hard startup crash when not installed."""
    try:
        from firecrawl import FirecrawlApp
        return FirecrawlApp
    except ImportError:
        return None


# ─── API key resolution ───────────────────────────────────────────────────────

def _resolve_api_key() -> Optional[str]:
    """Return the Firecrawl API key from session state or environment, or None."""
    # Try Streamlit session state first (set via the Settings UI)
    try:
        import streamlit as st
        key = st.session_state.get("firecrawl_api_key", "").strip()
        if key:
            return key
    except Exception:
        pass

    # Fall back to environment variable
    return os.environ.get("FIRECRAWL_API_KEY", "").strip() or None


def is_available() -> bool:
    """Return True if a Firecrawl API key is configured and SDK is installed."""
    sdk = _get_sdk()
    if sdk is None:
        return False
    return bool(_resolve_api_key())


def get_client():
    """Return a configured FirecrawlApp instance, or None if unavailable."""
    FirecrawlApp = _get_sdk()
    if FirecrawlApp is None:
        logger.warning("firecrawl-py is not installed. Run: pip install firecrawl-py")
        return None
    key = _resolve_api_key()
    if not key:
        return None
    try:
        return FirecrawlApp(api_key=key)
    except Exception as exc:
        logger.error("Failed to initialise Firecrawl client: %s", exc)
        return None


# ─── Fetch a single URL via Firecrawl ────────────────────────────────────────

def firecrawl_fetch(url: str) -> dict:
    """
    Fetch and clean a URL using Firecrawl.

    Returns a dict compatible with the rest of the pipeline:
    {
        "ok": bool,
        "url": str,           # final URL
        "html": str | None,   # raw HTML (if available)
        "markdown": str | None,  # clean markdown (Firecrawl's output)
        "error": str | None,
    }
    """
    client = get_client()
    if client is None:
        return {
            "ok": False, "url": url, "html": None,
            "markdown": None, "error": "Firecrawl not available (no API key)",
        }

    try:
        result = client.scrape_url(
            url,
            params={
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
                "waitFor": 2000,
            },
        )

        # firecrawl-py ≥ 1.x returns a ScrapeResponse object
        if hasattr(result, "markdown"):
            markdown = result.markdown or ""
            html = getattr(result, "html", None) or ""
            metadata = getattr(result, "metadata", {}) or {}
            final_url = (metadata.get("sourceURL") or metadata.get("url") or url)
            success = bool(markdown or html)
        elif isinstance(result, dict):
            markdown = result.get("markdown") or ""
            html = result.get("html") or ""
            metadata = result.get("metadata", {}) or {}
            final_url = metadata.get("sourceURL") or metadata.get("url") or url
            success = bool(markdown or html)
        else:
            return {
                "ok": False, "url": url, "html": None,
                "markdown": None, "error": f"Unexpected Firecrawl response type: {type(result)}",
            }

        return {
            "ok": success,
            "url": final_url,
            "html": html,
            "markdown": markdown,
            "error": None if success else "Firecrawl returned empty content",
        }

    except Exception as exc:
        logger.warning("Firecrawl fetch error for %s: %s", url, exc)
        return {
            "ok": False, "url": url, "html": None,
            "markdown": None, "error": str(exc),
        }


# ─── AI-powered web search via Firecrawl ─────────────────────────────────────

@dataclass
class SearchHit:
    title: str
    url: str
    description: str
    markdown: str = ""        # page content from Firecrawl, if scraped
    source: str = "firecrawl"


def firecrawl_search(
    query: str,
    limit: int = 10,
    scrape_content: bool = True,
) -> list[SearchHit]:
    """
    Search the web using Firecrawl and return a list of SearchHit results.

    Parameters
    ----------
    query : str
        Natural-language search query (e.g. "top architecture firms in Pune").
    limit : int
        Maximum number of results to return.
    scrape_content : bool
        If True, Firecrawl will also scrape and return page content.

    Returns
    -------
    list[SearchHit]  — empty list if unavailable or on error.
    """
    client = get_client()
    if client is None:
        logger.warning("Firecrawl search unavailable — no API key or SDK missing.")
        return []

    try:
        params: dict = {"limit": limit}
        if scrape_content:
            params["scrapeOptions"] = {"formats": ["markdown"]}

        response = client.search(query, params=params)

        hits: list[SearchHit] = []

        # Handle both object and dict responses from different SDK versions
        items = []
        if hasattr(response, "data"):
            items = response.data or []
        elif hasattr(response, "__iter__"):
            items = list(response)
        elif isinstance(response, dict):
            items = response.get("data", [])

        for item in items:
            if hasattr(item, "url"):
                # Object-style response (SDK ≥ 1.x)
                title = getattr(item, "title", "") or ""
                url = getattr(item, "url", "") or ""
                desc = getattr(item, "description", "") or ""
                md = getattr(item, "markdown", "") or ""
            elif isinstance(item, dict):
                title = item.get("title", "") or ""
                url = item.get("url", "") or ""
                desc = item.get("description", "") or ""
                md = item.get("markdown", "") or ""
            else:
                continue

            if url:
                hits.append(SearchHit(
                    title=title,
                    url=url,
                    description=desc,
                    markdown=md,
                ))

        logger.info("Firecrawl search '%s' → %d hits", query, len(hits))
        return hits

    except Exception as exc:
        logger.error("Firecrawl search error: %s", exc)
        return []
