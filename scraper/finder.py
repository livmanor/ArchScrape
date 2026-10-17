"""
scraper/finder.py — Target Company Online Presence Resolution.

Resolves user-entered target company queries (company names, brand names, or domain/URLs)
to authentic, live website URLs without any mocking or fabrication.

Resolution hierarchy:
1. Direct URL/Domain input (e.g., 'https://www.mododesigns.co.in', 'studiolotus.in')
2. Approved seed and verified directory records (seed_urls.csv, ahmedabad_architecture_firms.csv, DB)
3. Domain slug probing (e.g., 'Studio Lotus' -> 'https://www.studiolotus.in/')
4. Wikipedia MediaWiki Architecture Directory & infobox parsing
5. Live Search Engine query with redirect decoding
"""

import base64
import csv
import logging
import pathlib
import re
import urllib.parse
from typing import Optional

import requests

from scraper.validator import validate_url, normalise_domain, URLValidationError

logger = logging.getLogger(__name__)

ROOT_DIR = pathlib.Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _check_known_csvs(query_norm: str) -> Optional[dict]:
    """Check known seed and firm CSV files for an exact or substring match."""
    csv_paths = [
        DATA_DIR / "chennai_architecture_firms.csv",
        DATA_DIR / "ahmedabad_architecture_firms.csv",
        DATA_DIR / "seed_urls.csv",
    ]
    for p in csv_paths:
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = (row.get("url") or "").strip()
                    notes = (row.get("notes") or "").strip()
                    cat = (row.get("category") or "architecture").strip()
                    if not url:
                        continue
                    # Match against notes or domain
                    domain = normalise_domain(url).lower()
                    notes_lower = notes.lower()
                    if query_norm in notes_lower or notes_lower in query_norm or query_norm in domain or domain in query_norm:
                        return {
                            "url": url,
                            "category": cat,
                            "source": "verified_registry",
                            "notes": notes or domain,
                        }
        except Exception as exc:
            logger.debug("Error reading seed CSV %s: %s", p, exc)
    return None


def _discover_firms_online(city: str, count: int = 20) -> list[dict]:
    """Query open web search to discover architecture firms in any city."""
    query = f"top architecture firms in {city} official website"
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    firms = []
    seen = set()
    try:
        resp = requests.get(search_url, timeout=6, headers=BROWSER_HEADERS)
        if resp.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("li.b_algo h2 a"):
                href = a.get("href", "")
                target_url = href
                m = re.search(r"u=(a1[a-zA-Z0-9_\-]+)", href)
                if m:
                    b64 = m.group(1)[2:]
                    b64 += "=" * (-len(b64) % 4)
                    try:
                        decoded = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
                        target_url = decoded
                    except Exception:
                        pass

                skip_domains = [
                    "bing.com", "microsoft.com", "wikipedia.org", "facebook.com", "instagram.com",
                    "linkedin.com", "twitter.com", "youtube.com", "justdial.com", "indiamart.com",
                    "sulekha.com", "quora.com", "tripadvisor.com", "glassdoor.co.in", "ambitionbox.com",
                    "architecturaldigest.in", "houzz.in", "reddit.com"
                ]
                if target_url.startswith("http") and not any(sd in target_url.lower() for sd in skip_domains):
                    try:
                        clean_url = validate_url(target_url)
                        domain = normalise_domain(clean_url)
                        if domain not in seen:
                            seen.add(domain)
                            title = a.get_text(strip=True).split(" - ")[0].split(" | ")[0]
                            firms.append({
                                "url": clean_url,
                                "category": "architecture",
                                "notes": f"{title} - {city.title()}",
                                "city": city.title(),
                            })
                            if len(firms) >= count:
                                break
                    except Exception:
                        pass
    except Exception as exc:
        logger.debug("Online firm discovery error for %s: %s", city, exc)
    return firms


