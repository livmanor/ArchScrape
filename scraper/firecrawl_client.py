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
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, Union

import requests
from dotenv import load_dotenv

load_dotenv()

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
    # Structured executive intelligence fields
    organisation: str = ""
    owner_name: str = ""
    designation: str = ""
    city: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    socials: dict[str, str] = field(default_factory=dict)
    org_size: str = ""
    services: list[str] = field(default_factory=list)
    clean_summary: str = ""
    verification_status: str = "Extracted"
    confidence: str = "Medium"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "organisation": self.organisation or self.title,
            "owner_name": self.owner_name or "Not found",
            "designation": self.designation or "Not found",
            "city": self.city or "Not found",
            "emails": self.emails,
            "phones": self.phones,
            "socials": self.socials,
            "org_size": self.org_size or "Not stated",
            "services": self.services,
            "clean_summary": self.clean_summary or self.description,
            "verification_status": self.verification_status,
            "confidence": self.confidence,
        }


import html as py_html

# ─── Structured Lead Extraction Rules ────────────────────────────────────────

# Domains that are aggregator, review, listing, marketplace, social, or forum sites.
# Any search hit whose domain matches ANY entry here is dropped immediately.
_EXCLUDED_DOMAINS = {
    # ── Social / Video / Forums ──────────────────────────────────────────────
    "youtube.com", "youtu.be", "quora.com", "reddit.com", "pinterest.com", "pinterest.in",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "wikipedia.org", "medium.com", "tumblr.com", "blogger.com", "blogspot.com",
    "snapchat.com", "whatsapp.com",

    # ── Review / Rating sites ────────────────────────────────────────────────
    "yelp.com", "trustpilot.com", "trustpilot.in", "glassdoor.co.in", "glassdoor.com",
    "mouthshut.com", "sitejabber.com", "reviews.io", "g2.com", "capterra.com",
    "ambitionbox.com",

    # ── Indian business / property listing directories ────────────────────────
    "justdial.com", "sulekha.com", "indiamart.com", "tradeindia.com",
    "nobroker.in", "nobroker.com",
    "magicbricks.com", "99acres.com", "housing.com", "makaan.com", "proptiger.com",
    "commonfloor.com", "squareyards.com",
    "quikr.com", "olx.in", "olx.com",
    "urbanclap.com", "urbancompany.com",
    "houzz.com", "houzz.in",
    "yellowpages.com", "yellowpages.in",
    "exotica.in", "homify.in", "homify.com",
    "buildofy.com", "buildzar.com",
    "designcafe.com",          # large chain — keep only if user explicitly searches it
    "livspace.com",            # large chain / marketplace
    "pepperfry.com", "urban-ladder.com", "urbanladder.com",
    "coinsurance.com", "policybazaar.com",
    "zomato.com", "swiggy.com", "blinkit.com",
    "practo.com", "1mg.com", "lenskart.com",
    "quickerala.com", "quickrr.com",
    "servicesutra.com", "getit.in", "asklaila.com",
    "clickindia.com", "locanto.in",
    "jdmagicbox.com", "grotal.com", "burrp.com",

    # ── Job boards / recruitment ─────────────────────────────────────────────
    "naukri.com", "indeed.com", "monster.com", "shine.com", "foundit.in",
    "timesjobs.com", "freshersworld.com", "internshala.com", "instahyre.com",
    "linkedin.com", "apna.co",

    # ── E-commerce / Marketplaces ────────────────────────────────────────────
    "amazon.in", "amazon.com", "flipkart.com", "myntra.com", "meesho.com",
    "snapdeal.com", "paytmmall.com",

    # ── News / Blog aggregators ──────────────────────────────────────────────
    "times of india", "timesofindia.com", "hindustan times", "hindustantimes.com",
    "ndtv.com", "thehindu.com", "moneycontrol.com", "livemint.com",
    "economictimes.indiatimes.com", "indiatimes.com", "business-standard.com",
    "outlookindia.com", "scroll.in", "thequint.com", "deccanherald.com",
    "architecturaldigest.com", "architecturaldigest.in", "elle.in", "elle.com",
    "architectandinterior.com", "archello.com", "archdaily.com", "dezeen.com",
    "behance.net", "issuu.com", "slideshare.net",
    "wikimedia.org", "wikidata.org",

    # ── Maps / local search wrappers ─────────────────────────────────────────
    "maps.google.com", "goo.gl", "waze.com",
}

