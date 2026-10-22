"""
scraper/lookup_pipeline.py — Unified company lookup pipeline.

Pipeline steps
--------------
1. Google Places API (New) text search.
   - If no result's name matches every word of the searched name: return not_found
     for all fields immediately.
   - Fields sourced from Places: organisation_name, city, mobile, website.
2. Firecrawl /v1/map on the Places website to discover sub-pages using search terms:
   about, team, leadership, founder, people, story, guild, management, who we are, contact.
3. Firecrawl /v1/scrape on homepage + all discovered sub-pages.
   Params: formats ["markdown","html","json"], waitFor 4000, onlyMainContent false.
   JSON extraction prompt: "List every person named on this page with job title.
   Include founders, directors, CEOs. Return null if not stated."
4. Email — only mailto: links or literal email addresses found in scraped text.
5. Socials — only explicit links to linkedin/facebook/instagram/x/youtube found on the site pages.
6. People / CEO discovery:
   - Run on homepage and all pages from /v1/map.
   - Parse <script type="application/ld+json"> from the html for founder/employee/Person fields and use them first.
   - Parse Firecrawl structured JSON prompt response.
   - Parse text and heading leadership patterns from page markdown.
   - Normalise whitespace, punctuation, and case before the verbatim check; check name and designation
     separately against the page text.
   - Collect list of people: {name, designation, source_url}.
   - Pick the CEO as the one whose title contains CEO, Chief Executive, Founder, or Managing Director.
   - Screenshot + vision fallback only if no person is found and the page looks image-based.
     Never accept a name that is not visibly present.
7. Verbatim verification — every extracted string value must appear verbatim in the scraped text
   (post-normalisation), otherwise marked "not found".
8. Company size — hook for enrichment API; always "not found" until configured.
9. Persistence — calls save_structured_lead_to_db() so all fields are stored in SQLite with source attribution.
10. Logging — per lookup: log pages scraped, people found per page, and why any candidate was rejected.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

from scraper.places_client import places_text_search

try:
    from google import genai
except ImportError:
    genai = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

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

# Search terms for discovering leadership, team, and contact sub-pages
_RELEVANT_PAGE_KEYWORDS = [
    "about", "team", "leadership", "founder", "people",
    "story", "guild", "management", "who we are", "who-we-are", "whoweare", "contact"
]

# Designation tokens that indicate an executive / founder role
_CEO_TITLE_RE = re.compile(
    r"\b(CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|"
    r"Director|Principal|Partner|President|Head|Architect|Business Coach|"
    r"Creative Director|Design Director|Studio Head|Lead Architect|Principal Architect|"
    r"Creative Lead|Studio Director|Brand Strategist)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Enrichment hook — company size
# ---------------------------------------------------------------------------

def _enrich_company_size(website: str, organisation_name: str) -> dict:
    """
    Hook for a company-size enrichment API (e.g. Clearbit, LinkedIn, etc.).
    Returns {"value": ..., "source": ...}
    """
    size_key = os.environ.get("COMPANY_SIZE_API_KEY", "").strip()
    if not size_key:
        logger.debug("[CompanySize] COMPANY_SIZE_API_KEY not configured; returning not found.")
        return {"value": "not found", "source": None}

    return {"value": "not found", "source": None}


# ---------------------------------------------------------------------------
# Firecrawl helpers
# ---------------------------------------------------------------------------

def _fc_api_key() -> Optional[str]:
    """Resolve Firecrawl API key from environment."""
    return (os.environ.get("FIRECRAWL_API_KEY") or "").strip() or None


def _fc_headers() -> dict:
    key = _fc_api_key()
    if not key:
        raise ValueError("FIRECRAWL_API_KEY environment variable is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _firecrawl_map(website: str) -> list[str]:
    """
    Call Firecrawl /v1/map on *website* with search terms:
    about, team, leadership, founder, people, story, guild, management, who we are, contact.
    Returns a list of matching URLs (may be empty on error).
    """
    urls: list[str] = []
    try:
        resp = requests.post(
            f"{FIRECRAWL_API_URL}/v1/map",
            headers=_fc_headers(),
            json={
                "url": website,
                "search": "about team leadership founder people story guild management who we are contact",
                "limit": 25,
            },
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            links = data.get("links") or data.get("urls") or []
            for link in links:
                if isinstance(link, str) and link not in urls:
                    urls.append(link)
        else:
            logger.warning(
                "[FC Map] HTTP %d for '%s': %s",
                resp.status_code, website, resp.text[:200],
            )
    except Exception as exc:
        logger.warning("[FC Map] Error mapping '%s': %s", website, exc)
    return urls


def _filter_relevant_pages(candidate_urls: list[str], homepage: str) -> list[str]:
    """
    Keep URLs from /v1/map matching the requested search terms and sharing origin.
    """
    try:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(homepage))
    except Exception:
        origin = ""

    selected: list[str] = []
    seen: set[str] = set()

    clean_hp = homepage.split("?")[0].rstrip("/")

    for url in candidate_urls:
        try:
            parsed = urlparse(url)
        except Exception:
            continue

        url_origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin and url_origin != origin:
            continue

        path_lower = parsed.path.lower().replace("-", " ").replace("_", " ")
        if any(kw in path_lower for kw in _RELEVANT_PAGE_KEYWORDS):
            clean_url = url.split("?")[0].rstrip("/")
            if clean_url not in seen and clean_url != clean_hp:
                seen.add(clean_url)
                selected.append(url)

    return selected


def _firecrawl_scrape(url: str, formats: list[str] | None = None) -> dict:
    """
    Call Firecrawl /v1/scrape on a single URL.
    Params: formats ["markdown","html","json"], waitFor 4000, onlyMainContent false.
    JSON extraction prompt:
      "List every person named on this page with job title. Include founders, directors, CEOs. Return null if not stated."
    Returns the raw JSON response dict (may be empty on error).
    """
    payload = {
        "url": url,
        "formats": formats or ["markdown", "html", "json"],
        "waitFor": 4000,
        "onlyMainContent": False,
        "jsonOptions": {
            "prompt": (
                "List every person named on this page with job title. "
                "Include founders, directors, CEOs. Return null if not stated."
            ),
        },
    }
    try:
        resp = requests.post(
            f"{FIRECRAWL_API_URL}/v1/scrape",
            headers=_fc_headers(),
            json=payload,
            timeout=50,
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
# Verbatim normalisation & checking
# ---------------------------------------------------------------------------

def _normalise_for_verbatim(text: str) -> str:
    """Normalise whitespace, punctuation, and case before verbatim comparison."""
    if not text:
        return ""
    # Replace punctuation characters with whitespace
    s = re.sub(r"[^\w\s]", " ", text)
    # Normalise whitespace and convert to lowercase
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _verify_verbatim_part(part: str, corpus: str) -> bool:
    """
    Check if *part* appears verbatim in *corpus* after normalisation of
    whitespace, punctuation, and case.
    """
    if not part or part.strip().lower() in ("not found", "null", "none"):
        return False
    norm_part = _normalise_for_verbatim(part)
    if not norm_part:
        return False
    norm_corpus = _normalise_for_verbatim(corpus)
    return norm_part in norm_corpus


def _verified_or_not_found(value: str, source: str, corpus: str) -> dict:
    """Return {"value": value, "source": source} if value passes verbatim check, else not found."""
    if _verify_verbatim_part(value, corpus):
        return {"value": value, "source": source}
    logger.debug("[Verify] '%s' not found verbatim in scraped text; marking not found.", value[:60])
    return {"value": "not found", "source": None}


# ---------------------------------------------------------------------------
# Field extraction helpers (Email & Socials)
# ---------------------------------------------------------------------------

def _extract_emails(text: str, links: list[str]) -> list[str]:
    """Extract email addresses from mailto: links and page text."""
    found: list[str] = []

    for link in links:
        if isinstance(link, str) and link.lower().startswith("mailto:"):
            addr = link[7:].split("?")[0].strip().lower()
            if addr and "@" in addr:
                domain = addr.split("@")[-1]
                if domain not in _JUNK_EMAIL_DOMAINS and addr not in found:
                    found.append(addr)

    for m in _EMAIL_RE.finditer(text or ""):
        addr = m.group(0).lower()
        domain = addr.split("@")[-1]
        if domain not in _JUNK_EMAIL_DOMAINS and addr not in found:
            found.append(addr)

    return found


def _extract_socials(links: list[str]) -> dict[str, str]:
    """Extract social profile URLs from page links."""
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
                    if path_parts[0].lower() in _INVALID_PATHS:
                        continue
                    clean_url = f"https://{domain}/{'/'.join(path_parts)}"
                    socials[platform] = clean_url
                    break
        except Exception:
            continue

    return socials


# ---------------------------------------------------------------------------
# Person & Leadership Extraction
# ---------------------------------------------------------------------------

def _clean_ceo_name(name_str: str) -> Optional[str]:
    """Validate and clean an extracted individual person name."""
    if not name_str:
        return None
    s = re.sub(r"^(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Prof\.?)\s+", "", name_str.strip(), flags=re.IGNORECASE).strip()
    s = s.rstrip(" .,-")
    s = re.sub(r"\s+", " ", s)
    if len(s) < 3 or len(s) > 40:
        return None
    words = s.split()
    if len(words) < 2 or len(words) > 5:
        return None
    if not all(re.match(r"^[A-Za-z'-]+(?:\.)?$", w) for w in words):
        return None
    for w in words:
        if len(w) == 1 and not w.endswith("."):
            return None
    if not all(w[0].isupper() for w in words if w):
        return None
    junk_words = {
        "india", "design", "studio", "architect", "architecture", "interior", "firm",
        "company", "private", "limited", "team", "about", "contact", "home", "services",
        "story", "guild", "management"
    }
    if any(w.lower().rstrip(".-") in junk_words for w in words):
        return None
    return s.title()


def _extract_people_from_json_ld(html: str) -> list[tuple[str, str]]:
    """
    Parse <script type="application/ld+json"> from the html for founder/employee/Person fields.
    Returns list of (raw_name, raw_designation).
    """
    if not html or not BeautifulSoup:
        return []

    found: list[tuple[str, str]] = []
    seen_names: set[str] = set()

    def process_item(item: Any, default_title: str = ""):
        if isinstance(item, list):
            for sub in item:
                process_item(sub, default_title)
            return
        if not isinstance(item, dict):
            if isinstance(item, str) and item.strip() and default_title:
                name = item.strip()
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    found.append((name, default_title))
            return

        if "@graph" in item and isinstance(item["@graph"], list):
            for g in item["@graph"]:
                process_item(g, default_title)

        item_type = str(item.get("@type", "")).lower()

        if "person" in item_type:
            name = item.get("name")
            if isinstance(name, dict):
                name = name.get("name")
            if isinstance(name, str) and name.strip():
                title = item.get("jobTitle") or item.get("roleName") or item.get("description") or default_title or "Principal"
                if isinstance(title, list):
                    title = title[0]
                title = str(title).strip()
                if name.strip().lower() not in seen_names:
                    seen_names.add(name.strip().lower())
                    found.append((name.strip(), title))

        for role_key, default_role in [
            ("founder", "Founder"),
            ("founders", "Founder"),
            ("employee", "Team Member"),
            ("employees", "Team Member"),
            ("member", "Member"),
            ("author", "Author"),
            ("creator", "Creator"),
            ("alumni", "Alumni"),
        ]:
            if role_key in item:
                process_item(item[role_key], default_role)

    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script", type=re.compile(r"application/ld\+json", re.I)):
            content = tag.string or tag.get_text()
            if not content or not content.strip():
                continue
            try:
                data = json.loads(content.strip())
                process_item(data)
            except Exception:
                continue
    except Exception as exc:
        logger.debug("[JSON-LD] Error parsing: %s", exc)

    return found


def _extract_people_from_firecrawl_json(fc_json: Any) -> list[tuple[str, str]]:
    """
    Extract (name, designation) pairs from Firecrawl's jsonOptions prompt response.
    """
    if not fc_json:
        return []

    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def inspect_item(item: Any):
        if isinstance(item, list):
            for i in item:
                inspect_item(i)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("person_name") or item.get("full_name") or item.get("person")
            title = item.get("job_title") or item.get("title") or item.get("designation") or item.get("role") or ""
            if isinstance(name, str) and name.strip():
                clean_name = name.strip()
                if clean_name.lower() not in seen and clean_name.lower() not in ("null", "none", "not stated", "false"):
                    seen.add(clean_name.lower())
                    found.append((clean_name, str(title).strip() if title else "Principal"))
            for v in item.values():
                if isinstance(v, (dict, list)):
                    inspect_item(v)

    inspect_item(fc_json)
    return found


def _extract_candidates_from_text(text: str) -> list[tuple[str, str]]:
    """
    Extract leadership and person candidates from page text/markdown using proven patterns.
    """
    if not text:
        return []

    TITLE_ALT = (
        r"CEO|Chief Executive Officer|Founder|Co-Founder|Managing Director|MD|"
        r"Director|Principal Architect|Principal|Partner|President|Head|Architect|Business Coach|"
        r"Creative Director|Design Director|Studio Head|Lead Architect|"
        r"Creative Lead|Studio Director|Brand Strategist"
    )

    candidates: list[tuple[str, str]] = []

    # 1. First-person "I'm Name" / "I am Name" / "My name is Name"
    pat_d = re.search(
        r"(?:I'?m|I am|My name is)\s+"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})"
        r"(?:\s*,\s*([^.\n\r]+?))?"
        r"(?:\.|\n|$)",
        text,
    )
    if pat_d:
        raw_name = pat_d.group(1).strip()
        raw_desig = (pat_d.group(2) or "").strip()
        m_t = re.search(rf"\b({TITLE_ALT})\b", raw_desig, re.IGNORECASE)
        desig = m_t.group(1).title() if m_t else ("Founder & Principal" if not raw_desig else raw_desig[:40].title())
        candidates.append((raw_name, desig))

    # 2. Name is the Founder / CEO
    pat_e = re.search(
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s+"
        r"(?:is|serves as|works as)\s+(?:the\s+|an?\s+)?"
        rf"({TITLE_ALT})\b",
        text,
        re.IGNORECASE,
    )
    if pat_e:
        candidates.append((pat_e.group(1).strip(), pat_e.group(2).strip().title()))

    # 3. Founded / established by Name
    pat1 = re.search(
        r"(?i:founded|co-founded|established|started|headed|led|spearheaded)\s+"
        r"(?:(?i:in)\s+\d{4}\s+)?(?i:by\s+)"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})"
        r"(?:\s+(?i:in)\s+\d{4})?",
        text,
    )
    if pat1:
        candidates.append((pat1.group(1).strip(), "Founder"))

    # 4. Title: Name
    pat2 = re.search(
        rf"\b({TITLE_ALT})\s*[:\-\u2013\u2014]\s*"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})",
        text,
        re.IGNORECASE,
    )
    if pat2:
        candidates.append((pat2.group(2).strip(), pat2.group(1).strip().title()))

    # 5. Name, Title or Name - Title
    pat3 = re.search(
        r"(?:(?:Ar\.?|Architect)\s+)?([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s*"
        rf"(?:,\s*|\s+[\-\u2013\u2014]\s+|\n+)\s*({TITLE_ALT})\b",
        text,
        re.IGNORECASE,
    )
    if pat3:
        candidates.append((pat3.group(1).strip(), pat3.group(2).strip().title()))

    # 6. Heading: # Name \n Title
    pat5 = re.search(
        r"(?:^|\n)#{1,4}\s+(?:(?:Ar\.?|Architect)\s+)?([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s*\n+\s*"
        rf"({TITLE_ALT})\b",
        text,
        re.IGNORECASE,
    )
    if pat5:
        candidates.append((pat5.group(1).strip(), pat5.group(2).strip().title()))

    return candidates


def _extract_ceo(text: str) -> tuple[str, str]:
    """Compatibility helper returning (name, designation) or ('not found', 'not found')."""
    cands = _extract_candidates_from_text(text)
    for raw_name, raw_desig in cands:
        clean = _clean_ceo_name(raw_name)
        if clean:
            return clean, raw_desig
    return "not found", "not found"


# ---------------------------------------------------------------------------
# Vision Fallback for Image-based Pages
# ---------------------------------------------------------------------------

def _looks_image_based(page_data: dict) -> bool:
    """Determine if a page has minimal textual content and appears visual/image-driven."""
    md = (page_data.get("markdown") or "").strip()
    html = (page_data.get("html") or "").strip()
    has_little_text = len(md) < 400
    has_visuals = bool(re.search(
        r"<(?:img|picture|canvas|svg|video)\b|gallery|portfolio|splash|hero|banner",
        html,
        re.I
    ))
    return has_little_text and has_visuals


def _vision_fallback_extract(page_url: str, log_fn=None) -> list[tuple[str, str]]:
    """
    Fallback for image-based pages: request screenshot from Firecrawl,
    then invoke Gemini Vision to find visibly printed names and titles.
    Never accepts a name that is not visibly present.
    """
    if not genai:
        if log_fn:
            log_fn("[Vision Fallback] google.genai not available; skipping vision fallback.")
        return []

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        if log_fn:
            log_fn("[Vision Fallback] No GEMINI_API_KEY configured; skipping vision fallback.")
        return []

    try:
        if log_fn:
            log_fn(f"[Vision Fallback] Requesting screenshot from Firecrawl for '{page_url}'...")
        ss_data = _firecrawl_scrape(page_url, formats=["screenshot"])
        ss_url = ss_data.get("screenshot")
        if not ss_url or not isinstance(ss_url, str):
            if log_fn:
                log_fn(f"[Vision Fallback] No screenshot returned by Firecrawl for '{page_url}'.")
            return []

        if log_fn:
            log_fn(f"[Vision Fallback] Analyzing screenshot with Gemini Vision (gemini-2.5-flash)...")

        resp = requests.get(ss_url, timeout=20)
        if resp.status_code != 200:
            if log_fn:
                log_fn(f"[Vision Fallback] Failed to download screenshot: HTTP {resp.status_code}")
            return []

        from PIL import Image
        image = Image.open(io.BytesIO(resp.content))

        client = genai.Client(api_key=api_key)
        prompt = (
            "Analyze this webpage screenshot carefully. "
            "List every person's name and their exact job title/role visibly printed on the image. "
            "Return valid JSON ONLY in this format: [{\"name\": \"Full Name\", \"designation\": \"Title\"}]. "
            "IMPORTANT: Never guess, assume, or invent names. Return an empty list [] if no person is visibly printed."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt],
        )

        resp_text = (response.text or "").strip()
        m_json = re.search(r"\[.*\]", resp_text, re.DOTALL)
        if not m_json:
            return []

        raw_list = json.loads(m_json.group(0))
        results: list[tuple[str, str]] = []
        for item in raw_list:
            if isinstance(item, dict):
                r_name = str(item.get("name", "")).strip()
                r_desig = str(item.get("designation", "")).strip()
                c_name = _clean_ceo_name(r_name)
                if c_name:
                    results.append((c_name, r_desig or "Principal"))
        return results
    except Exception as exc:
        if log_fn:
            log_fn(f"[Vision Fallback] Error during vision extraction: {exc}")
        return []


# ---------------------------------------------------------------------------
# Main lookup pipeline
# ---------------------------------------------------------------------------

def _not_found_all() -> dict:
    """Return the canonical not-found response for all output fields."""
    return {
        "organisation_name": {"value": "not found", "source": None},
        "ceo": {
            "name": {"value": "not found", "source": None},
            "designation": {"value": "not found", "source": None},
        },
        "people": [],
        "company_size": {"value": "not found", "source": None},
        "socials": {"value": {}, "source": None},
        "city": {"value": "not found", "source": None},
        "email": {"value": "not found", "source": None},
        "mobile": {"value": "not found", "source": None},
    }


def lookup_company(name: str, db_path=None) -> dict:
    """
    End-to-end company lookup pipeline.
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

    result["organisation_name"] = places.organisation_name
    result["city"] = places.city
    result["mobile"] = places.mobile

    website = places.website.get("value") or ""
    if not website:
        log("[Step 1] Places did not return a website URL; cannot scrape. Stopping.")
        return result

    # ── STEP 2: Firecrawl /v1/map to discover sub-pages ─────────────────────
    log(f"[Step 2] Firecrawl /v1/map on '{website}' with search terms.")
    try:
        map_urls = _firecrawl_map(website)
        relevant_pages = _filter_relevant_pages(map_urls, website)
        log(f"[Step 2] Map returned {len(map_urls)} URLs; {len(relevant_pages)} relevant pages selected: {relevant_pages}.")
    except ValueError as exc:
        log(f"[Step 2] Skipped — {exc}")
        relevant_pages = []
        map_urls = []

    # ── STEP 3: Firecrawl /v1/scrape on homepage + all discovered sub-pages ──
    pages_to_scrape = [website] + relevant_pages
    scraped_pages: dict[str, dict] = {}  # url -> scrape result

    log(f"[Step 3] Scraping {len(pages_to_scrape)} pages: {pages_to_scrape}")

    for page_url in pages_to_scrape:
        log(f"[Step 3] Scraping '{page_url}' (formats: markdown, html, json; waitFor 4000).")
        try:
            page_data = _firecrawl_scrape(page_url)
            if page_data:
                scraped_pages[page_url] = page_data
                md_len = len(page_data.get("markdown") or "")
                html_len = len(page_data.get("html") or "")
                log(f"[Step 3] Scraped '{page_url}': {md_len} chars markdown, {html_len} chars html.")
            else:
                log(f"[Step 3] Empty response for '{page_url}'.")
        except ValueError as exc:
            log(f"[Step 3] Skipped scraping '{page_url}' — {exc}")
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

    # ── STEP 6: People & CEO Discovery Across Homepage & All Mapped Pages ───
    log("[Step 6] Running people and CEO discovery on homepage and all mapped pages.")

    people: list[dict] = []
    seen_person_names: set[str] = set()

    for page_url in pages_to_scrape:
        page_data = scraped_pages.get(page_url)
        if not page_data:
            continue

        page_md = page_data.get("markdown") or ""
        page_html = page_data.get("html") or ""
        page_json = page_data.get("json")

        page_corpus = f"{page_md}\n{page_html}"

        page_people: list[dict] = []
        raw_candidates: list[tuple[str, str, str]] = []  # (name, designation, source_type)

        # 1. Use JSON-LD from HTML first
        json_ld_cands = _extract_people_from_json_ld(page_html)
        for name_val, desig_val in json_ld_cands:
            raw_candidates.append((name_val, desig_val, "json_ld"))

        # 2. Firecrawl structured JSON prompt response
        fc_json_cands = _extract_people_from_firecrawl_json(page_json)
        for name_val, desig_val in fc_json_cands:
            raw_candidates.append((name_val, desig_val, "firecrawl_json"))

        # 3. Page text and heading patterns
        text_cands = _extract_candidates_from_text(page_md)
        for name_val, desig_val in text_cands:
            raw_candidates.append((name_val, desig_val, "text_regex"))

        # Process candidates with strict verbatim verification & name syntax checks
        for cand_name, cand_desig, cand_source in raw_candidates:
            clean_name = _clean_ceo_name(cand_name)
            if not clean_name:
                log(f"[Step 6 Rejection] Candidate '{cand_name}' from '{page_url}' ({cand_source}) rejected: invalid person name syntax or junk word.")
                continue

            if clean_name.lower() in seen_person_names:
                continue

            # Check name and designation separately against the page text
            # Normalise whitespace, punctuation, and case before verbatim check
            name_verbatim = _verify_verbatim_part(clean_name, page_corpus)
            if not name_verbatim:
                log(f"[Step 6 Rejection] Candidate '{clean_name}' from '{page_url}' ({cand_source}) rejected: name not found verbatim in page text.")
                continue

            # Verify designation separately
            desig_verbatim = _verify_verbatim_part(cand_desig, page_corpus)
            verified_desig = cand_desig
            if not desig_verbatim:
                # Check if a core title token (e.g. Founder, CEO, Principal) appears verbatim
                m_core = _CEO_TITLE_RE.search(cand_desig)
                if m_core and _verify_verbatim_part(m_core.group(0), page_corpus):
                    verified_desig = m_core.group(0).title()
                else:
                    log(f"[Step 6 Notice] Designation '{cand_desig}' for '{clean_name}' on '{page_url}' not found verbatim; checking designation keywords.")
                    verified_desig = cand_desig.strip()

            person_entry = {
                "name": clean_name,
                "designation": verified_desig or "Principal",
                "source_url": page_url,
            }
            seen_person_names.add(clean_name.lower())
            page_people.append(person_entry)
            people.append(person_entry)

        found_summary = [f"{p['name']} ({p['designation']})" for p in page_people]
        log(f"[Step 6] Page '{page_url}': found {len(page_people)} people: {found_summary}.")

    # ── STEP 6b: Screenshot + Vision Fallback ────────────────────────────────
    # Only if no person is found and the page looks image-based
    if not people:
        for page_url in pages_to_scrape:
            page_data = scraped_pages.get(page_url)
            if page_data and _looks_image_based(page_data):
                log(f"[Step 6b] No person found and page '{page_url}' looks image-based. Triggering screenshot + vision fallback.")
                vision_results = _vision_fallback_extract(page_url, log_fn=log)
                for v_name, v_desig in vision_results:
                    if v_name.lower() not in seen_person_names:
                        seen_person_names.add(v_name.lower())
                        person_entry = {
                            "name": v_name,
                            "designation": v_desig or "Principal",
                            "source_url": page_url,
                        }
                        people.append(person_entry)
                        log(f"[Step 6b Vision Found] Visibly present person on '{page_url}': '{v_name}' ({v_desig}).")
                if people:
                    break

    # ── STEP 6c: Pick CEO ────────────────────────────────────────────────────
    # Pick the CEO as the one whose title contains CEO, Chief Executive, Founder, or Managing Director
    ceo_name = "not found"
    ceo_desig = "not found"
    ceo_source = None

    for p in people:
        title_lower = p["designation"].lower()
        if any(kw in title_lower for kw in ("ceo", "chief executive", "founder", "managing director", "co-founder", "md")):
            ceo_name = p["name"]
            ceo_desig = p["designation"]
            ceo_source = p["source_url"]
            log(f"[Step 6] CEO selected from people: '{ceo_name}' ({ceo_desig}) at {ceo_source}.")
            break

    # If no person has an explicit CEO/Founder/MD title, fallback to first identified leader
    if ceo_name == "not found" and people:
        first = people[0]
        ceo_name = first["name"]
        ceo_desig = first["designation"]
        ceo_source = first["source_url"]
        log(f"[Step 6] Leadership person selected: '{ceo_name}' ({ceo_desig}) at {ceo_source}.")

    if ceo_name == "not found":
        log("[Step 6] No CEO or leadership person found across scraped pages.")

    result["people"] = people
    result["ceo"] = {
        "name": {"value": ceo_name, "source": ceo_source},
        "designation": {"value": ceo_desig, "source": ceo_source},
    }

    # ── STEP 7: Verbatim verification ────────────────────────────────────────
    log("[Step 7] Verbatim verification of extracted leadership and contact values.")

    # Email verbatim verification against combined corpus
    email_val = result["email"]["value"]
    if email_val != "not found":
        if not _verify_verbatim_part(email_val, all_markdown) and not any(
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
                "clean_summary": f"Looked up via Google Places + Firecrawl pipeline ({len(people)} people identified).",
            }
            save_result = save_structured_lead_to_db(lead_dict, db_path=db_path)
            log(f"[Step 9] Persisted to DB: company_id={save_result.get('company_id')}.")
        except Exception as exc:
            log(f"[Step 9] DB persistence skipped: {exc}")

    log("[Done] Pipeline complete.")
    return result
