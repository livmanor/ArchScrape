"""
scraper/lookup_pipeline.py — Unified company lookup pipeline.

Pipeline steps
--------------
1. Google Places API (New) text search.
   - If no result's name matches every word of the searched name: return not_found
     for all fields immediately.
   - Fields sourced from Places: organisation_name, city, mobile, website.
2. Firecrawl /v1/map on the Places website to discover relevant sub-pages
   (filters for contact / about / team).
3. Firecrawl /v1/scrape on homepage + up to 3 matched sub-pages.
   Params: formats ["markdown","links","json"], waitFor 3000, onlyMainContent false.
   JSON extraction prompt: "Extract only what is explicitly stated. Return null if
   not stated."
4. Email  — only mailto: links or literal email addresses found in scraped text.
5. Socials — only explicit links to linkedin/facebook/instagram/x/youtube found on
   the site pages.
6. CEO / designation — only from about/team page text; exact title preserved.
7. Verbatim verification — every extracted string value must appear verbatim in the
   scraped text (post-normalisation), otherwise overridden to "not found".
8. Company size — hook for enrichment API; always "not found" until configured.
   See _enrich_company_size() for integration point.
9. Persistence — calls save_structured_lead_to_db() so all fields are stored in
   SQLite with source attribution.

Output format
-------------
Every field in the returned dict is a sub-dict: {"value": ..., "source": ...}.
"source" is the URL where the value was found, or "google_places", or null.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

from scraper.places_client import places_text_search

logger = logging.getLogger(__name__)

FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev")

# Regex for bare email addresses in page text
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_JUNK_EMAIL_DOMAINS = {
    "example.com", "sample.com", "domain.com", "yourdomain.com",
    "wix.com", "sentry.io", "wordpress.org", "schema.org",
    "github.com", "email.com", "w3.org",
}

# Social platforms we collect
_SOCIAL_DOMAINS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
}

# Sub-page keywords that suggest contact / about / team content
_RELEVANT_PAGE_KEYWORDS = {"contact", "about", "team", "people", "leadership"}

# Designation tokens that indicate an executive / CEO role
_CEO_TITLE_RE = re.compile(
    r"\b(CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|"
    r"Director|Principal|Partner|President|Head)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Enrichment hook — company size
# ---------------------------------------------------------------------------

def _enrich_company_size(website: str, organisation_name: str) -> dict:
    """
    Hook for a company-size enrichment API (e.g. Clearbit, LinkedIn, etc.).

    To activate: set COMPANY_SIZE_API_KEY in the environment and implement
    the HTTP call below. Until configured this always returns "not found".

    Returns {"value": ..., "source": ...}
    """
    size_key = os.environ.get("COMPANY_SIZE_API_KEY", "").strip()
    if not size_key:
        logger.debug("[CompanySize] COMPANY_SIZE_API_KEY not configured; returning not found.")
        return {"value": "not found", "source": None}

    # ── ENRICHMENT API INTEGRATION POINT ──────────────────────────────────
    # Example (replace with your actual provider):
    #
    # resp = requests.get(
    #     "https://company-enrichment-api.example.com/lookup",
    #     params={"domain": urlparse(website).netloc, "name": organisation_name},
    #     headers={"Authorization": f"Bearer {size_key}"},
    #     timeout=8,
    # )
    # if resp.status_code == 200:
    #     size_text = resp.json().get("employee_range") or ""
    #     if size_text:
    #         return {"value": size_text, "source": "company_size_api"}
    # ──────────────────────────────────────────────────────────────────────

    return {"value": "not found", "source": None}


# ---------------------------------------------------------------------------
# Firecrawl helpers
# ---------------------------------------------------------------------------

def _fc_api_key() -> Optional[str]:
    """Resolve Firecrawl API key from environment (avoids Streamlit dependency)."""
    return (os.environ.get("FIRECRAWL_API_KEY") or "").strip() or None


def _fc_headers() -> dict:
    key = _fc_api_key()
    if not key:
        raise ValueError("FIRECRAWL_API_KEY environment variable is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _firecrawl_map(website: str) -> list[str]:
    """
    Call Firecrawl /v1/map on *website* with search terms contact/about/team.
    Returns a list of matching URLs (may be empty on error).
    """
    urls: list[str] = []
    for term in ("contact", "about", "team"):
        try:
            resp = requests.post(
                f"{FIRECRAWL_API_URL}/v1/map",
                headers=_fc_headers(),
                json={
                    "url": website,
                    "search": term,
                    "limit": 10,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                # v1/map returns {"links": [...]} or {"urls": [...]}
                links = data.get("links") or data.get("urls") or []
                for link in links:
                    if isinstance(link, str) and link not in urls:
                        urls.append(link)
            else:
                logger.warning(
                    "[FC Map] HTTP %d for '%s' (term='%s'): %s",
                    resp.status_code, website, term, resp.text[:200],
                )
        except Exception as exc:
            logger.warning("[FC Map] Error mapping '%s' (term='%s'): %s", website, term, exc)
    return urls


def _filter_relevant_pages(candidate_urls: list[str], homepage: str) -> list[str]:
    """
    From the candidate URLs returned by /v1/map, keep only those whose path
    contains a contact/about/team keyword AND that share the same origin as
    the homepage. Return at most 3 (one per category).
    """
    try:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(homepage))
    except Exception:
        origin = ""

    seen_keywords: set[str] = set()
    selected: list[str] = []

    for url in candidate_urls:
        try:
            parsed = urlparse(url)
        except Exception:
            continue

        # Must share the same origin
        url_origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin and url_origin != origin:
            continue

        path_lower = parsed.path.lower()
        for kw in _RELEVANT_PAGE_KEYWORDS:
            if kw in path_lower and kw not in seen_keywords:
                seen_keywords.add(kw)
                selected.append(url)
                break

        if len(selected) >= 3:
            break

    return selected


def _firecrawl_scrape(url: str) -> dict:
    """
    Call Firecrawl /v1/scrape on a single URL.
    Params: formats ["markdown","links","json"], waitFor 3000, onlyMainContent false.
    JSON extraction prompt encourages literal-only extraction.
    Returns the raw JSON response dict (may be empty on error).
    """
    payload = {
        "url": url,
        "formats": ["markdown", "links", "json"],
        "waitFor": 3000,
        "onlyMainContent": False,
        "jsonOptions": {
            "prompt": (
                "Extract only what is explicitly stated on this page. "
                "Return null for any field that is not directly stated."
            ),
        },
    }
    try:
        resp = requests.post(
            f"{FIRECRAWL_API_URL}/v1/scrape",
            headers=_fc_headers(),
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json().get("data") or {}
        logger.warning(
            "[FC Scrape] HTTP %d for '%s': %s",
            resp.status_code, url, resp.text[:200],
        )
    except Exception as exc:
        logger.warning("[FC Scrape] Error scraping '%s': %s", url, exc)
    return {}


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_emails(text: str, links: list[str]) -> list[str]:
    """
    Extract email addresses that are:
    - Explicitly in a mailto: link, OR
    - Literally present as an email pattern in the page text.
    Excludes junk domains.
    """
    found: list[str] = []

    # mailto: links
    for link in links:
        if isinstance(link, str) and link.lower().startswith("mailto:"):
            addr = link[7:].split("?")[0].strip().lower()
            if addr and "@" in addr:
                domain = addr.split("@")[-1]
                if domain not in _JUNK_EMAIL_DOMAINS and addr not in found:
                    found.append(addr)

    # Bare addresses in text
    for m in _EMAIL_RE.finditer(text or ""):
        addr = m.group(0).lower()
        domain = addr.split("@")[-1]
        if domain not in _JUNK_EMAIL_DOMAINS and addr not in found:
            found.append(addr)

    return found


def _extract_socials(links: list[str]) -> dict[str, str]:
    """
    Extract social profile URLs from page links.
    Only includes links to linkedin/facebook/instagram/x/youtube found on the
    site pages. Strips generic/share/policy paths.
    """
    _INVALID_PATHS = {
        "home", "share", "sharer", "sharer.php", "intent", "feed", "explore",
        "login", "signup", "terms", "privacy", "help", "about", "search",
        "policies", "pin", "pins", "p", "reel", "reels", "tv", "stories",
        "watch", "embed", "shorts", "playlist", "status", "hashtag", "results",
    }
    socials: dict[str, str] = {}

    for link in links:
        if not isinstance(link, str):
            continue
        try:
            parsed = urlparse(link)
            domain = parsed.netloc.lower().lstrip("www.")
            for sd, platform in _SOCIAL_DOMAINS.items():
                if sd in domain and platform not in socials:
                    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                    if not path_parts:
                        continue
                    first = path_parts[0].lower()
                    if first in _INVALID_PATHS:
                        continue
                    # LinkedIn: must be company/in/school
                    if platform == "linkedin" and first not in ("company", "in", "school"):
                        continue
                    # YouTube: must be @handle or c/channel/user
                    if platform == "youtube" and not (
                        first.startswith("@") or first in ("c", "channel", "user")
                    ):
                        continue
                    # Twitter/X: skip intent/share/status
                    if platform == "x" and first in ("intent", "share", "status", "search", "hashtag"):
                        continue
                    socials[platform] = link.rstrip(".,;:)\"'>")
        except Exception:
            continue

    return socials


def _extract_ceo(text: str) -> tuple[str, str]:
    """
    Extract CEO name and exact designation from about/team page text.
    Returns (name, designation) or ("not found", "not found").
    Only uses page text; never guesses or infers.
    """
    if not text:
        return "not found", "not found"

    # Pattern: "Name, <CEO Title>" or "<CEO Title>: Name" or "Name — <CEO Title>"
    # We look for a title token adjacent to a properly-cased name.

    # Pattern A: Title followed by colon/dash and then Name
    pat_a = re.search(
        r"(?P<title>"
        r"CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|"
        r"Director|Principal|Partner|President|Head"
        r")\s*[:\-\u2013\u2014]\s*"
        r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        text,
        re.IGNORECASE,
    )
    if pat_a:
        name = pat_a.group("name").strip()
        title = pat_a.group("title").strip()
        return name, title

    # Pattern B: Name followed by comma/dash and then Title
    pat_b = re.search(
        r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
        r"\s*[,\-\u2013\u2014]\s*"
        r"(?P<title>"
        r"CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|"
        r"Director|Principal|Partner|President|Head"
        r")\b",
        text,
    )
    if pat_b:
        name = pat_b.group("name").strip()
        title = pat_b.group("title").strip()
        return name, title

    # Pattern C: founded/led by Name
    pat_c = re.search(
        r"(?:founded|co-founded|led|headed|established)\s+(?:in\s+\d{4}\s+)?by\s+"
        r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        text,
        re.IGNORECASE,
    )
    if pat_c:
        name = pat_c.group("name").strip()
        return name, "Founder"

    return "not found", "not found"


# ---------------------------------------------------------------------------
# Verbatim verification
# ---------------------------------------------------------------------------

def _verify_verbatim(value: str, corpus: str) -> bool:
    """
    Return True if *value* appears verbatim (case-insensitive) inside *corpus*.
    Leading/trailing whitespace and internal multi-space are normalised before
    comparison so minor formatting differences don't cause false failures.
    """
    if not value or value == "not found":
        return False  # nothing to verify
    norm_val = re.sub(r"\s+", " ", value.strip()).lower()
    norm_corpus = re.sub(r"\s+", " ", corpus).lower()
    return norm_val in norm_corpus


def _verified_or_not_found(value: str, source: str, corpus: str) -> dict:
    """
    Return {"value": value, "source": source} if value passes verbatim check,
    otherwise {"value": "not found", "source": None}.
    """
    if _verify_verbatim(value, corpus):
        return {"value": value, "source": source}
    logger.debug("[Verify] '%s' not found verbatim in scraped text; marking not found.", value[:60])
    return {"value": "not found", "source": None}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _not_found_all() -> dict:
    """Return the canonical not-found response for all output fields."""
    return {
        "organisation_name": {"value": "not found", "source": None},
        "ceo": {
            "name": {"value": "not found", "source": None},
            "designation": {"value": "not found", "source": None},
        },
        "company_size": {"value": "not found", "source": None},
        "socials": {"value": {}, "source": None},
        "city": {"value": "not found", "source": None},
        "email": {"value": "not found", "source": None},
        "mobile": {"value": "not found", "source": None},
    }


def lookup_company(name: str, db_path=None) -> dict:
    """
    End-to-end company lookup pipeline.

    Parameters
    ----------
    name : str
        Company name exactly as typed by the user (e.g. "design cafe").
    db_path : pathlib.Path | None
        Optional path to SQLite database for persistence.

    Returns
    -------
    dict with keys:
        ok        : bool
        name      : str  (the searched name)
        pipeline  : list[str]  (log of steps taken)
        fields    : dict  (all output fields with {value, source})
        error     : str | None

    Output fields (all under "fields"):
        organisation_name  : {value, source}
        ceo                : {name: {value, source}, designation: {value, source}}
        company_size       : {value, source}
        socials            : {value: {platform: url}, source}
        city               : {value, source}
        email              : {value, source}
        mobile             : {value, source}
    """
    pipeline_log: list[str] = []

    def log(msg: str) -> None:
        logger.info(msg)
        pipeline_log.append(msg)

    result = _not_found_all()
    result["ok"] = True
    result["name"] = name
    result["pipeline"] = pipeline_log
    result["error"] = None

    # ── STEP 1: Google Places API ────────────────────────────────────────────
    log(f"[Step 1] Google Places text search for '{name}'.")
    places = places_text_search(name)

    if places is None:
        log("[Step 1] No name-matching place found — returning not_found for all fields.")
        result["ok"] = False
        result["error"] = (
            f"No Google Places result whose name matches every word of '{name}'. "
            "Returning not_found for all fields."
        )
        return result

    log(f"[Step 1] Places match: organisation='{places.organisation_name['value']}', "
        f"city='{places.city['value']}', mobile='{places.mobile['value']}', "
        f"website='{places.website['value']}'.")

    # Populate fields from Places
    result["organisation_name"] = places.organisation_name
    result["city"] = places.city
    result["mobile"] = places.mobile

    website = places.website.get("value") or ""
    if not website:
        log("[Step 1] Places did not return a website URL; cannot scrape. Stopping.")
        return result

    # ── STEP 2: Firecrawl /v1/map to discover sub-pages ─────────────────────
    log(f"[Step 2] Firecrawl /v1/map on '{website}'.")
    try:
        map_urls = _firecrawl_map(website)
        relevant_pages = _filter_relevant_pages(map_urls, website)
        log(f"[Step 2] Map returned {len(map_urls)} URLs; {len(relevant_pages)} relevant pages selected: {relevant_pages}.")
    except ValueError as exc:
        log(f"[Step 2] Skipped — {exc}")
        relevant_pages = []
        map_urls = []

    # ── STEP 3: Firecrawl /v1/scrape on homepage + relevant sub-pages ────────
    pages_to_scrape = [website] + relevant_pages
    scraped_pages: dict[str, dict] = {}  # url -> scrape result

    for page_url in pages_to_scrape:
        log(f"[Step 3] Scraping '{page_url}'.")
        try:
            page_data = _firecrawl_scrape(page_url)
            if page_data:
                scraped_pages[page_url] = page_data
                log(f"[Step 3] Scraped '{page_url}': "
                    f"{len(page_data.get('markdown') or '')} chars markdown.")
            else:
                log(f"[Step 3] Empty response for '{page_url}'.")
        except ValueError as exc:
            log(f"[Step 3] Skipped scraping — {exc}")
            break

    # Build combined corpus for verbatim checks
    all_markdown = "\n\n".join(
        (v.get("markdown") or "") for v in scraped_pages.values()
    )
    all_links: list[str] = []
    for v in scraped_pages.values():
        links_obj = v.get("links") or []
        if isinstance(links_obj, list):
            all_links.extend(links_obj)

    # ── STEP 4: Email extraction ─────────────────────────────────────────────
    log("[Step 4] Extracting emails from scraped pages.")
    emails_found = _extract_emails(all_markdown, all_links)
    if emails_found:
        # Use the first email; record source URL (whichever page it appeared in)
        chosen_email = emails_found[0]
        email_source = None
        for page_url, page_data in scraped_pages.items():
            page_md = page_data.get("markdown") or ""
            page_links = page_data.get("links") or []
            if isinstance(page_links, list) and any(
                l.lower().startswith("mailto:" + chosen_email) for l in page_links
            ):
                email_source = page_url
                break
            if chosen_email in page_md.lower():
                email_source = page_url
                break
        result["email"] = {"value": chosen_email, "source": email_source or website}
        log(f"[Step 4] Email found: '{chosen_email}' (source: {email_source}).")
    else:
        log("[Step 4] No email found.")

    # ── STEP 5: Socials extraction ───────────────────────────────────────────
    log("[Step 5] Extracting social links from scraped pages.")
    socials_found = _extract_socials(all_links)
    if socials_found:
        result["socials"] = {"value": socials_found, "source": website}
        log(f"[Step 5] Socials found: {list(socials_found.keys())}.")
    else:
        log("[Step 5] No social links found.")

    # ── STEP 6: CEO / designation — only from about/team pages ──────────────
    log("[Step 6] Extracting CEO/designation from about/team pages.")
    ceo_name = "not found"
    ceo_desig = "not found"
    ceo_source = None

    for page_url in relevant_pages:  # only sub-pages, not homepage
        page_data = scraped_pages.get(page_url)
        if not page_data:
            continue
        page_md = page_data.get("markdown") or ""
        path_lower = urlparse(page_url).path.lower()
        if not any(kw in path_lower for kw in ("about", "team", "people", "leadership")):
            continue

        extracted_name, extracted_desig = _extract_ceo(page_md)
        if extracted_name != "not found":
            ceo_name = extracted_name
            ceo_desig = extracted_desig
            ceo_source = page_url
            log(f"[Step 6] CEO found: '{ceo_name}' ({ceo_desig}) at {page_url}.")
            break

    if ceo_name == "not found":
        log("[Step 6] No CEO/designation found in about/team pages.")

    result["ceo"] = {
        "name": {"value": ceo_name, "source": ceo_source},
        "designation": {"value": ceo_desig, "source": ceo_source},
    }

    # ── STEP 7: Verbatim verification ────────────────────────────────────────
    log("[Step 7] Verbatim verification of extracted values.")

    # organisation_name: sourced from Google Places, so skip verbatim check
    # (Places data is authoritative; we don't require it to appear on the website)

    # CEO name — verify against the source page only
    if ceo_name != "not found" and ceo_source:
        source_corpus = (scraped_pages.get(ceo_source) or {}).get("markdown") or ""
        verified = _verified_or_not_found(ceo_name, ceo_source, source_corpus)
        if verified["value"] == "not found":
            log(f"[Step 7] CEO name '{ceo_name}' failed verbatim check.")
            result["ceo"]["name"] = {"value": "not found", "source": None}
            result["ceo"]["designation"] = {"value": "not found", "source": None}
        else:
            result["ceo"]["name"] = verified
            # Verify designation too
            desig_verified = _verified_or_not_found(ceo_desig, ceo_source, source_corpus)
            result["ceo"]["designation"] = desig_verified

    # Email — verify against combined corpus
    email_val = result["email"]["value"]
    if email_val != "not found":
        if not _verify_verbatim(email_val, all_markdown) and not any(
            email_val in (l[7:] if l.lower().startswith("mailto:") else "") for l in all_links
        ):
            log(f"[Step 7] Email '{email_val}' failed verbatim check.")
            result["email"] = {"value": "not found", "source": None}

    # ── STEP 8: Company size (enrichment hook) ────────────────────────────────
    log("[Step 8] Company size enrichment (hook).")
    result["company_size"] = _enrich_company_size(
        website=website,
        organisation_name=places.organisation_name.get("value") or name,
    )

    # ── STEP 9: Persist to SQLite ─────────────────────────────────────────────
    if db_path is not None:
        try:
            from services.company_service import save_structured_lead_to_db
            ceo_name_val = result["ceo"]["name"]["value"]
            ceo_desig_val = result["ceo"]["designation"]["value"]
            socials_val = result["socials"].get("value") or {}
            email_val = result["email"]["value"]
            mobile_val = result["mobile"]["value"]

            lead_dict = {
                "url": website,
                "organisation": result["organisation_name"]["value"],
                "owner_name": ceo_name_val if ceo_name_val != "not found" else None,
                "designation": ceo_desig_val if ceo_desig_val != "not found" else None,
                "city": result["city"]["value"] if result["city"]["value"] != "not found" else None,
                "org_size": result["company_size"]["value"] if result["company_size"]["value"] != "not found" else None,
                "emails": [email_val] if email_val != "not found" else [],
                "phones": [mobile_val] if mobile_val != "not found" else [],
                "socials": socials_val,
                "services": [],
                "clean_summary": f"Looked up via Google Places + Firecrawl pipeline.",
            }
            save_result = save_structured_lead_to_db(lead_dict, db_path=db_path)
            log(f"[Step 9] Persisted to DB: company_id={save_result.get('company_id')}.")
        except Exception as exc:
            log(f"[Step 9] DB persistence skipped: {exc}")

    log("[Done] Pipeline complete.")
    return result