# URL path patterns that indicate a listing / directory / "best X in city" page
# rather than a real company's own website. Matched against the URL path.
_LISTING_URL_PATH_RE = re.compile(
    r"/(best|top|leading|find|hire|compare|all|list-of)[-_]?"
    r"(interior[-_]?designers?|architects?|architecture|interior[-_]?design|home[-_]?interiors?|decorators?)"
    r"([-_]in[-_]|[-_]near[-_]|[-_]at[-_]|[-_]\w+[-_]|/)",
    re.IGNORECASE,
)

_INVALID_SOCIAL_PATHS = {
    "home", "share", "sharer", "sharer.php", "intent", "feed", "explore",
    "login", "signup", "terms", "privacy", "help", "about", "search", "policies",
    "pin", "pins", "p", "reel", "reels", "tv", "stories", "watch", "embed",
    "shorts", "playlist", "status", "hashtag", "intent", "results"
}

_GENERIC_TITLE_PATTERNS = [
    re.compile(r'^(?:top|best|leading|cheap and best|popular|recommended|find|discover|affordable)\s+.*\b(?:interior|interiors|architect|architecture|designers?|firms?|companies|studios?|decorators?|services?)\b.*$', re.I),
    re.compile(r'^\d{1,2}\s+(?:best|top|leading)\s+.*\b(?:interior|interiors|architect|architecture|designers?|firms?)\b.*$', re.I),
    re.compile(r'^(?:interior designers?|architects?|home interiors?|modular kitchens?)\s+(?:in|near|at)\s+.*$', re.I),
    re.compile(r'^(?:top modular kitchen designs|best interior designers in \w+|top interior designers in \w+).*$', re.I),
    # Review / listing page titles from aggregators
    re.compile(r'\b(?:reviews?|ratings?|complaints?|listing|directory|verified professionals|hire|compare|find near)\b.*\b(?:interior|architect|design)\b', re.I),
    re.compile(r'\b(?:interior|architect)\b.*\b(?:reviews?|ratings?|listing|directory|near me|in \w+ city)\b', re.I),
]

_INVALID_PERSON_WORDS = {
    "about", "team", "our team", "contact", "studio", "practice", "architecture",
    "architects", "interior", "interiors", "design", "designers", "services",
    "projects", "portfolio", "read more", "view all", "all rights", "copyright",
    "homepage", "profile", "leadership", "people", "awards", "news", "careers",
    "work", "works", "home", "search", "menu", "navigation", "india", "founder",
    "founders", "director", "architect", "management", "history", "philosophy",
    "delhi", "mumbai", "bengaluru", "hyderabad", "chennai", "pune", "kolkata",
    "ahmedabad", "ncr", "firm", "company", "private", "limited", "pvt", "ltd",
    "solutions", "innovations", "creations", "atelier", "associates", "group",
    "marble", "granite", "wood", "glass", "steel", "concrete", "lighting", "furniture",
    "contemporary", "sustainable", "urban", "residential", "commercial", "hospitality",
    # Stop words, pronouns, auxiliary verbs, and marketing descriptors
    "are", "we", "the", "proud", "co", "our", "they", "you", "he", "she", "it",
    "this", "that", "these", "those", "with", "from", "for", "and", "or", "not",
    "have", "has", "had", "been", "being", "was", "were", "their", "your", "my",
    "his", "her", "its", "who", "whom", "which", "what", "whose", "why", "how",
    "when", "where", "get", "got", "make", "made", "meet", "know", "let", "join",
    "see", "look", "find", "call", "tell", "ask", "help", "helps", "lead", "leads",
    "best", "top", "good", "great", "new", "old", "first", "last", "high", "low",
    "big", "small", "large", "next", "early", "young", "important", "few", "public",
    "same", "able", "expert", "experts", "specialist", "specialists", "professional",
    "professionals", "passionate", "dedicated", "experienced", "trusted", "skilled",
    "reputed", "creative", "innovative", "dynamic", "award", "winning", "certified",
    "licensed", "registered", "qualified", "builder", "builders", "contractor", "contractors"
}

