"""
scraper/firecrawl_client.py — Firecrawl-powered web fetching, AI search, and directory fallback.

Compatible with firecrawl-py v1.x / v4.x and direct Firecrawl REST API (v1).
Provides:
  - is_available()                     → bool
  - get_client()                       → FirecrawlApp | None
  - test_firecrawl_connection(key)     → tuple[bool, str]
  - firecrawl_fetch(url)               → dict {ok, url, html, markdown, error}
  - firecrawl_search(query, N, ...)    → list[SearchHit] (raises on API failure for clear feedback)
  - search_local_directory(query, N)   → list[SearchHit] (fallback to verified local datasets)

API key resolution priority:
  1. st.session_state["firecrawl_api_key"]
  2. st.session_state["_fc_key_input"] (sidebar widget text)
  3. st.session_state["fc_page_key_input"] (search page widget text)
  4. FIRECRAWL_API_KEY environment variable
"""

import csv
import logging
import os
import pathlib
from dataclasses import dataclass, field
from typing import Optional, Union

import requests

logger = logging.getLogger(__name__)

FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev")


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class SearchHit:
    title: str
    url: str
    description: str
    markdown: str = ""
    source: str = "firecrawl"  # 'firecrawl' | 'local_directory'


# ─── Lazy SDK Import ─────────────────────────────────────────────────────────

def _get_sdk():
    """Lazy-import FirecrawlApp; returns None if package is missing or wrong package."""
    try:
        from firecrawl import FirecrawlApp
        if not hasattr(FirecrawlApp, "scrape_url"):
            logger.error(
                "Imported FirecrawlApp missing 'scrape_url'. "
                "Run: pip install firecrawl-py==1.14.0"
            )
            return None
        return FirecrawlApp
    except ImportError:
        logger.warning("firecrawl-py is not installed. Run: pip install firecrawl-py")
        return None


# ─── Key Resolution ──────────────────────────────────────────────────────────

def _resolve_api_key() -> Optional[str]:
    """Return configured API key from session state, input widgets, or environment."""
    try:
        import streamlit as st
        # 1. Explicitly applied key
        k = (st.session_state.get("firecrawl_api_key") or "").strip()
        if k:
            return k
        # 2. Key typed in search page input
        k = (st.session_state.get("fc_page_key_input") or "").strip()
        if k:
            return k
        # 3. Key typed in sidebar widget
        k = (st.session_state.get("_fc_key_input") or "").strip()
        if k:
            return k
    except Exception:
        pass

    env_key = (os.environ.get("FIRECRAWL_API_KEY") or "").strip()
    return env_key or None


def is_available() -> bool:
    """True if SDK is importable AND an API key is configured."""
    return _get_sdk() is not None and bool(_resolve_api_key())


def get_client(api_key: Optional[str] = None):
    """Return a configured FirecrawlApp, or None."""
    FirecrawlApp = _get_sdk()
    if FirecrawlApp is None:
        return None
    key = api_key or _resolve_api_key()
    if not key:
        return None
    try:
        return FirecrawlApp(api_key=key, api_url=FIRECRAWL_API_URL)
    except Exception as exc:
        logger.error("Firecrawl client init failed: %s", exc)
        return None


# ─── Connection / Key Tester ─────────────────────────────────────────────────

def test_firecrawl_connection(api_key: Optional[str] = None) -> tuple[bool, str]:
    """
    Test whether the provided or configured API key can authenticate with Firecrawl.
    Returns (success: bool, message: str).
    """
    key = api_key or _resolve_api_key()
    if not key:
        return False, "No API key provided. Please enter your Firecrawl API key."

    try:
        # Perform a lightweight search request
        resp = requests.post(
            f"{FIRECRAWL_API_URL}/v1/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": "architecture", "limit": 1},
            timeout=10,
        )

        if resp.status_code == 200:
            return True, "✅ Connection successful! Firecrawl API key is valid and active."

        if resp.status_code == 401:
            return False, "❌ Invalid API key (HTTP 401 Unauthorized). Please check your key at firecrawl.dev."

        if resp.status_code == 402:
            return False, "❌ Insufficient credits (HTTP 402 Payment Required). Your Firecrawl account credits may be exhausted."

        if resp.status_code == 429:
            return False, "⚠️ Rate limit reached (HTTP 429). Please wait a few seconds and try again."

        # Parse error details if available
        try:
            err_data = resp.json()
            err_msg = err_data.get("error") or err_data.get("message") or resp.text
        except Exception:
            err_msg = resp.text

        return False, f"❌ Firecrawl returned HTTP {resp.status_code}: {err_msg}"

    except requests.exceptions.Timeout:
        return False, "⏱️ Connection timed out. Firecrawl service might be slow or unreachable."
    except Exception as exc:
        return False, f"❌ Connection failed: {exc}"


# ─── Single-URL Scrape ───────────────────────────────────────────────────────

def firecrawl_fetch(url: str) -> dict:
    """
    Scrape one URL with Firecrawl and return a normalised dict:
      {ok, url, html, markdown, error}
    """
    client = get_client()
    if client is None:
        return {
            "ok": False,
            "url": url,
            "html": None,
            "markdown": None,
            "error": "Firecrawl unavailable (no API key or SDK not installed)",
        }

    try:
        logger.info("[Firecrawl] scrape_url → %s", url)
        data = client.scrape_url(
            url,
            params={
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
                "waitFor": 2000,
            },
        )

        if not isinstance(data, dict):
            return {
                "ok": False,
                "url": url,
                "html": None,
                "markdown": None,
                "error": f"Unexpected response type from Firecrawl: {type(data)}",
            }

        markdown = (data.get("markdown") or "").strip()
        html = (data.get("html") or "").strip()
        metadata = data.get("metadata") or {}
        final_url = metadata.get("sourceURL") or metadata.get("url") or url

        ok = bool(markdown or html)
        return {
            "ok": ok,
            "url": final_url,
            "html": html,
            "markdown": markdown,
            "error": None if ok else "Firecrawl returned empty content for this page.",
        }

    except Exception as exc:
        logger.warning("[Firecrawl] scrape_url error for %s: %s", url, exc)
        return {
            "ok": False,
            "url": url,
            "html": None,
            "markdown": None,
            "error": str(exc),
        }