def get_city_seed_companies(city: str, limit: int = 50) -> list[dict]:
    """Retrieve up to limit verified company records for a given city."""
    city_norm = city.strip().lower()
    city_aliases = [city_norm]
    if city_norm in ("delhi", "new delhi", "delhi ncr", "ncr"):
        city_aliases = ["delhi", "new delhi", "delhi ncr"]
    elif city_norm in ("bengaluru", "bangalore"):
        city_aliases = ["bengaluru", "bangalore"]
    elif city_norm in ("bombay", "mumbai"):
        city_aliases = ["mumbai", "bombay"]
    elif city_norm in ("hyderabad", "secunderabad"):
        city_aliases = ["hyderabad", "secunderabad"]

    results: list[dict] = []
    seen_urls: set[str] = set()

    # Look for matching city CSVs first
    csv_paths = []
    for alias in city_aliases:
        p = DATA_DIR / f"{alias}_architecture_firms.csv"
        if p.exists() and p not in csv_paths:
            csv_paths.append(p)

    # Then check all other firm CSVs
    for p in sorted(DATA_DIR.glob("*_architecture_firms.csv")):
        if p not in csv_paths:
            csv_paths.append(p)
    csv_paths.append(DATA_DIR / "seed_urls.csv")

    for p in csv_paths:
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = (row.get("url") or "").strip()
                    notes = (row.get("notes") or "").strip()
                    cat = (row.get("category") or "architecture").strip()
                    if not url or url in seen_urls:
                        continue

                    # If this CSV specifically matches the target city alias
                    is_city_csv = any(p.name.startswith(alias) for alias in city_aliases)
                    notes_match = any(alias in notes.lower() for alias in city_aliases)

                    if is_city_csv or notes_match:
                        seen_urls.add(url)
                        results.append({"url": url, "category": cat, "notes": notes, "city": city.title()})

                    if len(results) >= limit:
                        return results
        except Exception as exc:
            logger.debug("Error reading %s: %s", p, exc)

    # If the city had no predefined CSV or needs more firms to reach the requested limit, discover online
    if len(results) < limit:
        discovered = _discover_firms_online(city, count=limit - len(results))
        for d in discovered:
            if d["url"] not in seen_urls:
                seen_urls.add(d["url"])
                results.append(d)
                if len(results) >= limit:
                    break

    return results[:limit]


def _check_db(conn, query_norm: str) -> Optional[dict]:
    """Check existing SQLite database for matching companies."""
    try:
        rows = conn.execute(
            """
            SELECT c.seed_url, c.domain_key, c.category,
                   (SELECT extracted_value FROM evidence WHERE company_id = c.id AND field_name = 'org_name' LIMIT 1) as org_name
            FROM companies c
            """
        ).fetchall()
        for r in rows:
            url = r["seed_url"]
            dom = (r["domain_key"] or "").lower()
            org = (r["org_name"] or "").lower()
            if query_norm in dom or dom in query_norm or (org and (query_norm in org or org in query_norm)):
                return {
                    "url": url,
                    "category": r["category"] or "architecture",
                    "source": "local_database",
                    "notes": org or dom,
                }
    except Exception as exc:
        logger.debug("Error querying DB for company: %s", exc)
    return None


def _probe_domain_slugs(company_name: str) -> Optional[dict]:
    """
    Generate domain candidates from company name and test them with real HTTP requests.
    E.g. 'Studio Lotus' -> studiolotus.in, studiolotus.com
    'Sanjay Puri Architects' -> sanjaypuriarchitects.com
    """
    words = re.findall(r"[a-zA-Z0-9]+", company_name.lower())
    if not words:
        return None

    slug_full = "".join(words)
    slug_variants = [slug_full]

    # If multi-word, also test first word combinations e.g. "edifice", "edificearchitects"
    if len(words) > 1 and len(words[0]) >= 4:
        first = words[0]
        slug_variants.append(first)
        slug_variants.append(f"{first}architects")
        slug_variants.append(f"{first}design")
        slug_variants.append(f"{first}india")

    # Common architecture & interior firm TLDs in India
    tlds = [".in", ".com", ".co.in", ".org"]

    for slug in slug_variants:
        for tld in tlds:
            for prefix in ["https://www.", "https://"]:
                target = f"{prefix}{slug}{tld}"
                try:
                    # Validate first
                    validate_url(target, resolve_ip=False)
                    resp = requests.head(
                        target,
                        timeout=3.5,
                        allow_redirects=True,
                        headers=BROWSER_HEADERS,
                    )
                    if resp.status_code < 400 and resp.url:
                        clean_url = validate_url(resp.url)
                        return {
                            "url": clean_url,
                            "category": "architecture",
                            "source": "live_domain_resolution",
                            "notes": f"Probed domain {clean_url}",
                        }
                except Exception:
                    continue
    return None