_CITY_MAP: dict[str, str] = {
    "new delhi": "Delhi NCR",
    "delhi": "Delhi NCR",
    "noida": "Delhi NCR",
    "gurgaon": "Delhi NCR",
    "gurugram": "Delhi NCR",
    "faridabad": "Delhi NCR",
    "ghaziabad": "Delhi NCR",
    "mumbai": "Mumbai",
    "navi mumbai": "Mumbai",
    "thane": "Mumbai",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "hyderabad": "Hyderabad",
    "secunderabad": "Hyderabad",
    "chennai": "Chennai",
    "madras": "Chennai",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",
    "pune": "Pune",
    "ahmedabad": "Ahmedabad",
    "gandhinagar": "Ahmedabad",
    "jaipur": "Jaipur",
    "chandigarh": "Chandigarh",
    "kochi": "Kochi",
    "cochin": "Kochi",
    "goa": "Goa",
    "panaji": "Goa",
    "surat": "Surat",
    "vadodara": "Vadodara",
    "baroda": "Vadodara",
    "lucknow": "Lucknow",
    "indore": "Indore",
    "coimbatore": "Coimbatore",
    "bhopal": "Bhopal",
    "visakhapatnam": "Visakhapatnam",
    "vizag": "Visakhapatnam",
}

_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_JUNK_EMAIL_DOMAINS = {
    "example.com", "sample.com", "domain.com", "yourdomain.com",
    "wix.com", "sentry.io", "wordpress.org", "schema.org", "github.com", "email.com"
}

_PHONE_REGEX = re.compile(
    r"""(?<!\d)(\+?91[-.\s]?)?(\(?0?\d{2,4}\)?[-.\s]?)?([6-9]\d{4}[-.\s]?\d{5}|[2-9]\d{6,9})(?!\d)""",
    re.VERBOSE,
)

_SOCIAL_PLATFORMS: dict[str, str] = {
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "houzz.com": "houzz",
    "houzz.in": "houzz",
    "youtube.com": "youtube",
    "behance.net": "behance",
    "pinterest.com": "pinterest",
    "twitter.com": "twitter",
    "x.com": "twitter",
}

_SERVICE_PATTERNS: list[tuple[str, str]] = [
    ("Architecture", r"\b(architecture|architectural design|building design)\b"),
    ("Interior Design", r"\b(interior design|interiors|interior architecture|decor)\b"),
    ("Urban Planning", r"\b(urban design|urban planning|masterplanning|master planning)\b"),
    ("Landscape", r"\b(landscape architecture|landscape design)\b"),
    ("Residential", r"\b(residential|villas|bungalows|luxury homes|apartments|housing)\b"),
    ("Commercial", r"\b(commercial|corporate|offices|workplaces|retail)\b"),
    ("Hospitality", r"\b(hospitality|hotels|resorts|restaurants|cafes)\b"),
    ("Sustainable Design", r"\b(sustainable design|green building|eco-friendly|griha|leed)\b"),
]


def _clean_single_name(name_str: str) -> Optional[str]:
    """Validate and clean an extracted individual person name."""
    if not name_str:
        return None
    s = re.sub(r"^(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+", "", name_str.strip(), flags=re.I).strip()
    s = s.rstrip(" .,-")
    s = re.sub(r"\s+", " ", s)
    if len(s) < 3 or len(s) > 40:
        return None
    words = s.split()
    if len(words) < 2 or len(words) > 5:
        return None
    if not all(re.match(r"^[A-Za-z'-]+(?:\.)?$", w) for w in words):
        return None
    tokens = {w.lower().rstrip(".-") for w in words}
    if tokens & _INVALID_PERSON_WORDS:
        return None
    # Reject names containing single-letter words that aren't recognized initials
    for w in words:
        if len(w) == 1 and not w.endswith("."):
            return None
    # Each word must start with an uppercase letter
    if not all(w[0].isupper() for w in words if w):
        return None
    return s.title()


