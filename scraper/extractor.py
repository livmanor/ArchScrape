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


# ─── Seniority ranking for Owner/Designation ──────────────────────────────────
_SENIORITY_RANKS: list[tuple[int, re.Pattern]] = [
    (1, re.compile(r"\b(founder|co-founder|owner|proprietor)\b", re.I)),
    (2, re.compile(r"\b(managing partner|managing director|ceo|chief executive officer)\b", re.I)),
    (3, re.compile(r"\b(principal architect|principal)\b", re.I)),
    (4, re.compile(r"\b(director|partner|design director|creative director|studio head)\b", re.I)),
    (5, re.compile(r"\b(head of design|lead architect|senior architect|associate architect|architect|interior designer)\b", re.I)),
]


def _designation_rank(title: str) -> int:
    for rank, pat in _SENIORITY_RANKS:
        if pat.search(title):
            return rank
    return 99


# ─── Stated Org Size and Team Buckets ─────────────────────────────────────────

def _to_size_bucket(count: int) -> str:
    if count <= 10:
        return "1-10"
    elif count <= 50:
        return "11-50"
    elif count <= 200:
        return "51-200"
    else:
        return "200+"


_STATED_SIZE_RES: list[re.Pattern] = [
    re.compile(
        r"\b(?:team|strength|staff|workforce|practice|firm|studio)\s+(?:of\s+)?(?:about|around|over|more than|approx(?:imately)?\s+)?(\d+)\+?\s*(?:professionals?|architects?|designers?|people|members?|employees?|talents?|specialists?)?\b",
        re.I,
    ),
    re.compile(
        r"\b(?:over|more than|nearly|around)?\s*(\d+)\+?\s+(?:professionals?|architects?|designers?|employees?|team members?|staff members?)\b",
        re.I,
    ),
    re.compile(
        r"\b(\d+)\s*(?:-|to)\s*(\d+)\s+(?:professionals?|architects?|designers?|employees?|people)\b",
        re.I,
    ),
]


_INVALID_NAME_WORDS = {
    "about", "team", "our team", "contact", "studio", "practice", "architecture",
    "architects", "interior", "interiors", "design", "designers", "services",
    "projects", "portfolio", "read more", "view all", "all rights", "copyright",
    "homepage", "profile", "leadership", "people", "awards", "news", "careers",
    "work", "works", "home", "search", "menu", "navigation", "india", "studio",
    "founder", "founders", "director", "architect", "management", "history", "philosophy",
}


def _clean_name(text: str) -> Optional[str]:
    if not text:
        return None
    clean = re.sub(r"\s+", " ", text).strip()
    clean = re.sub(r"^(?:Ar\.|Architect|Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+", "", clean, flags=re.I).strip()
    if len(clean) < 3 or len(clean) > 40:
        return None
    if clean.lower() in _INVALID_NAME_WORDS:
        return None
    parts = clean.split()
    if len(parts) < 2 or len(parts) > 5:
        return None
    if not all(re.match(r"^[A-Za-z'.-]+$", p) for p in parts):
        return None
    if any(p.lower() in _INVALID_NAME_WORDS for p in parts):
        return None
    return clean


def _is_junk_email(email: str) -> bool:
    if re.search(r"\.(png|jpg|jpeg|gif|svg|webp|pdf|doc|css|js|ico)$", email, re.I):
        return True
    junk_domains = {"example.com", "domain.com", "sample.com", "yourdomain.com", "email.com"}
    domain = email.split("@")[-1].lower()
    return domain in junk_domains


# ─── HTML content heuristics ─────────────────────────────────────────────────