def _query_wikipedia_official_site(company_name: str) -> Optional[dict]:
    """Query Wikipedia MediaWiki API for company official website."""
    search_queries = [
        f"{company_name} architecture",
        f"{company_name} architects",
        company_name,
    ]
    for q in search_queries:
        try:
            wiki_api = (
                f"https://en.wikipedia.org/w/api.php?action=opensearch&search="
                f"{urllib.parse.quote(q)}&limit=3&format=json"
            )
            resp = requests.get(
                wiki_api,
                timeout=4,
                headers={"User-Agent": "ArchScaleIntelligence/1.0 (contact@archscale.local)"},
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            titles = data[1] if len(data) > 1 else []
            for title in titles:
                parse_url = (
                    f"https://en.wikipedia.org/w/api.php?action=parse&page="
                    f"{urllib.parse.quote(title)}&prop=wikitext&format=json"
                )
                pr = requests.get(
                    parse_url,
                    timeout=4,
                    headers={"User-Agent": "ArchScaleIntelligence/1.0 (contact@archscale.local)"},
                )
                if pr.status_code != 200:
                    continue

                wt = pr.json().get("parse", {}).get("wikitext", {}).get("*", "")
                m = re.search(r"\{\{Official website\|([^\}\n\|]+)\}\}", wt, re.I) or re.search(
                    r"\|\s*website\s*=\s*(?:\{\{URL\|)?([^\}\n\|]+)", wt, re.I
                )
                if m:
                    raw_site = m.group(1).strip()
                    if not raw_site.startswith("http"):
                        raw_site = f"https://{raw_site}"
                    clean_site = validate_url(raw_site)
                    return {
                        "url": clean_site,
                        "category": "architecture",
                        "source": f"wikipedia_directory ({title})",
                        "notes": f"Verified via Wikipedia: {title}",
                    }
        except Exception as exc:
            logger.debug("Wikipedia resolution error for %s: %s", q, exc)

    return None


def _query_search_engine(company_name: str) -> Optional[dict]:
    """Query search engine and extract official website link."""
    query = f'"{company_name}" architecture official website'
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    try:
        resp = requests.get(search_url, timeout=5, headers=BROWSER_HEADERS)
        if resp.status_code != 200:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            target_url = href
            m = re.search(r"u=(a1[a-zA-Z0-9_\-]+)", href)
            if m:
                b64 = m.group(1)[2:]
                b64 += "=" * (-len(b64) % 4)
                try:
                    decoded = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
                    target_url = decoded
                except Exception:
                    pass

            if target_url.startswith("http") and not any(
                skip in target_url.lower() for skip in ["bing.com", "microsoft.com", "wikipedia.org", "facebook.com", "instagram.com", "linkedin.com", "twitter.com"]
            ):
                clean_url = validate_url(target_url)
                return {
                    "url": clean_url,
                    "category": "architecture",
                    "source": "live_web_search",
                    "notes": a.get_text(strip=True),
                }
    except Exception as exc:
        logger.debug("Search engine resolution error: %s", exc)
    return None


def resolve_company_url(
    target_input: str,
    db_conn=None,
    progress_callback=None,
) -> dict:
    """
    Resolve a target company query entered by the user into a validated URL.

    Parameters
    ----------
    target_input: Company name (e.g. 'Morphogenesis', 'Studio Lotus') or URL/domain.
    db_conn: Optional sqlite3.Connection to check local database.
    progress_callback: Optional callable for live progress status updates.

    Returns
    -------
    dict with keys:
        found: bool
        query: str
        url: Optional[str]
        domain: Optional[str]
        source: str
        notes: str
    """
    def log(msg: str):
        if progress_callback:
            progress_callback(msg)

    query = target_input.strip()
    if not query:
        return {"found": False, "query": "", "url": None, "domain": None, "source": "empty", "notes": "No input provided"}

    # ── 1. Direct URL / Domain input ──────────────────────────────────────────
    if query.startswith(("http://", "https://")):
        try:
            clean = validate_url(query)
            log(f"🔗 Direct URL entered: {clean}")
            return {
                "found": True,
                "query": query,
                "url": clean,
                "domain": normalise_domain(clean),
                "source": "direct_url",
                "notes": "Direct URL provided by user",
            }
        except URLValidationError as exc:
            return {"found": False, "query": query, "url": None, "domain": None, "source": "invalid_url", "notes": str(exc)}

    # If looks like a domain without scheme (e.g. 'morphogenesis.org', 'studiolotus.in')
    if "." in query and " " not in query and not query.endswith("."):
        try:
            clean = validate_url(f"https://{query}")
            log(f"🌐 Direct domain entered: {clean}")
            return {
                "found": True,
                "query": query,
                "url": clean,
                "domain": normalise_domain(clean),
                "source": "direct_domain",
                "notes": "Direct domain provided by user",
            }
        except URLValidationError:
            pass

    query_norm = query.lower()

    # ── 2. Check local database ───────────────────────────────────────────────
    if db_conn:
        log(f"🔍 Checking local verified records for '{query}'...")
        db_res = _check_db(db_conn, query_norm)
        if db_res:
            clean = validate_url(db_res["url"])
            log(f"✅ Found in local database: {clean}")
            return {
                "found": True,
                "query": query,
                "url": clean,
                "domain": normalise_domain(clean),
                "source": db_res["source"],
                "notes": db_res["notes"],
            }

    # ── 3. Check known approved CSV registries ────────────────────────────────
    log(f"📂 Checking approved architecture directory for '{query}'...")
    csv_res = _check_known_csvs(query_norm)
    if csv_res:
        clean = validate_url(csv_res["url"])
        log(f"✅ Discovered verified URL in directory: {clean}")
        return {
            "found": True,
            "query": query,
            "url": clean,
            "domain": normalise_domain(clean),
            "source": csv_res["source"],
            "notes": csv_res["notes"],
        }

    # ── 4. Intelligent live domain probe ─────────────────────────────────────
    log(f"⚡ Testing live domain variations for '{query}'...")
    probe_res = _probe_domain_slugs(query)
    if probe_res:
        clean = validate_url(probe_res["url"])
        log(f"✅ Live domain confirmed: {clean}")
        return {
            "found": True,
            "query": query,
            "url": clean,
            "domain": normalise_domain(clean),
            "source": probe_res["source"],
            "notes": probe_res["notes"],
        }

    # ── 5. Wikipedia Architecture Directory ───────────────────────────────────
    log(f"🏛️ Querying public architecture encyclopaedia for '{query}'...")
    wiki_res = _query_wikipedia_official_site(query)
    if wiki_res:
        clean = validate_url(wiki_res["url"])
        log(f"✅ Found official website from architecture directory: {clean}")
        return {
            "found": True,
            "query": query,
            "url": clean,
            "domain": normalise_domain(clean),
            "source": wiki_res["source"],
            "notes": wiki_res["notes"],
        }

    # ── 6. Live search engine query ───────────────────────────────────────────
    log(f"🌐 Querying live search index for '{query}'...")
    search_res = _query_search_engine(query)
    if search_res:
        clean = validate_url(search_res["url"])
        log(f"✅ Discovered official web address: {clean}")
        return {
            "found": True,
            "query": query,
            "url": clean,
            "domain": normalise_domain(clean),
            "source": search_res["source"],
            "notes": search_res["notes"],
        }

    return {
        "found": False,
        "query": query,
        "url": None,
        "domain": None,
        "source": "not_found",
        "notes": f"Could not resolve an official website for '{query}'. Please enter the company website URL directly.",
    }