def _validate_names(raw_joined_names: str) -> Optional[str]:
    """Validate multiple or single names separated by and/&/comma."""
    parts = re.split(r",|\s+and\s+|\s*&\s*", raw_joined_names, flags=re.I)
    cleaned = []
    for p in parts:
        c = _clean_single_name(p)
        if c and c not in cleaned:
            cleaned.append(c)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + " & " + cleaned[-1]


def extract_org_name_from_text(title: str, url: str, description: str = "") -> str:
    """
    Extract clean organisation/firm name from title, url domain, and description.
    Resolves generic SEO titles (e.g. 'Best Interior Designers in Chennai') into
    real company brand names (e.g. 'Anbre Interiors', 'Bizzoppo Interiors').
    """
    t = (title or "").strip()

    # Determine domain brand name as strong anchor
    domain_brand = ""
    try:
        parsed = urllib.parse.urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc.lower().lstrip("www.")
        raw_brand = domain.split(".")[0]
        raw_brand = re.sub(r"[-_]", " ", raw_brand).strip()
        if raw_brand and raw_brand.lower() not in (
            "facebook", "linkedin", "instagram", "twitter", "houzz", "behance", "youtube", "quora"
        ):
            domain_brand = raw_brand.title()
    except Exception:
        pass

    # Check if the title is a generic SEO title
    is_generic_title = any(p.match(t) for p in _GENERIC_TITLE_PATTERNS)

    # 1. If title has standard brand delimiters, inspect parts
    for delim in [" | ", " - ", " – ", " — ", " :: ", " : ", " • ", " · ", " ~ "]:
        if delim in t:
            parts = [p.strip() for p in t.split(delim) if p.strip()]
            for part in parts:
                p_lower = part.lower()
                if any(kw in p_lower for kw in [
                    "home", "about", "contact", "official website", "portfolio",
                    "top architect", "best architect", "leading architect",
                    "architecture firm", "interior design", "design studio",
                    "architects in", "designers in", "recent work", "projects",
                    "reviews", "photos"
                ]):
                    continue
                if any(p.match(part) for p in _GENERIC_TITLE_PATTERNS):
                    continue
                if len(part) >= 2 and not part.isdigit():
                    return part

    # 2. If title is generic (e.g. "Top Modular Kitchen Designs" or "Best Interior Designers in Chennai"),
    # look in description or domain for the true business name
    if is_generic_title or not t:
        if domain_brand:
            # Check if domain brand appears in description, e.g. "Anbre: Best home interiors..." -> "Anbre Interiors"
            desc_text = f"{t} {description}"
            m_brand_ext = re.search(
                rf'\b({re.escape(domain_brand)}(?:\s+(?:Interiors?|Architects?|Designs?|Studio|Decorators?|Solutions|Living))?)\b',
                desc_text,
                re.I,
            )
            if m_brand_ext:
                candidate = m_brand_ext.group(1).strip()
                if 2 <= len(candidate) <= 40:
                    return candidate.title()
            return domain_brand

    # 3. Clean trailing SEO phrases from title
    clean_t = re.sub(
        r"\s*[\-\|•:–—]\s*(Home|Official Website|About|Contact|Top Architects?|Best Architects?|Leading Architecture.*|Architects? in [A-Za-z]+|Interior Designers? in [A-Za-z]+|Architecture & Interior Design.*|Architecture firm.*|Architecture Studio|India).*$",
        "",
        t,
        flags=re.I,
    ).strip()

    if clean_t and not any(p.match(clean_t) for p in _GENERIC_TITLE_PATTERNS) and 2 <= len(clean_t) <= 45:
        return clean_t

    if domain_brand:
        return domain_brand

    return t or "Unknown Organisation"


