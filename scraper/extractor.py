"""
scraper/extractor.py — HTML and JSON-LD extraction pipeline.

Extracts business intelligence fields from:
1. JSON-LD structured data (schema.org)
2. HTML <meta> tags (Open Graph, general meta)
3. HTML content heuristics (contact pages, about pages)

Every extracted value retains:
- The exact source URL
- The extraction method
- A supporting text snippet
- An initial verification status of "Extracted" (not "Verified")

Design principles:
- Collect multiple candidates; do not arbitrarily pick one
- Never fabricate values; return None for absent fields
- Mark owner/founder fields as "Needs review" — ownership is high-risk
  to infer and must be manually confirmed
"""

import json
import logging
import re
import urllib.parse
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ─── Indian phone patterns ────────────────────────────────────────────────────
# Matches: +91-XXXXXXXXXX, 0XX-XXXXXXXX, +91 XXXXX XXXXX, 10-digit mobiles
_PHONE_RE = re.compile(
    r"""(?<!\d)(\+?91[-.\s]?)?                  # optional country code
        (\(?0\d{2,4}\)?[-.\s]?)?                # optional STD code
        ([6-9]\d{4}[-.\s]?\d{5}                 # Indian mobile
        |[2-9]\d{7,9})                          # landline
        (?!\d)""",
    re.VERBOSE,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# ─── Social media domain → field name ────────────────────────────────────────
_SOCIAL_DOMAINS: dict[str, str] = {
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "pinterest.com": "pinterest",
    "houzz.com": "houzz",
    "behance.net": "behance",
}

# ─── Designation patterns ─────────────────────────────────────────────────────
_DESIGNATION_RE = re.compile(
    r"\b(Founder|Co-Founder|Principal Architect|Managing Director|Director|"
    r"CEO|Chief Executive Officer|Partner|Principal|Head of Design|"
    r"Creative Director|Lead Architect|Senior Architect|Architect|"
    r"Interior Designer|Design Director|Studio Head)\b",
    re.IGNORECASE,
)


# ─── Data class for a candidate value ─────────────────────────────────────────

class Candidate:
    """A single extracted candidate for a given field."""
    __slots__ = ("field_name", "value", "source_url", "supporting_text",
                 "method", "verification_status")

    def __init__(
        self,
        field_name: str,
        value: Optional[str],
        source_url: str,
        supporting_text: Optional[str],
        method: str,
        verification_status: str = "Extracted",
    ) -> None:
        self.field_name = field_name
        self.value = value
        self.source_url = source_url
        self.supporting_text = supporting_text
        self.method = method
        self.verification_status = verification_status


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _snippet(text: str, maxlen: int = 300) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:maxlen] + ("…" if len(text) > maxlen else "")