def _extract_contact_page(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Extract business phone numbers and emails from mailto: links and visible text.
    """
    candidates: list[Candidate] = []
    text = soup.get_text(separator=" ", strip=True)

    # Phones
    phones = _extract_phones(text)
    for ph in phones[:5]:
        idx = text.find(ph)
        snippet = _snippet(text[max(0, idx - 60): idx + len(ph) + 60])
        candidates.append(Candidate(
            "phone", ph, source_url, snippet, "html_content",
            verification_status="Extracted",
        ))

    # Emails: mailto: links first, then text regex
    seen_emails: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            raw = href[7:].split("?")[0].strip()
            if _EMAIL_RE.match(raw) and not _is_junk_email(raw) and raw.lower() not in seen_emails:
                seen_emails.add(raw.lower())
                snippet = f'<a href="{href}">{a.get_text(strip=True) or raw}</a>'
                candidates.append(Candidate(
                    "email", raw, source_url, snippet, "html_content",
                    verification_status="Extracted",
                ))

    for em in _extract_emails(text):
        if not _is_junk_email(em) and em.lower() not in seen_emails:
            seen_emails.add(em.lower())
            idx = text.find(em)
            snippet = _snippet(text[max(0, idx - 60): idx + len(em) + 60])
            candidates.append(Candidate(
                "email", em, source_url, snippet, "html_content",
                verification_status="Extracted",
            ))

    return candidates


def _extract_team_members(soup: BeautifulSoup, source_url: str) -> list[tuple[str, str, int, str]]:
    """
    Finds (name, designation, rank, snippet) tuples from cards, headings, and text patterns.
    """
    team_members: list[tuple[str, str, int, str]] = []
    seen_names: set[str] = set()

    # 1. Cards with class names like team, member, person, profile, leader
    for card in soup.find_all(["div", "li", "article", "section"], class_=True):
        cls_str = " ".join(card.get("class", [])).lower()
        if any(k in cls_str for k in ("team", "member", "person", "leader", "profile", "bio", "founder", "staff")):
            name_tag = (
                card.find(["h2", "h3", "h4", "h5", "strong", "b"])
                or card.find(class_=re.compile(r"name", re.I))
            )
            desig_tag = (
                card.find(class_=re.compile(r"role|designation|title|position", re.I))
                or card.find(["p", "span"])
            )
            if name_tag:
                name_clean = _clean_name(name_tag.get_text(strip=True))
                if name_clean and name_clean.lower() not in seen_names:
                    d_text = desig_tag.get_text(strip=True) if desig_tag else ""
                    match = _DESIGNATION_RE.search(d_text)
                    desig = match.group(0) if match else (d_text if 3 < len(d_text) < 40 else "Architect")
                    rank = _designation_rank(desig)
                    snippet = _snippet(card.get_text(separator=" ", strip=True))
                    seen_names.add(name_clean.lower())
                    team_members.append((name_clean, desig, rank, snippet))

    # 2. Heading followed by designation in sibling
    for h in soup.find_all(["h2", "h3", "h4", "h5"]):
        name_clean = _clean_name(h.get_text(strip=True))
        if name_clean and name_clean.lower() not in seen_names:
            sib = h.find_next_sibling(["p", "span", "div", "h4", "h5", "h6"])
            if sib:
                sib_text = sib.get_text(strip=True)
                match = _DESIGNATION_RE.search(sib_text)
                if match:
                    desig = match.group(0)
                    rank = _designation_rank(desig)
                    snippet = f"{name_clean} — {sib_text}"
                    seen_names.add(name_clean.lower())
                    team_members.append((name_clean, desig, rank, snippet))

    # 3. Text patterns: "Name, Designation" or "Name - Designation"
    text = soup.get_text(separator="\n", strip=True)
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or len(line_clean) > 120:
            continue
        m = re.match(r"^([A-Z][A-Za-z. '\-]{2,35})\s*(?:,\s*|\s*[-–—]\s*|\s*\(\s*)([A-Za-z\s/]{3,50})\)?$", line_clean)
        if m:
            cand_name = _clean_name(m.group(1))
            cand_desig = m.group(2).strip()
            desig_m = _DESIGNATION_RE.search(cand_desig)
            if cand_name and desig_m and cand_name.lower() not in seen_names:
                desig = desig_m.group(0)
                rank = _designation_rank(desig)
                seen_names.add(cand_name.lower())
                team_members.append((cand_name, desig, rank, line_clean))

    return team_members


def _extract_org_size(soup: BeautifulSoup, source_url: str, team_count: int = 0) -> list[Candidate]:
    """
    Extract org size bucket + basis:
    (a) Regex for stated size ("team of 25", "50+ professionals", "over 100 employees")
    (b) Fallback to count of team members listed (lower bound)
    (c) Else "Not found"
    """
    text = soup.get_text(separator=" ", strip=True)
    candidates: list[Candidate] = []

    # 1. Stated size regex
    for pat in _STATED_SIZE_RES:
        m = pat.search(text)
        if m:
            groups = [g for g in m.groups() if g]
            if len(groups) == 2:
                try:
                    low = int(groups[0])
                    high = int(groups[1])
                    n = (low + high) // 2
                except ValueError:
                    n = int(groups[0])
            elif groups:
                try:
                    n = int(groups[0])
                except ValueError:
                    continue
            else:
                continue

            bucket = _to_size_bucket(n)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            snippet = _snippet(text[start:end])

            candidates.append(Candidate(
                "org_size", bucket, source_url, snippet, "html_content", "Extracted"
            ))
            candidates.append(Candidate(
                "org_size_basis", "stated", source_url, snippet, "html_content", "Extracted"
            ))
            return candidates

    # 2. Fallback to count of team members listed (lower bound)
    if team_count >= 2:
        bucket = _to_size_bucket(team_count)
        snippet = f"Counted {team_count} team members listed on {source_url}"
        candidates.append(Candidate(
            "org_size", bucket, source_url, snippet, "html_content", "Extracted"
        ))
        candidates.append(Candidate(
            "org_size_basis", "team_count", source_url, snippet, "html_content", "Extracted"
        ))
        return candidates

    # 3. Else "Not found" — never guess
    candidates.append(Candidate(
        "org_size", "Not found", source_url, "No stated team size or team list found on public pages",
        "html_content", "Not found"
    ))
    candidates.append(Candidate(
        "org_size_basis", "not_found", source_url, "No stated team size or team list found on public pages",
        "html_content", "Not found"
    ))
    return candidates


def _extract_about_page(soup: BeautifulSoup, source_url: str) -> list[Candidate]:
    """
    Look for person names + designations on about/team/leadership pages.
    Chooses the most senior person as owner.
    Always marks owner/designation as 'Needs review'.
    Also extracts org_size.
    """
    candidates: list[Candidate] = []
    text = soup.get_text(separator=" ", strip=True)

    # Scan team members
    team_members = _extract_team_members(soup, source_url)

    if team_members:
        # Sort by seniority rank (1 = Founder, 2 = MD/CEO, 3 = Principal, ...)
        team_members.sort(key=lambda x: x[2])
        senior = team_members[0]
        # Most senior person as owner
        candidates.append(Candidate(
            "owner_name", senior[0], source_url, senior[3],
            "html_content", "Needs review",
        ))
        candidates.append(Candidate(
            "designation", senior[1], source_url, senior[3],
            "html_content", "Needs review",
        ))
    else:
        # Fallback: scan designation keywords in text
        for m in _DESIGNATION_RE.finditer(text):
            designation = m.group(0)
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            context = _snippet(text[start:end])
            candidates.append(Candidate(
                "designation", designation, source_url, context,
                "html_content", "Needs review",
            ))

    # Org size from this page
    candidates.extend(_extract_org_size(soup, source_url, team_count=len(team_members)))

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
                break
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


def _extract_city(soup: BeautifulSoup, source_url: str, market_city: Optional[str] = None) -> list[Candidate]:
    text = soup.get_text(separator=" ", strip=True)
    matches = _CITY_RE.findall(text)
    if matches:
        from collections import Counter
        city = Counter(m.title() for m in matches).most_common(1)[0][0]
        idx = text.lower().find(city.lower())
        snippet = _snippet(text[max(0, idx - 60): idx + len(city) + 60])
        return [Candidate("city", city, source_url, snippet, "html_content", "Extracted")]

    # Fallback to market-city filter labelled "inferred"
    if market_city and market_city.strip():
        m_city = market_city.strip().title()
        return [Candidate(
            "city", m_city, source_url,
            f"Inferred from market city filter: {m_city}",
            "inferred", "Needs review",
        )]

    return []


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

# ─── Main extraction entry point ─────────────────────────────────────────────

def extract(
    html: str,
    source_url: str,
    page_role: str = "homepage",
    market_city: Optional[str] = None,
) -> list[Candidate]:
    """
    Extract all available business intelligence fields from an HTML page.

    Parameters
    ----------
    html:        Raw HTML string.
    source_url:  The URL the HTML was fetched from.
    page_role:   One of 'homepage', 'contact', 'about', 'team', 'services',
                 'portfolio' — controls which heuristics are applied.
    market_city: Optional market city filter for fallback city inference.

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

    # City (JSON-LD addresses take precedence, then HTML text, then market_city fallback)
    if not any(c.field_name == "city" for c in candidates):
        candidates.extend(_extract_city(soup, source_url, market_city=market_city))

    # Gallery images (useful for visual intelligence)
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
        # Homepage: contact extraction + about/team heuristics (for owner/size on homepage) + services + projects + awards
        candidates.extend(_extract_contact_page(soup, source_url))
        candidates.extend(_extract_about_page(soup, source_url))
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