def extract_owner_and_designation(text: str) -> tuple[str, str]:
    """
    Extract (owner_name, designation) from scraped text/markdown with strict validation.
    Returns ('Not found', 'Not found') if no verified leadership info exists.
    """
    if not text:
        return "Not found", "Not found"

    TITLE_ALT = (
        r"Founder(?:\s*(?:and|&)\s*(?:Principal Architect|CEO|Managing Director|Partner))?|"
        r"Co-Founder|Principal Architect|Managing Director|Creative Director|Design Director|"
        r"Studio Head|Lead Architect|Partner|Principal|CEO|Chief Executive Officer|Director|"
        r"President|Business Coach|Creative Lead|Studio Director|Brand Strategist|Head"
    )

    # 1. First-person "I'm Name" / "I am Name" / "My name is Name" bio pattern
    pat1 = re.search(
        r"(?:I'?m|I am|My name is)\s+"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})"
        r"(?:\s*,\s*([^.\n\r]+?))?"
        r"(?:\.|\n|$)",
        text,
    )
    if pat1:
        clean = _clean_single_name(pat1.group(1))
        if clean:
            raw_desig = (pat1.group(2) or "").strip()
            m_t = re.search(rf"\b({TITLE_ALT})\b", raw_desig, re.I)
            desig = m_t.group(1).title() if m_t else ("Founder & Principal" if not raw_desig else raw_desig[:40].title())
            return clean, desig

    # 2. "Name is/serves as the CEO/Founder"
    pat2 = re.search(
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s+"
        r"(?:is|serves as|works as)\s+(?:the\s+|an?\s+)?"
        rf"({TITLE_ALT})\b",
        text,
        re.I,
    )
    if pat2:
        clean = _clean_single_name(pat2.group(1))
        if clean:
            return clean, pat2.group(2).strip().title()

    # 3. Founded/established by Name [& Name]
    pat3 = re.search(
        r"(?i:founded|co-founded|established|started|headed|led|spearheaded)\s+"
        r"(?:(?i:in)\s+\d{4}\s+)?(?i:by\s+)"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,4}(?:\s*(?:&|and|,)\s*[A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,4})*)"
        r"(?:\s+(?i:in)\s+\d{4})?",
        text,
    )
    if pat3:
        raw_names = pat3.group(1).strip()
        valid_names = _validate_names(raw_names)
        if valid_names:
            desig = (
                "Founding Partner & Principal Architect"
                if ("&" in valid_names or "and" in valid_names.lower())
                else "Founder & Principal Architect"
            )
            return valid_names, desig

    # 4. Designation: Name
    pat4 = re.search(
        rf"\b({TITLE_ALT})\s*[:\-\u2013\u2014]\s*"
        r"(?:(?:Ar\.?|Architect|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+)?"
        r"([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})",
        text,
        re.I,
    )
    if pat4:
        desig = pat4.group(1).strip()
        clean = _clean_single_name(pat4.group(2))
        if clean:
            return clean, desig.title()

    # 5. Name, Designation or Name — Designation
    pat5 = re.search(
        r"(?:(?:Ar\.?|Architect)\s+)?([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s*"
        rf"(?:,\s*|\s+[\-\u2013\u2014]\s+|\n+)\s*({TITLE_ALT})\b",
        text,
        re.I,
    )
    if pat5:
        clean = _clean_single_name(pat5.group(1))
        if clean:
            return clean, pat5.group(2).strip().title()

    # 6. Markdown heading with name followed by designation
    pat6 = re.search(
        r"(?:^|\n)#{1,4}\s+(?:(?:Ar\.?|Architect)\s+)?([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\s*\n+\s*"
        rf"({TITLE_ALT})\b",
        text,
        re.I,
    )
    if pat6:
        clean = _clean_single_name(pat6.group(1))
        if clean:
            return clean, pat6.group(2).strip().title()

    # 7. Ar. Name or Architect Name
    pat7 = re.search(
        r"\b(?:Ar\.|Architect)\s+([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){1,3})\b",
        text,
    )
    if pat7:
        clean = _clean_single_name(pat7.group(1))
        if clean:
            return clean, "Principal Architect"

    return "Not found", "Not found"


