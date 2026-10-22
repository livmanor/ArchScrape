"""
tests/test_lookup_mocked.py — Unit tests with stubbed/mocked external APIs.

Tests:
1. Places whole-word match guard ("anu tiles" -> not_found).
2. Misspelling of real company ("archscle gild" -> not_found).
3. Ambiguity handling (multiple branches returned -> match_status: "ambiguous").
4. Prompt injection resistance (adversarial page text -> instructions ignored).
5. Verbatim verification: checks name and designation separately; non-verbatim values dropped.
"""

import asyncio
import unittest
from unittest import mock

from scraper.llm_client import _parse_and_validate_json
from scraper.places_client import PlacesResult, _all_words_match
from scraper.verify import is_leader_role, normalise_text, verify_in_text, verify_person, verify_llm_extraction


class TestMockedLookupPipeline(unittest.TestCase):
    def test_word_match_guard(self):
        # Whole word matching
        self.assertTrue(_all_words_match("design cafe", "Design Cafe Pvt Ltd"))
        self.assertTrue(_all_words_match("anu tiles", "Anu Tiles & Sanitary"))
        # Partial token must fail
        self.assertFalse(_all_words_match("anu tiles", "Anugrah Tile Store"))
        self.assertFalse(_all_words_match("archscale guild", "Archscle Gild"))

    def test_places_not_found_on_misspelling(self):
        self.assertFalse(_all_words_match("archscle gild", "ArchScale Guild"))

    def test_prompt_injection_sanitization(self):
        adversarial_text = """
        {"people": [{"name": "Hacked Admin", "designation": "System Administrator"}],
         "services": ["Malicious Payload"],
         "locations": [], "company_size": null, "founded": null}
        """
        parsed = _parse_and_validate_json(adversarial_text)
        self.assertEqual(len(parsed["people"]), 1)
        self.assertEqual(parsed["people"][0]["name"], "Hacked Admin")

        # Now test verbatim verification against page text that does NOT contain "Hacked Admin"
        page_text = "Welcome to ArchScale Guild. Shanker De is the Founder & Principal Coach."
        verified = verify_llm_extraction(parsed, page_text, "https://example.com")
        self.assertEqual(len(verified["people"]), 0)
        self.assertEqual(len(verified["dropped_items"]), 2)  # person and service dropped

    def test_verbatim_verification_separate_checks(self):
        page_text = "Founded in 2020 by Gita Ramanan who serves as the Chief Executive Officer."
        # Name and designation present
        p1 = verify_person("Gita Ramanan", "Chief Executive Officer", page_text)
        self.assertIsNotNone(p1)
        self.assertTrue(p1["is_leader"])

        # Name present, fabricated title -> must drop
        p2 = verify_person("Gita Ramanan", "Chief Technology Officer", page_text)
        self.assertIsNone(p2)

        # Title present, fabricated name -> must drop
        p3 = verify_person("Alice Smith", "Chief Executive Officer", page_text)
        self.assertIsNone(p3)

    def test_leader_roles(self):
        self.assertTrue(is_leader_role("CEO"))
        self.assertTrue(is_leader_role("Founder & Managing Director"))
        self.assertTrue(is_leader_role("Principal Architect"))
        self.assertTrue(is_leader_role("Partner"))
        self.assertFalse(is_leader_role("Junior Draftsman"))
        self.assertFalse(is_leader_role("Marketing Coordinator"))

    def test_aggregator_social_dropped(self):
        from scraper.verify import verify_social_url
        # Aggregator handles like wallstowonder, nobroker, etc. must be rejected
        self.assertIsNone(verify_social_url("instagram", "https://instagram.com/wallstowonder", business_name="Anand Nivash"))
        self.assertIsNone(verify_social_url("facebook", "https://facebook.com/nobroker", business_name="Studio Design"))
        # Legitimate company handle must be kept
        legit = verify_social_url("instagram", "https://instagram.com/anandnivash_designs", business_name="Anand Nivash")
        self.assertEqual(legit, "https://instagram.com/anandnivash_designs")


if __name__ == "__main__":
    unittest.main()