def _clean(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _extract_phones(text: str) -> list[str]:
    raw = _PHONE_RE.findall(text)
    results = []
    for groups in raw:
        number = "".join(groups).strip()
        digits = re.sub(r"[^\d+]", "", number)
        if len(digits) >= 7:
            results.append(number.strip())
    return list(dict.fromkeys(results))  # dedupe, preserve order


def _extract_emails(text: str) -> list[str]:
    found = _EMAIL_RE.findall(text)
    # Filter out image/file extensions accidentally matched
    return list(dict.fromkeys(
        e for e in found
        if not re.search(r"\.(png|jpg|jpeg|gif|svg|webp|pdf|doc)$", e, re.I)
    ))


def _extract_social_links(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    results: list[Candidate] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        parsed = urllib.parse.urlparse(href)
        domain = parsed.netloc.lower().lstrip("www.")
        for sd, field in _SOCIAL_DOMAINS.items():
            if sd in domain and href not in seen:
                seen.add(href)
                results.append(Candidate(
                    field_name=field,
                    value=href,
                    source_url=source_url,
                    supporting_text=f'<a href="{href}">{a.get_text(strip=True)}</a>',
                    method="html_content",
                ))
    return results


# ─── JSON-LD extraction ───────────────────────────────────────────────────────

def _extract_jsonld(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            _parse_jsonld_item(item, source_url, candidates)

    return candidates


def _parse_jsonld_item(item: dict, source_url: str, out: list[Candidate]) -> None:
    schema_type = item.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = " ".join(schema_type)
    schema_type = schema_type.lower()

    raw_json = json.dumps(item, ensure_ascii=False)[:500]

    def add(field: str, val: Any, status: str = "Extracted") -> None:
        v = _clean(val)
        if v:
            out.append(Candidate(field, v, source_url, raw_json, "json_ld", status))

    # Organisation fields
    if any(t in schema_type for t in ("organization", "localbusiness", "professionalservice",
                                       "architecturalbusiness", "homeandconstructionbusiness")):
        add("org_name", item.get("name"))
        add("phone", item.get("telephone"))
        add("email", item.get("email"))
        add("website", item.get("url"))
        add("org_size", item.get("numberOfEmployees") or item.get("size"))

        addr = item.get("address")
        if isinstance(addr, dict):
            city = addr.get("addressLocality") or addr.get("addressRegion")
            add("city", city)
            full_addr = ", ".join(filter(None, [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
                addr.get("addressCountry"),
            ]))
            add("address", full_addr)
        elif isinstance(addr, str):
            add("address", addr)

        # Social links
        same_as = item.get("sameAs", [])
        if isinstance(same_as, str):
            same_as = [same_as]
        for sa_url in same_as:
            parsed = urllib.parse.urlparse(sa_url)
            domain = parsed.netloc.lower().lstrip("www.")
            for sd, field in _SOCIAL_DOMAINS.items():
                if sd in domain:
                    out.append(Candidate(field, sa_url, source_url, raw_json, "json_ld"))

    # Person fields (founders / owners)
    if "person" in schema_type:
        name = _clean(item.get("name"))
        if name:
            # Mark as Needs review — we cannot confirm ownership from JSON-LD alone
            out.append(Candidate(
                "owner_name", name, source_url, raw_json, "json_ld",
                verification_status="Needs review",
            ))
        job = _clean(item.get("jobTitle"))
        if job:
            out.append(Candidate(
                "designation", job, source_url, raw_json, "json_ld",
                verification_status="Needs review",
            ))

    # Handle nested founder/member arrays
    for key in ("founder", "founders", "member", "employee"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            val = [val]
        if isinstance(val, list):
            for person in val:
                if isinstance(person, dict):
                    _parse_jsonld_item(person, source_url, out)


# ─── Meta tag extraction ──────────────────────────────────────────────────────

def _extract_meta(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    candidates: list[Candidate] = []

    def meta(name: str) -> Optional[str]:
        tag = (
            soup.find("meta", attrs={"name": name})
            or soup.find("meta", attrs={"property": name})
        )
        if tag and isinstance(tag, Tag):
            return _clean(tag.get("content"))  # type: ignore[arg-type]
        return None

    title = _clean(soup.title.string if soup.title else None)
    if title:
        candidates.append(Candidate("page_title", title, source_url, f"<title>{title}</title>", "html_meta"))

    og_sitename = meta("og:site_name")
    if og_sitename:
        candidates.append(Candidate("org_name", og_sitename, source_url, f'<meta property="og:site_name" content="{og_sitename}">', "html_meta"))

    description = meta("description") or meta("og:description")
    if description:
        candidates.append(Candidate("description", description, source_url, description[:300], "html_meta"))

    return candidates


# ─── HTML content heuristics ─────────────────────────────────────────────────

def _extract_contact_page(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Extract phone numbers, emails from the visible text.
    Avoids treating every person on the page as an owner.
    """
    candidates: list[Candidate] = []
    text = soup.get_text(separator=" ", strip=True)

    phones = _extract_phones(text)
    for ph in phones[:5]:  # at most 5
        idx = text.find(ph)
        snippet = _snippet(text[max(0, idx - 60): idx + len(ph) + 60])
        candidates.append(Candidate(
            "phone", ph, source_url, snippet, "html_content",
            verification_status="Extracted",
        ))

    emails = _extract_emails(text)
    for em in emails[:5]:
        idx = text.find(em)
        snippet = _snippet(text[max(0, idx - 60): idx + len(em) + 60])
        candidates.append(Candidate(
            "email", em, source_url, snippet, "html_content",
        ))

    return candidates


def _extract_about_page(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Look for person names + designations on about/team/leadership pages.
    Marks everything as Needs review because ownership cannot be confirmed
    from HTML alone.
    """
    candidates: list[Candidate] = []
    text = soup.get_text(separator=" ", strip=True)

    # Look for designation keywords — use surrounding text as name candidate
    for m in _DESIGNATION_RE.finditer(text):
        designation = m.group(0)
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 80)
        context = _snippet(text[start:end])

        candidates.append(Candidate(
            "designation", designation, source_url, context,
            "html_content", "Needs review",
        ))

    return candidates


def _extract_org_name_from_html(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """Fall-back org name from heading tags."""
    candidates: list[Candidate] = []
    for tag_name in ("h1", "h2"):
        for tag in soup.find_all(tag_name):
            text = _clean(tag.get_text(separator=" ", strip=True))
            if text and 3 < len(text) < 120:
                candidates.append(Candidate(
                    "org_name", text, source_url,
                    f"<{tag_name}>{text}</{tag_name}>",
                    "html_content",
                ))
                break  # only first of each level
        if candidates:
            break
    return candidates


# ─── City extraction heuristics ──────────────────────────────────────────────

_INDIA_CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow",
    "Kanpur", "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam",
    "Pimpri-Chinchwad", "Patna", "Vadodara", "Ghaziabad", "Ludhiana",
    "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot", "Varanasi",
    "Srinagar", "Aurangabad", "Dhanbad", "Amritsar", "Navi Mumbai",
    "Allahabad", "Howrah", "Guwahati", "Ranchi", "Coimbatore", "Vijayawada",
    "Jodhpur", "Madurai", "Raipur", "Kochi", "Chandigarh", "Gurgaon",
    "Gurugram", "Noida", "Mysuru", "Mysore", "Bhubaneswar", "Thiruvananthapuram",
    "Tiruchirappalli", "Bareilly", "Aligarh", "Moradabad", "Jalandhar",
    "Bhiwandi", "Saharanpur", "Warangal", "Guntur", "New Delhi",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _INDIA_CITIES) + r")\b",
    re.IGNORECASE,
)


def _extract_city(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    text = soup.get_text(separator=" ", strip=True)
    matches = _CITY_RE.findall(text)
    if not matches:
        return []
    # Most frequent city is likely the business city
    from collections import Counter
    city = Counter(m.title() for m in matches).most_common(1)[0][0]
    idx = text.lower().find(city.lower())
    snippet = _snippet(text[max(0, idx - 60): idx + len(city) + 60])
    return [Candidate("city", city, source_url, snippet, "html_content")]


# ─── Website field ────────────────────────────────────────────────────────────

def _extract_services(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Extract services, products, or project types offered by the firm.
    Looks for list items, service cards, and heading-preceded paragraphs.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()

    # Service keywords to look for in section headings
    SERVICE_SECTION_KW = re.compile(
        r"\b(services?|what we do|our work|solutions?|offerings?|expertise|capabilities|"
        r"projects?|portfolio|specializ|product|design services?)\b",
        re.IGNORECASE,
    )

    # Look for sections that likely describe services
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        heading_text = heading.get_text(strip=True)
        if not SERVICE_SECTION_KW.search(heading_text):
            continue

        # Collect list items or paragraphs following this heading
        sibling = heading.find_next_sibling()
        collected = 0
        while sibling and collected < 12:
            if sibling.name in ("ul", "ol"):
                for li in sibling.find_all("li"):
                    val = _clean(li.get_text(separator=" ", strip=True))
                    if val and 4 < len(val) < 200 and val not in seen:
                        seen.add(val)
                        candidates.append(Candidate(
                            "service", val, source_url,
                            f"Under '{heading_text}': {val}",
                            "html_content",
                        ))
                        collected += 1
            elif sibling.name in ("p", "div"):
                val = _clean(sibling.get_text(separator=" ", strip=True))
                if val and 8 < len(val) < 300 and val not in seen:
                    seen.add(val)
                    candidates.append(Candidate(
                        "service", val, source_url,
                        f"Under '{heading_text}': {val}",
                        "html_content",
                    ))
                    collected += 1
            elif sibling.name in ("h1", "h2", "h3", "h4"):
                break  # reached next section
            sibling = sibling.find_next_sibling()

    return candidates[:15]


def _extract_projects(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Extract project names, portfolio entries, or case study titles.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()

    PROJECT_KW = re.compile(
        r"\b(project|portfolio|case study|our work|featured work|completed|"
        r"residential|commercial|luxury|interior|renovation|architecture)\b",
        re.IGNORECASE,
    )

    # Look for article/card elements that mention project names
    for container in soup.find_all(["article", "section", "div"], class_=True):
        cls_str = " ".join(container.get("class", []))
        if not PROJECT_KW.search(cls_str):
            continue
        # Get heading inside the container
        heading = container.find(["h2", "h3", "h4", "h5"])
        if heading:
            val = _clean(heading.get_text(separator=" ", strip=True))
            if val and 4 < len(val) < 150 and val not in seen:
                seen.add(val)
                desc_el = container.find("p")
                desc = _clean(desc_el.get_text(separator=" ", strip=True)) if desc_el else None
                snippet = f"Project: {val}" + (f" — {desc[:100]}" if desc else "")
                candidates.append(Candidate(
                    "project", val, source_url, snippet, "html_content",
                ))

    return candidates[:10]


def _extract_gallery_images(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Extract image URLs that look like portfolio/gallery photos.
    """
    candidates: list[Candidate] = []
    seen: set[str] = set()
    base_parsed = urllib.parse.urlparse(source_url)

    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
        if not src:
            continue
        # Resolve relative
        abs_src = urllib.parse.urljoin(source_url, src)
        if abs_src in seen:
            continue

        # Filter out tiny icons, logos, base64
        if "data:image" in abs_src or abs_src in seen:
            continue

        parsed_img = urllib.parse.urlparse(abs_src)
        # Only same-domain or HTTPS images
        if parsed_img.scheme not in ("http", "https"):
            continue

        alt = _clean(img.get("alt", "")) or ""
        if any(skip in abs_src.lower() for skip in ["logo", "icon", "favicon", "avatar", "sprite", "pixel"]):
            continue

        seen.add(abs_src)
        candidates.append(Candidate(
            "gallery_image", abs_src, source_url,
            f'<img src="{abs_src}" alt="{alt}">',
            "html_content",
        ))

        if len(candidates) >= 12:
            break

    return candidates


def _extract_awards(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """Extract awards, recognitions, certifications."""
    candidates: list[Candidate] = []
    AWARD_KW = re.compile(
        r"\b(award|recognition|certified|accredited|winner|finalist|honour|honor|"
        r"achievement|accolade|ranking|best|top)\b",
        re.IGNORECASE,
    )
    text = soup.get_text(separator=" ", strip=True)
    for m in AWARD_KW.finditer(text):
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 120)
        snippet = _snippet(text[start:end])
        if len(snippet) > 20:
            candidates.append(Candidate(
                "award", snippet, source_url, snippet, "html_content",
            ))
        if len(candidates) >= 5:
            break
    return candidates


# ─── Website field ────────────────────────────────────────────────────────────

def _extract_website(source_url: str) -> Candidate:
    parsed = urllib.parse.urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return Candidate("website", base, source_url, f"Seed URL: {base}", "structured")


# ─── Main extraction entry point ─────────────────────────────────────────────

def extract(html: str, source_url: str, page_role: str = "homepage") -> list[Candidate]:
    """
    Extract all available business intelligence fields from an HTML page.

    Parameters
    ----------
    html:       Raw HTML string.
    source_url: The URL the HTML was fetched from.
    page_role:  One of 'homepage', 'contact', 'about', 'team', 'services',
                'portfolio' — controls which heuristics are applied.

    Returns
    -------
    List of Candidate objects. Multiple candidates for the same field are
    allowed and expected.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        logger.warning("Failed to parse HTML from %s: %s", source_url, exc)
        return []

    candidates: list[Candidate] = []

    # JSON-LD (highest confidence for structured data)
    candidates.extend(_extract_jsonld(soup, source_url))

    # Meta tags
    candidates.extend(_extract_meta(soup, source_url))

    # Social links (all pages)
    candidates.extend(_extract_social_links(soup, source_url))

    # Org name from headings (fallback)
    if not any(c.field_name == "org_name" for c in candidates):
        candidates.extend(_extract_org_name_from_html(soup, source_url))

    # Website
    candidates.append(_extract_website(source_url))

    # City
    candidates.extend(_extract_city(soup, source_url))

    # Gallery images (all pages — useful for competitor visual intelligence)
    candidates.extend(_extract_gallery_images(soup, source_url))

    # Page-role specific extraction
    if page_role == "contact":
        candidates.extend(_extract_contact_page(soup, source_url))

    elif page_role in ("about", "team", "leadership", "people", "founders"):
        candidates.extend(_extract_about_page(soup, source_url))
        candidates.extend(_extract_contact_page(soup, source_url))

    elif page_role in ("services", "solutions"):
        candidates.extend(_extract_services(soup, source_url))
        candidates.extend(_extract_contact_page(soup, source_url))

    elif page_role in ("portfolio", "projects", "work"):
        candidates.extend(_extract_projects(soup, source_url))
        candidates.extend(_extract_gallery_images(soup, source_url))

    else:
        # Homepage: light contact extraction + services + projects
        candidates.extend(_extract_contact_page(soup, source_url))
        candidates.extend(_extract_services(soup, source_url))
        candidates.extend(_extract_projects(soup, source_url))
        candidates.extend(_extract_awards(soup, source_url))

    return candidates


def classify_page_role(url: str) -> str:
    """Infer the page role from the URL path."""
    path = urllib.parse.urlparse(url).path.lower()
    for kw in ("contact",):
        if kw in path:
            return "contact"
    for kw in ("service", "solution", "expertise", "offering"):
        if kw in path:
            return "services"
    for kw in ("portfolio", "projects", "work", "gallery"):
        if kw in path:
            return "portfolio"
    for kw in ("about", "studio", "firm"):
        if kw in path:
            return "about"
    for kw in ("team", "people", "leadership", "founders", "principal"):
        if kw in path:
            return "team"
    return "homepage"



# ─── Main extraction entry point ─────────────────────────────────────────────

def extract(html: str, source_url: str, page_role: str = "homepage") -> list[Candidate]:
    """
    Extract all available business intelligence fields from an HTML page.

    Parameters
    ----------
    html:       Raw HTML string.
    source_url: The URL the HTML was fetched from.
    page_role:  One of 'homepage', 'contact', 'about', 'team' — controls
                which heuristics are applied.

    Returns
    -------
    List of Candidate objects. Multiple candidates for the same field are
    allowed and expected.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        logger.warning("Failed to parse HTML from %s: %s", source_url, exc)
        return []

    candidates: list[Candidate] = []

    # JSON-LD (highest confidence for structured data)
    candidates.extend(_extract_jsonld(soup, source_url))

    # Meta tags
    candidates.extend(_extract_meta(soup, source_url))

    # Social links (all pages)
    candidates.extend(_extract_social_links(soup, source_url))

    # Org name from headings (fallback)
    if not any(c.field_name == "org_name" for c in candidates):
        candidates.extend(_extract_org_name_from_html(soup, source_url))

    # Website
    candidates.append(_extract_website(source_url))

    # City
    candidates.extend(_extract_city(soup, source_url))

    # Page-role specific extraction
    if page_role in ("contact",):
        candidates.extend(_extract_contact_page(soup, source_url))
    elif page_role in ("about", "team", "leadership", "people", "founders"):
        candidates.extend(_extract_about_page(soup, source_url))
        candidates.extend(_extract_contact_page(soup, source_url))
    else:
        # Homepage: light contact extraction
        candidates.extend(_extract_contact_page(soup, source_url))

    return candidates


def classify_page_role(url: str) -> str:
    """Infer the page role from the URL path."""
    path = urllib.parse.urlparse(url).path.lower()
    for kw in ("contact",):
        if kw in path:
            return "contact"
    for kw in ("about", "studio", "firm"):
        if kw in path:
            return "about"
    for kw in ("team", "people", "leadership", "founders", "principal"):
        if kw in path:
            return "team"
    return "homepage"
