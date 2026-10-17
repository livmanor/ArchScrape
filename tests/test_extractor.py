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


# ─── Leads Feature Unit Tests (Task 1 & Task 5) ───────────────────────────────

FIXTURE_TEAM_SENIORITY = """
<html>
<body>
    <div class="team-grid">
        <div class="member-card">
            <h3>Ar. Bimal Patel</h3>
            <span class="role">Founder and Managing Director</span>
        </div>
        <div class="member-card">
            <h3>Rahul Sen</h3>
            <span class="role">Senior Architect</span>
        </div>
        <div class="member-card">
            <h3>Pooja Sharma</h3>
            <span class="role">Interior Designer</span>
        </div>
    </div>
</body>
</html>
"""

FIXTURE_STATED_ORG_SIZE = """
<html>
<body>
    <div class="about-hero">
        <p>Founded in 1996, our practice comprises a dedicated team of 25 architects and planners across India.</p>
    </div>
</body>
</html>
"""

FIXTURE_STATED_LARGE_ORG_SIZE = """
<html>
<body>
    <p>We are a firm of over 100 professionals delivering sustainable infrastructure.</p>
</body>
</html>
"""

FIXTURE_TEAM_LIST_ONLY = """
<html>
<body>
    <div class="team-list">
        <div class="team-profile"><h4>Aarav Mehta</h4><p>Partner</p></div>
        <div class="team-profile"><h4>Diya Patel</h4><p>Principal Architect</p></div>
        <div class="team-profile"><h4>Karan Joshi</h4><p>Project Lead</p></div>
        <div class="team-profile"><h4>Rhea Nair</h4><p>Associate Architect</p></div>
    </div>
</body>
</html>
"""

FIXTURE_NO_SIZE_OR_TEAM = """
<html>
<body>
    <h1>Minimal Studio</h1>
    <p>Creating contemporary architectural spaces.</p>
</body>
</html>
"""

FIXTURE_MAILTO_LINKS = """
<html>
<body>
    <footer>
        <a href="mailto:contact@designfirm.example?subject=Project%20Inquiry">Email Us</a>
        <a href="mailto:careers@designfirm.example">Careers</a>
    </footer>
</body>
</html>
"""


class TestOwnerSeniorityExtraction:
    def test_senior_founder_chosen_as_owner(self):
        """When multiple team members are listed, the most senior (Founder) is selected as owner_name."""
        candidates = extract(FIXTURE_TEAM_SENIORITY, "https://firm.example/team", page_role="team")
        owners = [c for c in candidates if c.field_name == "owner_name"]
        assert owners, "Should extract owner_name candidate"
        # Bimal Patel is Founder and MD, senior to Senior Architect Rahul Sen
        assert "Bimal Patel" in owners[0].value
        assert owners[0].verification_status == "Needs review"

    def test_senior_designation_matched(self):
        candidates = extract(FIXTURE_TEAM_SENIORITY, "https://firm.example/team", page_role="team")
        desigs = [c for c in candidates if c.field_name == "designation"]
        assert desigs
        assert any(d.value in ("Founder", "Managing Director") for d in desigs)
        assert all(d.verification_status == "Needs review" for d in desigs)


class TestOrgSizeExtraction:
    def test_stated_team_of_25_maps_to_bucket(self):
        """'team of 25 architects' should yield bucket '11-50' with basis 'stated'."""
        candidates = extract(FIXTURE_STATED_ORG_SIZE, "https://firm.example/about", page_role="about")
        sizes = [c for c in candidates if c.field_name == "org_size"]
        bases = [c for c in candidates if c.field_name == "org_size_basis"]
        assert sizes, "Should extract org_size"
        assert sizes[0].value == "11-50"
        assert bases[0].value == "stated"

    def test_stated_over_100_maps_to_bucket(self):
        """'over 100 professionals' should yield bucket '51-200' with basis 'stated'."""
        candidates = extract(FIXTURE_STATED_LARGE_ORG_SIZE, "https://firm.example/about", page_role="about")
        sizes = [c for c in candidates if c.field_name == "org_size"]
        bases = [c for c in candidates if c.field_name == "org_size_basis"]
        assert sizes[0].value == "51-200"
        assert bases[0].value == "stated"

    def test_team_members_count_fallback(self):
        """When no stated size exists, count of 4 team members yields '1-10' with basis 'team_count'."""
        candidates = extract(FIXTURE_TEAM_LIST_ONLY, "https://firm.example/team", page_role="team")
        sizes = [c for c in candidates if c.field_name == "org_size"]
        bases = [c for c in candidates if c.field_name == "org_size_basis"]
        assert sizes[0].value == "1-10"
        assert bases[0].value == "team_count"

    def test_org_size_not_found(self):
        """When neither stated size nor team list is present, returns 'Not found'."""
        candidates = extract(FIXTURE_NO_SIZE_OR_TEAM, "https://firm.example/about", page_role="about")
        sizes = [c for c in candidates if c.field_name == "org_size"]
        bases = [c for c in candidates if c.field_name == "org_size_basis"]
        assert sizes[0].value == "Not found"
        assert bases[0].value == "not_found"