def extract_city(text: str, query: str = "") -> str:
    """Detect city or metropolitan area from query or content."""
    query_lower = (query or "").lower()
    text_lower = (text or "").lower()

    # 1. If query explicitly specifies a target city, check if that city is in the query
    query_matched_city = None
    for k in sorted(_CITY_MAP.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(k) + r"\b"
        if re.search(pattern, query_lower):
            query_matched_city = _CITY_MAP[k]
            break

    # If query specified a city and text mentions it (or any of its aliases), prioritize it!
    if query_matched_city:
        for k, v in _CITY_MAP.items():
            if v == query_matched_city:
                if re.search(r"\b" + re.escape(k) + r"\b", text_lower):
                    return query_matched_city

    # 2. Count mentions of all cities in text to find the most prominent one
    city_counts: dict[str, int] = {}
    for k, v in _CITY_MAP.items():
        pattern = r"\b" + re.escape(k) + r"\b"
        matches = len(re.findall(pattern, text_lower))
        if matches > 0:
            city_counts[v] = city_counts.get(v, 0) + matches

    if city_counts:
        # Return city with highest frequency
        best_city = max(city_counts.items(), key=lambda item: item[1])[0]
        return best_city

    if query_matched_city:
        return query_matched_city

    return "Not stated"


def extract_emails(text: str) -> list[str]:
    """Extract and validate public emails from text."""
    matches = _EMAIL_REGEX.findall(text)
    cleaned = []
    for m in matches:
        m_lower = m.lower().strip()
        if re.search(r"\.(png|jpg|jpeg|gif|svg|webp|pdf|doc|css|js|ico)$", m_lower):
            continue
        domain = m_lower.split("@")[-1]
        if domain in _JUNK_EMAIL_DOMAINS:
            continue
        if m_lower not in cleaned:
            cleaned.append(m_lower)
    return cleaned


def extract_phones(text: str) -> list[str]:
    """Extract and validate phone/mobile numbers from text."""
    raw = _PHONE_REGEX.findall(text)
    phones = []
    for groups in raw:
        num = "".join(groups).strip()
        digits = re.sub(r"[^\d+]", "", num)
        if len(digits) >= 10:
            formatted = num.strip()
            if formatted not in phones:
                phones.append(formatted)
    return phones


def extract_socials(text: str) -> dict[str, str]:
    """Extract verified social media profiles from text or markdown links."""
    socials: dict[str, str] = {}
    urls = re.findall(r'https?://[^\s\)\]\"\'>]+', text)
    for u in urls:
        u_clean = u.rstrip(".,;:)\"'>")
        try:
            parsed = urllib.parse.urlparse(u_clean)
            domain = parsed.netloc.lower().lstrip("www.")
            for sd, field_name in _SOCIAL_PLATFORMS.items():
                if sd in domain and field_name not in socials:
                    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                    if not path_parts:
                        continue
                    first_segment = path_parts[0].lower()
                    if first_segment in _INVALID_SOCIAL_PATHS:
                        continue
                    # YouTube channels/profiles must be @handle, c/, channel/, or user/
                    if field_name == "youtube":
                        if not (first_segment.startswith("@") or first_segment in ("c", "channel", "user")):
                            continue
                    # Twitter/X profile check
                    if field_name == "twitter":
                        if first_segment in ("intent", "share", "status", "search", "hashtag"):
                            continue
                    # LinkedIn profile check
                    if field_name == "linkedin":
                        if first_segment not in ("company", "school", "in"):
                            continue
                    # Instagram profile check
                    if field_name == "instagram":
                        if first_segment in ("p", "reel", "tv", "stories", "explore"):
                            continue
                    socials[field_name] = u_clean
        except Exception:
            continue
    return socials


def extract_services(text: str) -> list[str]:
    """Extract key architectural/design service areas."""
    services = []
    text_lower = text.lower()
    for label, pat in _SERVICE_PATTERNS:
        if re.search(pat, text_lower):
            services.append(label)
    if not services:
        services = ["Architecture & Design"]
    return services


def extract_clean_summary(description: str, markdown: str) -> str:
    """Generate a clean executive summary without raw code, HTML tags, or markdown clutter."""
    raw_text = description if (description and len(description.strip()) > 20 and not description.strip().startswith("[")) else ""
    if not raw_text and markdown:
        lines = [l.strip() for l in markdown.splitlines() if l.strip()]
        content_lines = []
        for l in lines:
            if l.startswith("#") or l.startswith("!") or l.startswith("|") or l.startswith("- ["):
                continue
            if len(l.split()) >= 6:
                clean_line = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', l)
                clean_line = re.sub(r'[*_`#]', '', clean_line)
                clean_line = re.sub(r'<[^>]+>', '', clean_line)
                clean_line = re.sub(r'\s+', ' ', clean_line).strip()
                content_lines.append(clean_line)
            if len(" ".join(content_lines)) > 160:
                break
        if content_lines:
            raw_text = " ".join(content_lines)

    if raw_text:
        # Strip markdown links, HTML tags, backticks, asterisks
        clean = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', raw_text)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = re.sub(r'[*_`#]', '', clean)
        clean = py_html.unescape(clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Clean leading date/rating artifacts e.g. "21 Oct 2023 · ", "Rating 5.0(4,379)"
        clean = re.sub(r'^(?:\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s*[·•-]\s*)+', '', clean)
        clean = re.sub(r'^Rating\s+[\d.]+(?:\([^)]*\))?\s*', '', clean)
        return clean[:300].strip()

    return "Architecture and interior design studio with verified public web profile."


def extract_structured_fields_from_hit(
    url: str,
    title: str,
    description: str,
    markdown: str = "",
    source: str = "firecrawl",
    query: str = "",
) -> dict:
    """
    Transform raw Firecrawl / local directory scrape results into structured
    business intelligence: organisation, owner_name, designation, city, contacts, services.
    """
    combined_text = f"{title}\n{description}\n{markdown}"

    organisation = extract_org_name_from_text(title, url, description=description)
    owner_name, designation = extract_owner_and_designation(combined_text)
    city = extract_city(combined_text, query)
    emails = extract_emails(combined_text)
    phones = extract_phones(combined_text)
    socials = extract_socials(combined_text)
    services = extract_services(combined_text)

    org_size = "Not stated"
    for pat in [
        r'\b(?:team|staff)\s+(?:of\s+)?(\d+)\+?\b',
        r'\b(\d+)\+?\s+(?:architects|designers|professionals|people|employees)\b',
    ]:
        m = re.search(pat, combined_text, re.I)
        if m:
            count = int(m.group(1))
            if count <= 10:
                org_size = "1-10 team members"
            elif count <= 50:
                org_size = "11-50 team members"
            elif count <= 200:
                org_size = "51-200 team members"
            else:
                org_size = "200+ team members"
            break

    clean_summary = extract_clean_summary(description, markdown)

    if source == "local_directory":
        verification_status = "Verified"
        confidence = "High"
    elif owner_name != "Not found" and (emails or phones):
        verification_status = "Verified Live Lead"
        confidence = "High"
    elif owner_name != "Not found" or (emails or phones):
        verification_status = "Extracted"
        confidence = "Medium"
    else:
        verification_status = "Needs review"
        confidence = "Standard"

    return {
        "organisation": organisation,
        "owner_name": owner_name,
        "designation": designation,
        "city": city,
        "emails": emails,
        "phones": phones,
        "socials": socials,
        "services": services,
        "org_size": org_size,
        "clean_summary": clean_summary,
        "verification_status": verification_status,
        "confidence": confidence,
    }


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
                "onlyMainContent": False,
                "waitFor": 3000,
            },
        )

        if not isinstance(data, dict):
            return {
                "ok": False,
                "url": url,
                "html": None,
                "markdown": None,
                "metadata": {},
                "error": f"Unexpected response type from Firecrawl: {type(data)}",
            }

        markdown = (data.get("markdown") or "").strip()
        html = (data.get("html") or "").strip()
        metadata = data.get("metadata") or {}
        final_url = metadata.get("sourceURL") or metadata.get("url") or url

        ok = bool(markdown or html)
        structured = extract_structured_fields_from_hit(
            url=final_url,
            title=metadata.get("title") or "",
            description=metadata.get("description") or "",
            markdown=markdown or html,
            source="firecrawl",
        )
        return {
            "ok": ok,
            "url": final_url,
            "html": html,
            "markdown": markdown,
            "metadata": metadata,
            "structured": structured,
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
    Search the web via Firecrawl and return list[SearchHit] with structured
    organisation, executive leadership (owner, designation), contact, and location intelligence.

    Raises Exception with detailed error messages on API failure so that the UI
    can inform the user immediately (e.g. 401 invalid key, 402 out of credits).
    """
    key = _resolve_api_key()
    if not key:
        raise ValueError(
            "Firecrawl API key not found. Please enter and apply your Firecrawl API key "
            "in the search panel or sidebar."
        )

    # Prepare search payload with a buffer so filtering social/aggregator domains still leaves requested count
    fetch_limit = min(limit + 6, 30)
    payload = {
        "query": query,
        "limit": fetch_limit,
        "country": country,
        "lang": "en",
    }
    if scrape_content:
        payload["scrapeOptions"] = {"formats": ["markdown"]}

    logger.info("[Firecrawl] search query='%s' limit=%d (fetch_limit=%d)", query, limit, fetch_limit)

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

        # ── Filter 1: excluded domain blocklist ─────────────────────────────
        try:
            parsed_u = urllib.parse.urlparse(url if url.startswith("http") else f"https://{url}")
            h_domain = parsed_u.netloc.lower().lstrip("www.")
            if any(ex in h_domain for ex in _EXCLUDED_DOMAINS):
                logger.info("[Firecrawl] Blocked aggregator domain: %s", url)
                continue
        except Exception:
            pass

        # ── Filter 2: listing/directory URL path pattern ──────────────────────
        try:
            if _LISTING_URL_PATH_RE.search(parsed_u.path):
                logger.info("[Firecrawl] Blocked listing URL path: %s", url)
                continue
        except Exception:
            pass

        # ── Filter 3: generic listing/review page title ───────────────────────
        _pre_title = (item.get("title") or "").strip()
        if _pre_title and any(p.search(_pre_title) for p in _GENERIC_TITLE_PATTERNS):
            logger.info("[Firecrawl] Blocked listing-style title: %r → %s", _pre_title, url)
            continue

        title = (item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        markdown = (item.get("markdown") or "").strip()

        # Extract structured intelligence from Firecrawl's scraped response
        structured = extract_structured_fields_from_hit(
            url=url,
            title=title,
            description=description,
            markdown=markdown,
            source="firecrawl",
            query=query,
        )

        hits.append(SearchHit(
            title=title,
            url=url,
            description=description,
            markdown=markdown,
            source="firecrawl",
            organisation=structured["organisation"],
            owner_name=structured["owner_name"],
            designation=structured["designation"],
            city=structured["city"],
            emails=structured["emails"],
            phones=structured["phones"],
            socials=structured["socials"],
            org_size=structured["org_size"],
            services=structured["services"],
            clean_summary=structured["clean_summary"],
            verification_status=structured["verification_status"],
            confidence=structured["confidence"],
        ))

        if len(hits) >= limit:
            break

    logger.info("[Firecrawl] search '%s' → %d structured hits", query, len(hits))
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
                        clean_org = notes.split(" - ")[0].strip() if " - " in notes else notes
                        title = clean_org or url.replace("https://", "").replace("http://", "").split("/")[0]
                        desc = f"Verified {category.title()} firm in {city_name}. {notes}"

                        structured = extract_structured_fields_from_hit(
                            url=url,
                            title=title,
                            description=desc,
                            markdown="",
                            source="local_directory",
                            query=query,
                        )
                        structured["organisation"] = clean_org or title
                        structured["city"] = city_name
                        structured["services"] = [category.title()]
                        structured["verification_status"] = "Verified"
                        structured["confidence"] = "High"

                        hit_obj = SearchHit(
                            title=title,
                            url=url,
                            description=desc,
                            markdown="",
                            source="local_directory",
                            organisation=structured["organisation"],
                            owner_name=structured["owner_name"],
                            designation=structured["designation"],
                            city=structured["city"],
                            emails=structured["emails"],
                            phones=structured["phones"],
                            socials=structured["socials"],
                            org_size=structured["org_size"],
                            services=structured["services"],
                            clean_summary=structured["clean_summary"],
                            verification_status=structured["verification_status"],
                            confidence=structured["confidence"],
                        )
                        matches.append((score, hit_obj))
        except Exception as exc:
            logger.debug("Error reading %s: %s", csv_file, exc)

    # Sort by relevance score descending
    matches.sort(key=lambda x: x[0], reverse=True)
    return [hit for _, hit in matches[:limit]]
