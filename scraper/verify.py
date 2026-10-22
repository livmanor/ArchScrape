"""
scraper/verify.py — Verbatim verification and executive role checking.

Enforces:
1. Normalises whitespace, punctuation, and case before checking strings against page text.
2. Checks people name and designation SEPARATELY against the page text.
   Drops any value that fails. Logs the dropped value and the reason.
3. Requires a role word for a person to count as a leader:
   (CEO, Chief Executive, Founder, Co-founder, Managing Director, Director, Principal, Partner).
4. Verifies services, locations, and company size against page text.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Required role words for a person to qualify as a leader
LEADER_ROLE_WORDS = [
    "ceo",
    "chief executive",
    "founder",
    "co-founder",
    "managing director",
    "director",
    "principal",
    "partner",
]

_LEADER_ROLE_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in LEADER_ROLE_WORDS) + r")\b",
    re.IGNORECASE,
)


def normalise_text(s: str) -> str:
    """
    Normalise whitespace, punctuation, and case.
    Replaces punctuation characters with spaces and collapses repeated whitespace.
    """
    if not s:
        return ""
    # Lowercase
    lowered = s.lower()
    # Replace punctuation and special characters with spaces
    no_punct = re.sub(r"[^\w\s]", " ", lowered)
    # Collapse whitespace
    return " ".join(no_punct.split())


def verify_in_text(value: str, page_text: str) -> bool:
    """
    Confirm that `value` appears in `page_text` post-normalisation.
    """
    if not value or not page_text:
        return False
    norm_val = normalise_text(value)
    if not norm_val:
        return False
    norm_page = normalise_text(page_text)
    return norm_val in norm_page


def is_leader_role(designation: str) -> bool:
    """
    Return True if designation contains one of the required leader role words:
    CEO, Chief Executive, Founder, Co-founder, Managing Director, Director, Principal, Partner.
    """
    if not designation:
        return False
    return bool(_LEADER_ROLE_RE.search(designation))


def verify_person(name: str, designation: str, page_text: str, source_url: str = "") -> Optional[dict[str, Any]]:
    """
    Check people name and designation SEPARATELY against page text.
    Drop any value that fails. Log the dropped value and the reason.

    Returns dict if both name and designation are verified, else None.
    """
    # 1. Verify Name
    if not verify_in_text(name, page_text):
        logger.info(
            "[Verification] Dropped person name '%s': not found verbatim in page text (%s)",
            name,
            source_url,
        )
        return None

    # 2. Verify Designation
    if not verify_in_text(designation, page_text):
        logger.info(
            "[Verification] Dropped designation '%s' for '%s': not found verbatim in page text (%s)",
            designation,
            name,
            source_url,
        )
        return None

    is_leader = is_leader_role(designation)

    return {
        "name": name.strip(),
        "designation": designation.strip(),
        "is_leader": is_leader,
        "source_url": source_url,
    }


def verify_llm_extraction(
    llm_data: dict[str, Any],
    page_text: str,
    source_url: str = "",
) -> dict[str, Any]:
    """
    Verifies all fields extracted by the LLM against the raw page text.
    Every non-verbatim value is dropped and logged.
    """
    verified: dict[str, Any] = {
        "people": [],
        "leaders": [],
        "services": [],
        "locations": [],
        "company_size": None,
        "founded": None,
        "dropped_items": [],
    }

    # 1. Verify People
    for p in llm_data.get("people", []):
        name = p.get("name", "")
        desig = p.get("designation", "")
        person_res = verify_person(name, desig, page_text, source_url)
        if person_res:
            verified["people"].append({
                "name": person_res["name"],
                "designation": person_res["designation"],
                "source": source_url,
            })
            if person_res["is_leader"]:
                verified["leaders"].append({
                    "name": person_res["name"],
                    "designation": person_res["designation"],
                    "source": source_url,
                })
        else:
            verified["dropped_items"].append({
                "field": "people",
                "value": f"{name} ({desig})",
                "reason": "Failed verbatim presence check in page text",
            })

    # 2. Verify Services
    for s in llm_data.get("services", []):
        if verify_in_text(s, page_text):
            verified["services"].append({"value": s, "source": source_url})
        else:
            logger.info("[Verification] Dropped service '%s': not found verbatim in page text", s)
            verified["dropped_items"].append({
                "field": "services",
                "value": s,
                "reason": "Not found verbatim in page text",
            })

    # 3. Verify Locations
    for loc in llm_data.get("locations", []):
        if verify_in_text(loc, page_text):
            verified["locations"].append({"value": loc, "source": source_url})
        else:
            logger.info("[Verification] Dropped location '%s': not found verbatim in page text", loc)
            verified["dropped_items"].append({
                "field": "locations",
                "value": loc,
                "reason": "Not found verbatim in page text",
            })

    # 4. Verify Company Size
    size = llm_data.get("company_size")
    if size and verify_in_text(str(size), page_text):
        verified["company_size"] = {"value": str(size), "source": source_url}
    elif size:
        logger.info("[Verification] Dropped company_size '%s': not found verbatim in page text", size)
        verified["dropped_items"].append({
            "field": "company_size",
            "value": str(size),
            "reason": "Not found verbatim in page text",
        })

    # 5. Verify Founded Year
    founded = llm_data.get("founded")
    if founded and verify_in_text(str(founded), page_text):
        verified["founded"] = {"value": str(founded), "source": source_url}
    elif founded:
        logger.info("[Verification] Dropped founded '%s': not found verbatim in page text", founded)
        verified["dropped_items"].append({
            "field": "founded",
            "value": str(founded),
            "reason": "Not found verbatim in page text",
        })

    return verified