class TestCityExtractionLeads:
    def test_city_fallback_inferred_from_market_filter(self):
        """When no city is present in HTML/JSON-LD, falls back to market_city labelled 'inferred' and 'Needs review'."""
        candidates = extract(
            FIXTURE_NO_SIZE_OR_TEAM,
            "https://firm.example/",
            page_role="homepage",
            market_city="Ahmedabad",
        )
        cities = [c for c in candidates if c.field_name == "city"]
        assert cities, "Should have inferred city candidate"
        assert cities[0].value == "Ahmedabad"
        assert cities[0].method == "inferred"
        assert cities[0].verification_status == "Needs review"

    def test_real_city_takes_precedence_over_market_city(self):
        """If city is found in page text (e.g. Pune), it takes precedence over market_city filter."""
        candidates = extract(
            FIXTURE_JSONLD_ORG,
            "https://firm.example/",
            page_role="homepage",
            market_city="Ahmedabad",
        )
        cities = [c for c in candidates if c.field_name == "city"]
        assert any("Pune" in (c.value or "") for c in cities)


class TestBusinessEmailExtraction:
    def test_extracts_mailto_with_query_params(self):
        """mailto: hrefs with subject query params must be cleanly parsed to extract the bare email."""
        candidates = extract(FIXTURE_MAILTO_LINKS, "https://firm.example/contact", page_role="contact")
        emails = [c.value for c in candidates if c.field_name == "email"]
        assert "contact@designfirm.example" in emails
        assert "careers@designfirm.example" in emails
        assert not any("?" in (e or "") for e in emails)

    def test_rejects_junk_email_extensions(self):
        html_junk = "<html><body><p>Contact icon.png@2x and logo.svg@somedomain</p></body></html>"
        candidates = extract(html_junk, "https://firm.example/contact", page_role="contact")
        emails = [c.value for c in candidates if c.field_name == "email"]
        assert not any(e.endswith(".png") or e.endswith(".svg") for e in emails)


class TestVendorAndNonPersonExclusion:
    def test_rejects_material_and_supplier_names(self):
        """'Marble Suppliers' or 'Tile Manufacturers' must never be accepted as owner names."""
        from scraper.extractor import _clean_name
        assert _clean_name("Marble Suppliers") is None
        assert _clean_name("Tile Manufacturers") is None
        assert _clean_name("Lighting Consultants") is None
        assert _clean_name("Granite Enterprises") is None
        assert _clean_name("Timber Works") is None
        # Real architect names must still be accepted
        assert _clean_name("Arpan Shah") == "Arpan Shah"
        assert _clean_name("Bimal Patel") == "Bimal Patel"
        assert _clean_name("Sonali Rastogi") == "Sonali Rastogi"

    def test_ignores_team_cards_in_vendor_sections(self):
        """Cards nested inside vendor or credit sections must not be extracted as team/owners."""
        html_credits = """
        <html>
        <body>
            <section class="project-credits vendors">
                <div class="team-member">
                    <h3>Marble Suppliers</h3>
                    <p class="role">Partner</p>
                </div>
            </section>
            <section class="leadership team">
                <div class="member">
                    <h3>Kavita Rao</h3>
                    <p class="role">Founder & Principal Architect</p>
                </div>
            </section>
        </body>
        </html>
        """
        candidates = extract(html_credits, "https://firm.example/about", page_role="about")
        owners = [c.value for c in candidates if c.field_name == "owner_name"]
        assert "Marble Suppliers" not in owners
        assert "Kavita Rao" in owners

