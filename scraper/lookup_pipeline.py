"""
scraper/lookup_pipeline.py — Unified company lookup pipeline with OpenRouter LLM extraction.

Pipeline steps:
1. Cache check (SQLite): 30 days for identity, 7 days for people/size, 2 days for not_found.
2. Google Places API (New) text search:
   - If no result's name matches every word of searched name -> match_status: "not_found", all fields "not found", source null.
   - If multiple plausible branches match -> match_status: "ambiguous", short list of candidates, stop immediately.
   - Fields from Places: organisation_name, city (addressComponents only), mobile, website.
3. Firecrawl /v1/map on Places website:
   - Search terms: about, team, leadership, founder, people, story, guild, management, who we are, contact.
4. Parallel scraping (asyncio.gather):
   - Homepage + top relevant pages (max 6). Formats ["markdown", "html"], waitFor 4000, onlyMainContent false.
5. Match check:
   - Confirm scraped site belongs to the Places business (compare domain, title/intro with Places name).
   - If unsure/unmatched -> match_status: "ambiguous", no data merged.
6. Extraction & Verification:
   - Parse <script type="application/ld+json"> (founder, employee, Person) before LLM results.
   - Async OpenRouter LLM extraction (extract_fields) on each page in parallel.
   - Verbatim verification (scraper.verify): check name and designation SEPARATELY post-normalisation.
   - Require role word (CEO, Chief Executive, Founder, Co-founder, Managing Director, Director, Principal, Partner) to qualify as leader.
   - Pick CEO: person whose title contains CEO, Chief Executive, Founder, or Managing Director.
   - Code-based extraction for email (mailto:, tel:, social links). Obfuscated email fallback via LLM.
7. Persistence & Caching:
   - Persist to SQLite database with source attribution.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import time
from typing import Any, Callable, Coroutine, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from scraper.llm_client import extract_fields
from scraper.lookup_cache import get_cached_lookup, save_cached_lookup
from scraper.places_client import PlacesResult, places_text_search
from scraper.rate_limiter import (
    check_and_increment_openrouter_quota,
    check_and_increment_places_quota,
    execute_deduplicated_lookup,
)
from scraper.verify import is_leader_role, normalise_text, verify_in_text, verify_llm_extraction, verify_social_url

logger = logging.getLogger(__name__)

FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_JUNK_EMAIL_DOMAINS = {
    "example.com", "sample.com", "domain.com", "yourdomain.com",
    "wix.com", "sentry.io", "wordpress.org", "schema.org",
    "github.com", "email.com", "w3.org",
}

_SOCIAL_DOMAINS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
}

_RELEVANT_PAGE_KEYWORDS = [
    "about", "team", "leadership", "founder", "people",
    "story", "guild", "management", "who we are", "who-we-are", "whoweare", "contact"
]

_CEO_PRIORITY_TITLES = [
    "ceo", "chief executive", "founder", "co-founder", "managing director", "md"
]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _fc_api_key() -> Optional[str]:
    return (os.environ.get("FIRECRAWL_API_KEY") or "").strip() or None


def _fc_headers() -> dict:
    key = _fc_api_key()
    if not key:
        raise ValueError("FIRECRAWL_API_KEY environment variable is not set.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ─── Firecrawl /v1/map ────────────────────────────────────────────────────────

async def _firecrawl_map_async(client: httpx.AsyncClient, website: str) -> list[str]:
    key = _fc_api_key()
    if not key:
        return []

    try:
        resp = await client.post(
            f"{FIRECRAWL_API_URL}/v1/map",
            headers=_fc_headers(),
            json={
                "url": website,
                "search": "about team leadership founder people story guild management who we are contact",
                "limit": 25,
            },
            timeout=25.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            links = data.get("links") or data.get("urls") or []
            return [l for l in links if isinstance(l, str)]
        logger.warning("[FC Map] HTTP %d for '%s': %.200s", resp.status_code, website, resp.text)
    except Exception as exc:
        logger.warning("[FC Map] Error mapping '%s': %s", website, exc)
    return []


def _filter_relevant_pages(candidate_urls: list[str], homepage: str) -> list[str]:
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

    return selected[:6]  # Max 6 relevant subpages


# ─── Parallel Scraping ────────────────────────────────────────────────────────

async def _firecrawl_scrape_page_async(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, dict[str, Any]]:
    key = _fc_api_key()
    if not key:
        return url, {}

    payload = {
        "url": url,
        "formats": ["markdown", "html"],
        "waitFor": 4000,
        "onlyMainContent": False,
    }
    try:
        resp = await client.post(
            f"{FIRECRAWL_API_URL}/v1/scrape",
            headers=_fc_headers(),
            json=payload,
            timeout=50.0,
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or {}
            return url, data
        logger.warning("[FC Scrape] HTTP %d for '%s': %.200s", resp.status_code, url, resp.text)
    except Exception as exc:
        logger.warning("[FC Scrape] Error scraping '%s': %s", url, exc)
    return url, {}


# ─── Match Check ──────────────────────────────────────────────────────────────

def _confirm_site_match(
    searched_name: str,
    website: str,
    homepage_html: str,
    homepage_md: str,
) -> tuple[bool, str]:
    """
    Confirm the scraped site belongs to the Places business:
    compare domain and page title/intro with the Places name and address.
    """
    domain = urlparse(website).netloc.lower().replace("www.", "")
    domain_slug = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])

    # Reject known directory/aggregator domains immediately
    for agg in ("wallstowonder", "nobroker", "justdial", "sulekha", "indiamart", "magicbricks", "housing", "99acres", "houzz"):
        if agg in domain:
            return False, f"rejected_aggregator_domain_{agg}"

    # Significant words from business name
    name_words = [
        w.lower()
        for w in searched_name.split()
        if len(w) >= 3 and w.lower() not in ("pvt", "ltd", "llp", "inc", "the", "and", "co", "firm", "studio")
    ]
    if not name_words:
        name_words = [w.lower() for w in searched_name.split()]

    # 1. Domain token check
    if any(w in domain_slug for w in name_words):
        return True, "domain_token_match"

    # 2. Page title & H1 check
    title = ""
    h1 = ""
    try:
        soup = BeautifulSoup(homepage_html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        h1_tag = soup.find("h1")
        if h1_tag:
            h1 = h1_tag.get_text(strip=True)
    except Exception:
        pass

    combined_header = f"{title} {h1} {homepage_md[:300]}".lower()
    matches = sum(1 for w in name_words if re.search(r"\b" + re.escape(w) + r"\b", combined_header))
    if matches >= max(1, len(name_words) // 2):
        return True, "header_token_match"

    # If domain and headers have zero overlap with company name words
    return False, "unmatched_domain_and_header"


# ─── Contact Channels ────────────────────────────────────────────────────────

def _extract_emails_from_code(html: str, markdown: str) -> list[str]:
    found: set[str] = set()

    # 1. mailto: links in HTML
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                raw = href[7:].split("?")[0].strip()
                if _EMAIL_RE.match(raw):
                    domain = raw.split("@")[-1].lower()
                    if domain not in _JUNK_EMAIL_DOMAINS:
                        found.add(raw.lower())
    except Exception:
        pass

    # 2. Literal emails in markdown text
    for em in _EMAIL_RE.findall(markdown):
        domain = em.split("@")[-1].lower()
        if domain not in _JUNK_EMAIL_DOMAINS and not re.search(r"\.(png|jpg|jpeg|gif|svg|webp|pdf)$", em, re.I):
            found.add(em.lower())

    return sorted(list(found))


def _extract_socials_from_links(links: list[str], business_name: str = "") -> dict[str, str]:
    socials: dict[str, str] = {}
    for link in links:
        if not isinstance(link, str) or not link.startswith("http"):
            continue
        try:
            domain = urlparse(link).netloc.lower().replace("www.", "")
        except Exception:
            continue
        for platform_domain, platform_name in _SOCIAL_DOMAINS.items():
            if platform_domain in domain and platform_name not in socials:
                v_link = verify_social_url(platform_name, link, business_name=business_name)
                if v_link:
                    socials[platform_name] = v_link
    return socials


# ─── JSON-LD Structured Data ─────────────────────────────────────────────────

def _extract_people_from_json_ld(html: str) -> list[tuple[str, str]]:
    people: list[tuple[str, str]] = []
    if not html or "<script" not in html:
        return people

    try:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
            except Exception:
                continue

            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue

                # Check Person types
                schema_type = str(item.get("@type", "")).lower()
                if "person" in schema_type:
                    name = str(item.get("name") or "").strip()
                    job = str(item.get("jobTitle") or "").strip()
                    if name:
                        people.append((name, job or "Founder"))

                # Check founder, employee, member fields
                for k in ("founder", "founders", "employee", "member"):
                    val = item.get(k)
                    if isinstance(val, dict):
                        n = str(val.get("name") or "").strip()
                        j = str(val.get("jobTitle") or "").strip()
                        if n:
                            people.append((n, j or "Founder"))
                    elif isinstance(val, list):
                        for sub in val:
                            if isinstance(sub, dict):
                                n = str(sub.get("name") or "").strip()
                                j = str(sub.get("jobTitle") or "").strip()
                                if n:
                                    people.append((n, j or "Founder"))
    except Exception as exc:
        logger.debug("[JSON-LD] Error parsing JSON-LD: %s", exc)

    return people


# ─── Core Async Pipeline ─────────────────────────────────────────────────────

async def lookup_company(
    name: str,
    db_path: Optional[str | Any] = None,
    refresh: bool = False,
    website_override: Optional[str] = None,
    progress_callback: Optional[Callable[[str, Any], None]] = None,
) -> dict[str, Any]:
    """
    Unified company lookup pipeline.
    """
    start_time = time.time()
    sources_called: list[str] = []

    def notify(event: str, data: Any) -> None:
        if progress_callback:
            try:
                progress_callback(event, data)
            except Exception:
                pass

    clean_name = " ".join(name.strip().split())
    if not clean_name:
        return {
            "organisation_name": {"value": "not found", "source": None},
            "ceo": {"name": {"value": "not found", "source": None}, "designation": {"value": "not found", "source": None}},
            "people": [],
            "company_size": {"value": "not found", "source": None},
            "socials": {},
            "city": {"value": "not found", "source": None},
            "email": {"value": "not found", "source": None},
            "mobile": {"value": "not found", "source": None},
            "services": [],
            "locations": [],
            "match_status": "not_found",
            "retrieved_at": _now_iso(),
        }

    # ── 1. Cache Check ───────────────────────────────────────────────────────
    cached = get_cached_lookup(clean_name, db_path=str(db_path) if db_path else None, refresh=refresh)
    if cached and not website_override:
        logger.info("[Lookup] Returning cached result for '%s'", clean_name)
        notify("done", cached)
        return cached

    # Deduplicate in-flight concurrent requests for the exact same query
    async def _run() -> dict[str, Any]:
        return await _lookup_company_impl(clean_name, db_path, notify, sources_called, start_time, website_override=website_override)

    result = await execute_deduplicated_lookup(clean_name, _run)

    # Save to SQLite cache
    place_id = result.get("raw_place_id") or None
    website_val = result.get("website", {}).get("value")
    domain = urlparse(website_val).netloc if website_val and website_val != "not found" else None

    save_cached_lookup(
        clean_name,
        result,
        db_path=str(db_path) if db_path else None,
        place_id=place_id,
        domain=domain,
    )

    return result


async def _lookup_company_impl(
    name: str,
    db_path: Optional[str | Any],
    notify: Callable[[str, Any], None],
    sources_called: list[str],
    start_time: float,
    website_override: Optional[str] = None,
) -> dict[str, Any]:
    # Empty result template
    empty_ceo = {"name": {"value": "not found", "source": None}, "designation": {"value": "not found", "source": None}}
    result: dict[str, Any] = {
        "organisation_name": {"value": "not found", "source": None},
        "ceo": empty_ceo,
        "people": [],
        "company_size": {"value": "not found", "source": None},
        "socials": {},
        "city": {"value": "not found", "source": None},
        "email": {"value": "not found", "source": None},
        "mobile": {"value": "not found", "source": None},
        "services": [],
        "locations": [],
        "match_status": "not_found",
        "retrieved_at": _now_iso(),
    }

    # ── STEP 1: Google Places API (New) ──────────────────────────────────────
    check_and_increment_places_quota(str(db_path) if db_path else None)
    sources_called.append("google_places")
    t0 = time.time()

    places = places_text_search(name)
    logger.info("[Step 1] Google Places completed in %.2fs (Found: %s)", time.time() - t0, bool(places))

    if places is None:
        if website_override:
            logger.info("[Step 1] Places did not find '%s', but website_override '%s' provided. Proceeding to website discovery.", name, website_override)
            website_url = website_override
            result["organisation_name"] = {"value": name, "source": "input"}
            result["match_status"] = "matched"
        else:
            logger.info("[Step 1] No name-matching place found for '%s'. Returning not_found.", name)
            result["match_status"] = "not_found"
            notify("done", result)
            return result
    else:
        # Ambiguity: multiple plausible branches
        if places.ambiguous:
            logger.info("[Step 1] Places returned %d plausible branches for '%s'. Flagging ambiguous.", len(places.candidates), name)
            result["match_status"] = "ambiguous"
            result["candidates"] = places.candidates
            result["organisation_name"] = places.organisation_name
            notify("done", result)
            return result

        # Sourced from Places
        result["raw_place_id"] = places.place_id
        result["organisation_name"] = places.organisation_name
        result["city"] = places.city  # from addressComponents only, never from query
        result["mobile"] = places.mobile
        result["match_status"] = "matched"

        notify("places", {
            "organisation_name": result["organisation_name"],
            "city": result["city"],
            "mobile": result["mobile"],
            "website": places.website,
            "match_status": result["match_status"],
        })

        website_url = website_override or (places.website.get("value") or "").strip()
        if not website_url or website_url == "not found":
            logger.info("[Step 1] Places did not return a website URL. Lookup complete with Places data.")
            notify("done", result)
            return result

    # ── STEP 2: Discovery & Parallel Scraping ─────────────────────────────────
    async with httpx.AsyncClient() as http_client:
        # Map subpages
        sources_called.append("firecrawl_map")
        t_map = time.time()
        map_links = await _firecrawl_map_async(http_client, website_url)
        relevant_subpages = _filter_relevant_pages(map_links, website_url)
        pages_to_scrape = [website_url] + relevant_subpages
        logger.info("[Step 2] Firecrawl /v1/map in %.2fs. Selected %d pages: %s", time.time() - t_map, len(pages_to_scrape), pages_to_scrape)

        # Scrape all pages in parallel with asyncio.gather
        sources_called.append("firecrawl_scrape")
        t_scrape = time.time()
        scrape_tasks = [_firecrawl_scrape_page_async(http_client, u) for u in pages_to_scrape]
        scraped_tuples = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        logger.info("[Step 3] Parallel scrape of %d pages finished in %.2fs", len(pages_to_scrape), time.time() - t_scrape)

        scraped_pages: dict[str, dict[str, Any]] = {}
        for item in scraped_tuples:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict) and item[1]:
                scraped_pages[item[0]] = item[1]

        if not scraped_pages:
            logger.warning("[Step 3] No pages successfully scraped from %s. Returning Places data.", website_url)
            notify("done", result)
            return result

        hp_data = scraped_pages.get(website_url) or next(iter(scraped_pages.values()))
        hp_html = hp_data.get("html") or ""
        hp_md = hp_data.get("markdown") or ""

        # ── STEP 4: Match Check (Requirement 4) ──────────────────────────────
        matched, match_reason = _confirm_site_match(name, website_url, hp_html, hp_md)
        if not matched:
            logger.warning("[MatchCheck] Site %s does not match Places business '%s' (%s). Flagging ambiguous.", website_url, name, match_reason)
            result["match_status"] = "ambiguous"
            result["ambiguity_reason"] = f"Website domain/content did not match business name '{name}'"
            notify("done", result)
            return result

        # ── STEP 5: Contact Channels Extraction (Code) ───────────────────────
        all_markdown = "\n\n".join(p.get("markdown") or "" for p in scraped_pages.values())
        all_links: list[str] = []
        for p in scraped_pages.values():
            l_obj = p.get("links") or []
            if isinstance(l_obj, list):
                all_links.extend(l_obj)

        code_emails = _extract_emails_from_code(hp_html, all_markdown)
        if code_emails:
            result["email"] = {"value": code_emails[0], "source": website_url}

        socials = _extract_socials_from_links(all_links, business_name=name)
        if socials:
            result["socials"] = {k: {"value": v, "source": website_url} for k, v in socials.items()}

        notify("website", {
            "pages_scraped": list(scraped_pages.keys()),
            "email": result["email"],
            "socials": result["socials"],
        })

        # ── STEP 6: Structured & LLM Intelligence Extraction ──────────────────
        sources_called.append("openrouter_llm")
        t_llm = time.time()

        # Parse JSON-LD across all scraped pages first
        json_ld_people: list[dict[str, Any]] = []
        for p_url, p_data in scraped_pages.items():
            for p_name, p_role in _extract_people_from_json_ld(p_data.get("html") or ""):
                json_ld_people.append({
                    "name": p_name,
                    "designation": p_role,
                    "source": p_url,
                })

        # Run extract_fields with OpenRouter on each scraped page in parallel
        # Check OpenRouter daily quota before calling
        check_and_increment_openrouter_quota(str(db_path) if db_path else None)

        llm_tasks = [
            extract_fields(p_data.get("markdown") or p_data.get("html") or "", p_url)
            for p_url, p_data in scraped_pages.items()
        ]
        llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)
        logger.info("[Step 6] OpenRouter parallel extraction completed in %.2fs", time.time() - t_llm)

        all_verified_people: list[dict[str, Any]] = []
        all_verified_services: list[dict[str, str]] = []
        all_verified_locations: list[dict[str, str]] = []
        verified_size: Optional[dict[str, Any]] = None
        seen_names: set[str] = set()

        # Include JSON-LD people (already from source HTML)
        for jp in json_ld_people:
            n_clean = jp["name"].strip()
            if normalise_text(n_clean) not in seen_names:
                seen_names.add(normalise_text(n_clean))
                all_verified_people.append(jp)

        # Verify LLM extracted fields against respective page text
        page_urls = list(scraped_pages.keys())
        for idx, item in enumerate(llm_results):
            if isinstance(item, Exception) or not isinstance(item, dict):
                continue
            curr_url = page_urls[idx] if idx < len(page_urls) else website_url
            page_text = scraped_pages[curr_url].get("markdown") or scraped_pages[curr_url].get("html") or ""

            # Verbatim verification
            verified_data = verify_llm_extraction(item, page_text, curr_url)

            # People
            for p in verified_data.get("people", []):
                n_norm = normalise_text(p["name"])
                if n_norm and n_norm not in seen_names:
                    seen_names.add(n_norm)
                    all_verified_people.append(p)

            # Services
            for s in verified_data.get("services", []):
                if not any(s["value"].lower() == ex["value"].lower() for ex in all_verified_services):
                    all_verified_services.append(s)

            # Locations
            for loc in verified_data.get("locations", []):
                if not any(loc["value"].lower() == ex["value"].lower() for ex in all_verified_locations):
                    all_verified_locations.append(loc)

            # Company size
            if not verified_size and verified_data.get("company_size"):
                verified_size = verified_data["company_size"]

            # Socials from OpenRouter (verified against aggregator handles)
            for plat, s_obj in verified_data.get("socials", {}).items():
                if plat not in result["socials"] and s_obj.get("value"):
                    result["socials"][plat] = s_obj

        # Pick CEO: person whose title contains CEO, Chief Executive, Founder, or Managing Director
        ceo_person = None
        for p in all_verified_people:
            desig_norm = normalise_text(p["designation"])
            if any(title in desig_norm for title in _CEO_PRIORITY_TITLES):
                ceo_person = p
                break

        # Fallback to any leader role (Principal, Partner, Director)
        if not ceo_person:
            for p in all_verified_people:
                if is_leader_role(p["designation"]):
                    ceo_person = p
                    break

        if ceo_person:
            result["ceo"] = {
                "name": {"value": ceo_person["name"], "source": ceo_person["source"]},
                "designation": {"value": ceo_person["designation"], "source": ceo_person["source"]},
            }

        result["people"] = all_verified_people
        result["services"] = all_verified_services
        result["locations"] = all_verified_locations
        if verified_size:
            result["company_size"] = verified_size

        notify("intelligence", {
            "ceo": result["ceo"],
            "people": result["people"],
            "services": result["services"],
            "locations": result["locations"],
            "company_size": result["company_size"],
        })

    # ── STEP 7: DB Persistence ───────────────────────────────────────────────
    if db_path is not None:
        try:
            from services.company_service import save_structured_lead_to_db
            lead_dict = {
                "url": website_url,
                "organisation": result["organisation_name"]["value"],
                "owner_name": result["ceo"]["name"]["value"] if result["ceo"]["name"]["value"] != "not found" else None,
                "designation": result["ceo"]["designation"]["value"] if result["ceo"]["designation"]["value"] != "not found" else None,
                "city": result["city"]["value"] if result["city"]["value"] != "not found" else None,
                "org_size": result["company_size"]["value"] if result["company_size"]["value"] != "not found" else None,
                "emails": [result["email"]["value"]] if result["email"]["value"] != "not found" else [],
                "phones": [result["mobile"]["value"]] if result["mobile"]["value"] != "not found" else [],
                "socials": {k: v["value"] for k, v in result["socials"].items()},
                "services": [s["value"] for s in result["services"]],
                "clean_summary": f"Unified lookup via Google Places + Firecrawl + OpenRouter ({len(all_verified_people)} people).",
            }
            save_structured_lead_to_db(lead_dict, db_path=db_path)
            logger.info("[Step 7] Saved lead to SQLite database.")
        except Exception as exc:
            logger.debug("[Step 7] DB persistence skipped: %s", exc)

    logger.info(
        "[Lookup Complete] '%s' finished in %.2fs (Sources: %s, Status: %s)",
        name,
        time.time() - start_time,
        ", ".join(sources_called),
        result["match_status"],
    )

    notify("done", result)
    return result


def lookup_company_sync(
    name: str,
    db_path: Optional[str | Any] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper for lookup_company."""
    return asyncio.run(lookup_company(name=name, db_path=db_path, refresh=refresh))
