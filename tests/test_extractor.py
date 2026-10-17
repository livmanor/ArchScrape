"""
tests/test_extractor.py — Unit tests for the HTML/JSON-LD extraction pipeline.

Uses synthetic HTML fixtures only. No real company data is embedded.
All fixtures are clearly labelled as test data.
"""

import json
import pytest
from scraper.extractor import (
    Candidate,
    classify_page_role,
    extract,
)

# ─── Synthetic HTML fixtures ───────────────────────────────────────────────────
# These are artificial test documents, NOT real company records.

FIXTURE_JSONLD_ORG = """
<html>
<head>
    <title>Test Architecture Studio &#8212; Fictional</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Test Architecture Studio",
        "telephone": "+91-9999900000",
        "email": "info@test-arch-studio.example",
        "url": "https://test-arch-studio.example",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Pune",
            "addressRegion": "Maharashtra"
        },
        "sameAs": [
            "https://www.linkedin.com/company/test-arch-studio"
        ]
    }
    </script>
</head>
<body><h1>Test Architecture Studio</h1></body>
</html>
"""

FIXTURE_JSONLD_PERSON = """
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Jane Test Architect",
        "jobTitle": "Principal Architect"
    }
    </script>
</head>
<body></body>
</html>
"""

FIXTURE_CONTACT_PAGE = """
<html>
<head><title>Contact — Test Studio</title></head>
<body>
    <p>Reach us at info@test-studio.example or call +91 88888 77777</p>
    <p>Office: Mumbai, Maharashtra</p>
</body>
</html>
"""

FIXTURE_OG_META = """
<html>
<head>
    <meta property="og:site_name" content="Test Interior Studio" />
    <meta name="description" content="Premium interior design in Bengaluru." />
</head>
<body><h1>Test Interior Studio — Fictional</h1></body>
</html>
"""

FIXTURE_SOCIAL_LINKS = """
<html>
<body>
    <a href="https://www.linkedin.com/company/test-firm">LinkedIn</a>
    <a href="https://www.instagram.com/testfirm">Instagram</a>
    <a href="https://www.facebook.com/testfirm">Facebook</a>
</body>
</html>
"""

FIXTURE_MALFORMED_HTML = "<html><head><script type='application/ld+json'>{BROKEN JSON</script></head><body></body></html>"

SOURCE = "https://test-arch-studio.example/"


class TestJSONLDExtraction:
    def test_extracts_org_name(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        org_names = [c for c in candidates if c.field_name == "org_name"]
        assert any("Test Architecture Studio" in (c.value or "") for c in org_names)

    def test_extracts_phone(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        phones = [c for c in candidates if c.field_name == "phone"]
        assert phones, "Should extract at least one phone candidate"

    def test_extracts_email(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        emails = [c for c in candidates if c.field_name == "email"]
        assert any("test-arch-studio.example" in (c.value or "") for c in emails)

    def test_extracts_city_from_address(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        cities = [c for c in candidates if c.field_name == "city"]
        assert any("Pune" in (c.value or "") for c in cities)

    def test_extracts_linkedin_from_sameas(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        linkedin = [c for c in candidates if c.field_name == "linkedin"]
        assert linkedin, "Should extract LinkedIn from sameAs"

    def test_jsonld_method_tagged(self):
        candidates = extract(FIXTURE_JSONLD_ORG, SOURCE)
        jsonld_cands = [c for c in candidates if c.method == "json_ld"]
        assert jsonld_cands, "JSON-LD candidates should be tagged with method='json_ld'"


class TestPersonJSONLD:
    def test_person_marked_needs_review(self):
        """Owner/founder data from JSON-LD must be flagged as Needs review."""
        candidates = extract(FIXTURE_JSONLD_PERSON, SOURCE)
        person_cands = [c for c in candidates if c.field_name == "owner_name"]
        assert all(c.verification_status == "Needs review" for c in person_cands), (
            "Person/owner candidates must be marked 'Needs review' — not auto-verified."
        )

    def test_designation_needs_review(self):
        candidates = extract(FIXTURE_JSONLD_PERSON, SOURCE)
        desig = [c for c in candidates if c.field_name == "designation"]
        assert all(c.verification_status == "Needs review" for c in desig)


class TestContactPageExtraction:
    def test_extracts_email_from_contact(self):
        candidates = extract(FIXTURE_CONTACT_PAGE, "https://test-studio.example/contact", "contact")
        emails = [c for c in candidates if c.field_name == "email"]
        assert any("test-studio.example" in (c.value or "") for c in emails)

    def test_extracts_phone_from_contact(self):
        candidates = extract(FIXTURE_CONTACT_PAGE, "https://test-studio.example/contact", "contact")
        phones = [c for c in candidates if c.field_name == "phone"]
        assert phones, "Should find a phone number on contact page"

    def test_extracts_mumbai_city(self):
        candidates = extract(FIXTURE_CONTACT_PAGE, "https://test-studio.example/contact", "contact")
        cities = [c for c in candidates if c.field_name == "city"]
        assert any("Mumbai" in (c.value or "") for c in cities)


class TestMetaExtraction:
    def test_og_sitename(self):
        candidates = extract(FIXTURE_OG_META, SOURCE)
        org = [c for c in candidates if c.field_name == "org_name" and c.method == "html_meta"]
        assert any("Test Interior Studio" in (c.value or "") for c in org)

    def test_description(self):
        candidates = extract(FIXTURE_OG_META, SOURCE)
        desc = [c for c in candidates if c.field_name == "description"]
        assert desc


class TestSocialLinks:
    def test_linkedin_extracted(self):
        candidates = extract(FIXTURE_SOCIAL_LINKS, SOURCE)
        li = [c for c in candidates if c.field_name == "linkedin"]
        assert li

    def test_instagram_extracted(self):
        candidates = extract(FIXTURE_SOCIAL_LINKS, SOURCE)
        ig = [c for c in candidates if c.field_name == "instagram"]
        assert ig

    def test_facebook_extracted(self):
        candidates = extract(FIXTURE_SOCIAL_LINKS, SOURCE)
        fb = [c for c in candidates if c.field_name == "facebook"]
        assert fb


class TestWebsiteField:
    def test_website_always_present(self):
        """The website field should always be extracted from the source URL."""
        candidates = extract(FIXTURE_CONTACT_PAGE, SOURCE)
        websites = [c for c in candidates if c.field_name == "website"]
        assert websites

    def test_website_is_base_url(self):
        candidates = extract(FIXTURE_CONTACT_PAGE, SOURCE)
        websites = [c for c in candidates if c.field_name == "website"]
        assert any(c.value == "https://test-arch-studio.example" for c in websites)


class TestMalformedHTML:
    def test_malformed_jsonld_handled(self):
        """Malformed JSON-LD must not raise an exception."""
        candidates = extract(FIXTURE_MALFORMED_HTML, SOURCE)
        # Should return candidates without crashing (meta/content still extractable)
        assert isinstance(candidates, list)


class TestClassifyPageRole:
    def test_contact(self):
        assert classify_page_role("https://example.com/contact") == "contact"

    def test_about(self):
        assert classify_page_role("https://example.com/about-us") == "about"

    def test_team(self):
        assert classify_page_role("https://example.com/our-team") == "team"

    def test_homepage(self):
        assert classify_page_role("https://example.com/") == "homepage"

    def test_leadership(self):
        assert classify_page_role("https://example.com/leadership") == "team"