# ─── Live Web Search ─────────────────────────────────────────────────────────

def firecrawl_search(
    query: str,
    limit: int = 10,
    scrape_content: bool = True,
    country: str = "in",
) -> list[SearchHit]:
    """
    Search the web via Firecrawl and return list[SearchHit].

    Raises Exception with detailed error messages on API failure so that the UI
    can inform the user immediately (e.g. 401 invalid key, 402 out of credits).
    """
    key = _resolve_api_key()
    if not key:
        raise ValueError(
            "Firecrawl API key not found. Please enter and apply your Firecrawl API key "
            "in the search panel or sidebar."
        )

    # Prepare search payload
    payload = {
        "query": query,
        "limit": limit,
        "country": country,
        "lang": "en",
    }
    if scrape_content:
        payload["scrapeOptions"] = {"formats": ["markdown"]}

    logger.info("[Firecrawl] search query='%s' limit=%d", query, limit)

    def _execute_search(json_payload: dict) -> requests.Response:
        return requests.post(
            f"{FIRECRAWL_API_URL}/v1/search",
            headers={"Authorization": f"Bearer {key}"},
            json=json_payload,
            timeout=35,
        )

    try:
        resp = _execute_search(payload)
    except requests.exceptions.Timeout:
        # If search with scrapeOptions timed out, retry lightweight search without scrapeOptions
        if scrape_content:
            logger.warning("[Firecrawl] Search with scrapeOptions timed out; retrying without scrapeOptions...")
            light_payload = {k: v for k, v in payload.items() if k != "scrapeOptions"}
            resp = _execute_search(light_payload)
        else:
            raise Exception("Search request timed out after 35 seconds. Firecrawl may be busy.")

    # Handle HTTP status codes with clear feedback
    if resp.status_code == 401:
        raise Exception(
            "Firecrawl Error 401: Unauthorized / Invalid API Key. "
            "Please check your key at firecrawl.dev and paste the correct key."
        )

    if resp.status_code == 402:
        raise Exception(
            "Firecrawl Error 402: Insufficient Credits. "
            "Your Firecrawl account free credits may be exhausted. Please check firecrawl.dev."
        )

    if resp.status_code == 429:
        raise Exception(
            "Firecrawl Error 429: Rate Limit Exceeded. "
            "Too many requests have been made in a short time. Please wait 10 seconds and try again."
        )

    if resp.status_code != 200:
        err_detail = resp.text
        try:
            err_json = resp.json()
            err_detail = err_json.get("error") or err_json.get("message") or resp.text
        except Exception:
            pass
        raise Exception(f"Firecrawl API returned status {resp.status_code}: {err_detail}")

    try:
        data = resp.json()
    except Exception:
        raise Exception("Failed to parse Firecrawl response as JSON.")

    if not isinstance(data, dict):
        raise Exception(f"Unexpected Firecrawl response format: {type(data)}")

    # In v1 API, results can be under "data"
    raw_hits = data.get("data")
    if raw_hits is None and "results" in data:
        raw_hits = data.get("results")

    if not raw_hits or not isinstance(raw_hits, list):
        return []

    hits: list[SearchHit] = []
    for item in raw_hits:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        hits.append(SearchHit(
            title=(item.get("title") or "").strip(),
            url=url,
            description=(item.get("description") or "").strip(),
            markdown=(item.get("markdown") or "").strip(),
            source="firecrawl",
        ))

    logger.info("[Firecrawl] search '%s' → %d hits", query, len(hits))
    return hits


# ─── Local Curated Directory Fallback ────────────────────────────────────────

def search_local_directory(query: str, limit: int = 15) -> list[SearchHit]:
    """
    Search the pre-compiled architecture firm datasets in data/ for matching firms.
    Works offline, instantly, with zero API keys.
    """
    q_lower = query.lower().strip()
    words = [w for w in q_lower.split() if len(w) > 2 and w not in {"the", "and", "for", "best", "cheap", "top"}]

    data_dir = pathlib.Path(__file__).parent.parent / "data"
    if not data_dir.exists():
        return []

    matches: list[tuple[int, SearchHit]] = []
    seen_urls = set()

    for csv_file in sorted(data_dir.glob("*_architecture_firms.csv")):
        city_name = csv_file.name.split("_")[0].capitalize()
        try:
            with open(csv_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = (row.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue

                    notes = (row.get("notes") or "").strip()
                    category = (row.get("category") or "architecture").strip()

                    search_text = f"{url} {notes} {city_name} {category}".lower()

                    # Scoring
                    score = 0
                    if q_lower in search_text:
                        score += 10
                    for w in words:
                        if w in search_text:
                            score += 2

                    if score > 0 or not words:
                        seen_urls.add(url)
                        title = notes or url.replace("https://", "").replace("http://", "").split("/")[0]
                        desc = f"Verified {category.title()} firm in {city_name}. {notes}"
                        matches.append((
                            score,
                            SearchHit(
                                title=title,
                                url=url,
                                description=desc,
                                markdown="",
                                source="local_directory",
                            )
                        ))
        except Exception as exc:
            logger.debug("Error reading %s: %s", csv_file, exc)

    # Sort by relevance score descending
    matches.sort(key=lambda x: x[0], reverse=True)
    return [hit for _, hit in matches[:limit]]
