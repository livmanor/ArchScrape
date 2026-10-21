"""
scraper/places_client.py — Google Places API (New) text-search client.

Used as step 1 of the company lookup pipeline.

Public API
----------
places_text_search(name: str) -> PlacesResult | None
    Searches Google Places for the given name.
    Returns None if the API key is missing, or if no result's name matches
    every word of the searched name (whole-word, case-insensitive).
    That "not found" semantics are enforced here so callers don't have to
    repeat the guard logic.

Configuration
-------------
GOOGLE_PLACES_API_KEY environment variable (required).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Fields we request from the Places API (New) field mask.
# addressComponents -> city; nationalPhoneNumber -> mobile; websiteUri -> website.
_FIELD_MASK = (
    "places.displayName,"
    "places.formattedAddress,"
    "places.addressComponents,"
    "places.nationalPhoneNumber,"
    "places.internationalPhoneNumber,"
    "places.websiteUri"
)


@dataclass
class PlacesResult:
    """Structured result from a Places API text search."""
    # Each field is a dict: {value: str | None, source: str | None}
    organisation_name: dict = field(default_factory=lambda: {"value": "not found", "source": None})
    city: dict = field(default_factory=lambda: {"value": "not found", "source": None})
    mobile: dict = field(default_factory=lambda: {"value": "not found", "source": None})
    website: dict = field(default_factory=lambda: {"value": "not found", "source": None})
    # Raw place data for downstream consumers
    raw_place: dict = field(default_factory=dict)


def _resolve_api_key() -> Optional[str]:
    """Return the Google Places API key from the environment."""
    key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    return key or None


def _all_words_match(searched_name: str, result_name: str) -> bool:
    """
    Return True only if every word (>=2 chars) in searched_name appears as a
    whole word (case-insensitive) inside result_name.

    Examples:
        _all_words_match("design cafe", "Design Cafe") -> True
        _all_words_match("anu tiles", "Anu Tiles & Sanitary") -> True
        _all_words_match("anu tiles", "Anugrah Tile Store") -> False
          (because "tiles" is absent as a whole word)
    """
    words = [w for w in searched_name.lower().split() if len(w) >= 2]
    result_lower = result_name.lower()
    for word in words:
        # whole-word boundary check
        if not re.search(r"\b" + re.escape(word) + r"\b", result_lower):
            return False
    return True


def _extract_city(address_components: list) -> Optional[str]:
    """
    Pull the city (locality) from addressComponents array.
    Falls back to administrative_area_level_2, then administrative_area_level_1.
    Never returns a value derived from the user query.
    """
    priority = [
        "locality",
        "administrative_area_level_2",
        "sublocality_level_1",
        "administrative_area_level_1",
    ]
    buckets: dict = {}
    for component in address_components:
        short = (component.get("shortText") or "").strip()
        long_text = (component.get("longText") or "").strip()
        for t in component.get("types", []):
            if t in priority and t not in buckets:
                buckets[t] = long_text or short

    for p in priority:
        if p in buckets:
            return buckets[p]
    return None


def places_text_search(name: str) -> Optional[PlacesResult]:
    """
    Search Google Places (New) for *name* and return a PlacesResult.

    Returns None in these cases:
    - No API key configured.
    - HTTP error from Places API.
    - No place returned whose displayName matches every word of *name*.

    The source attached to each field is always "google_places" when found.
    """
    key = _resolve_api_key()
    if not key:
        logger.warning("[Places] GOOGLE_PLACES_API_KEY not set; skipping Places lookup.")
        return None

    payload = {
        "textQuery": name,
        "languageCode": "en",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": _FIELD_MASK,
    }

    try:
        resp = requests.post(_PLACES_SEARCH_URL, json=payload, headers=headers, timeout=10)
    except requests.exceptions.Timeout:
        logger.warning("[Places] Request timed out for '%s'.", name)
        return None
    except Exception as exc:
        logger.warning("[Places] Request failed for '%s': %s", name, exc)
        return None

    if resp.status_code == 401:
        logger.error("[Places] API key invalid (HTTP 401).")
        return None
    if resp.status_code == 403:
        logger.error("[Places] API key lacks Places API access (HTTP 403).")
        return None
    if resp.status_code != 200:
        logger.warning("[Places] HTTP %d for '%s': %s", resp.status_code, name, resp.text[:300])
        return None

    try:
        data = resp.json()
    except Exception:
        logger.warning("[Places] Could not parse JSON response for '%s'.", name)
        return None

    places = data.get("places") or []
    if not places:
        logger.info("[Places] No results for '%s'.", name)
        return None

    # Check every returned place for name match; use the first matching one.
    matching_place = None
    for place in places:
        display_name_obj = place.get("displayName") or {}
        display_name = (display_name_obj.get("text") or "").strip()
        if display_name and _all_words_match(name, display_name):
            matching_place = place
            logger.info("[Places] Name match: searched='%s' place='%s'.", name, display_name)
            break
        else:
            logger.info(
                "[Places] Name mismatch: searched='%s' place='%s'. Skipping.",
                name, display_name,
            )

    if matching_place is None:
        logger.info("[Places] No name-matching place found for '%s'.", name)
        return None

    # Extract fields from the matching place
    result = PlacesResult(raw_place=matching_place)

    # organisation_name
    display_name_obj = matching_place.get("displayName") or {}
    org_name = (display_name_obj.get("text") or "").strip()
    if org_name:
        result.organisation_name = {"value": org_name, "source": "google_places"}

    # city (from addressComponents, never from query)
    addr_components = matching_place.get("addressComponents") or []
    city = _extract_city(addr_components)
    if city:
        result.city = {"value": city, "source": "google_places"}

    # mobile (nationalPhoneNumber preferred; fallback to international)
    national = (matching_place.get("nationalPhoneNumber") or "").strip()
    intl = (matching_place.get("internationalPhoneNumber") or "").strip()
    phone = national or intl
    if phone:
        result.mobile = {"value": phone, "source": "google_places"}

    # website (websiteUri)
    website = (matching_place.get("websiteUri") or "").strip()
    if website:
        result.website = {"value": website, "source": "google_places"}

    return result
