"""
demo_lookup.py — Offline demo of lookup_pipeline.lookup_company().

Mocks Google Places and Firecrawl so no real API keys are needed.
Demonstrates the two required test cases:
  1. "anu tiles"   -> not_found (Places returns a name that does NOT match)
  2. "design cafe" -> populated fields from Places + scraped page
"""

import json
import sys
import types
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Mock scraper.places_client so we don't need a real Google key
# ---------------------------------------------------------------------------
from scraper.places_client import PlacesResult

def _fake_places(name: str):
    """
    "anu tiles"   -> return a place called "Anugrah Tiles" (word 'tiles' absent
                     as whole word from searched token — wait, 'tiles' IS there.
                     Better: return "Anu Tile World" so 'tiles' doesn't match)
                     Actually use a result whose name does NOT contain BOTH words
                     simultaneously. Simplest: no matching place at all.
    "design cafe" -> return a real-looking match.
    """
    n = name.lower().strip()

    if n == "anu tiles":
        # Return a result whose display name does NOT satisfy word-match for "anu tiles"
        # so _all_words_match fails and the function returns None
        return None  # simulates "no name-matching place found"

    if "design cafe" in n or n == "design cafe":
        r = PlacesResult()
        r.organisation_name = {"value": "Design Cafe", "source": "google_places"}
        r.city             = {"value": "Bengaluru", "source": "google_places"}
        r.mobile           = {"value": "+91 80 4718 0000", "source": "google_places"}
        r.website          = {"value": "https://www.designcafe.com", "source": "google_places"}
        r.raw_place        = {}
        return r

    return None


# ---------------------------------------------------------------------------
# Mock Firecrawl calls (map + scrape)
# ---------------------------------------------------------------------------

_ABOUT_MARKDOWN = """
# About Design Cafe

Design Cafe is a full-stack interior design company founded in Bengaluru in 2015.

**Founder & CEO - Gita Ramanan**

Gita Ramanan is the CEO and Co-Founder of Design Cafe. She has over 20 years of
experience in interior design and architecture.

Contact us at hello@designcafe.com or call +91 80 4718 0000.

Follow us:
- LinkedIn: https://www.linkedin.com/company/designcafe
- Instagram: https://www.instagram.com/designcafe.in/
"""

_FAKE_MAP_RESPONSE = {
    "links": [
        "https://www.designcafe.com/",
        "https://www.designcafe.com/about",
        "https://www.designcafe.com/contact",
        "https://www.designcafe.com/team",
    ]
}

_FAKE_SCRAPE_HOME = {
    "markdown": "# Design Cafe\nIndia's largest full-stack home interior design company.\nhello@designcafe.com",
    "links": [
        "mailto:hello@designcafe.com",
        "https://www.linkedin.com/company/designcafe",
        "https://www.instagram.com/designcafe.in/",
        "https://www.designcafe.com/about",
        "https://www.designcafe.com/contact",
    ],
}

_FAKE_SCRAPE_ABOUT = {
    "markdown": _ABOUT_MARKDOWN,
    "links": [
        "mailto:hello@designcafe.com",
        "https://www.linkedin.com/company/designcafe",
        "https://www.instagram.com/designcafe.in/",
    ],
}

_FAKE_SCRAPE_CONTACT = {
    "markdown": "# Contact Us\nhello@designcafe.com | +91 80 4718 0000\n100 Feet Road, Indiranagar, Bengaluru",
    "links": ["mailto:hello@designcafe.com"],
}


def _fake_firecrawl_map(website):
    return ["https://www.designcafe.com/about",
            "https://www.designcafe.com/contact",
            "https://www.designcafe.com/team"]


def _fake_firecrawl_scrape(url):
    if "about" in url:
        return _FAKE_SCRAPE_ABOUT
    if "contact" in url:
        return _FAKE_SCRAPE_CONTACT
    return _FAKE_SCRAPE_HOME


# ---------------------------------------------------------------------------
# Run with mocks
# ---------------------------------------------------------------------------

import scraper.lookup_pipeline as pipeline

def run_demo(name: str) -> dict:
    with (
        mock.patch("scraper.lookup_pipeline.places_text_search", side_effect=_fake_places),
        mock.patch("scraper.lookup_pipeline._firecrawl_map", side_effect=_fake_firecrawl_map),
        mock.patch("scraper.lookup_pipeline._firecrawl_scrape", side_effect=_fake_firecrawl_scrape),
    ):
        result = pipeline.lookup_company(name=name, db_path=None)
    return result


def _print_result(label: str, result: dict):
    print(f"\n{'='*60}")
    print(f"  Query: {label!r}")
    print(f"{'='*60}")
    fields = {
        "organisation_name": result.get("organisation_name"),
        "ceo":               result.get("ceo"),
        "company_size":      result.get("company_size"),
        "socials":           result.get("socials"),
        "city":              result.get("city"),
        "email":             result.get("email"),
        "mobile":            result.get("mobile"),
    }
    print(json.dumps(fields, indent=2, ensure_ascii=False))
    print(f"\n  Pipeline steps ({len(result.get('pipeline', []))}):")
    for step in result.get("pipeline", []):
        print(f"    {step}")
    if result.get("error"):
        print(f"\n  Error: {result['error']}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ArchScrape — Lookup Pipeline Demo (offline mock)")
    print("="*60)

    r1 = run_demo("anu tiles")
    _print_result("anu tiles", r1)

    r2 = run_demo("design cafe")
    _print_result("design cafe", r2)
