"""
tests/test_firecrawl.py — Unit tests for firecrawl_client.py and directory fallback.
"""

from scraper.firecrawl_client import (
    SearchHit,
    is_available,
    search_local_directory,
    test_firecrawl_connection as check_firecrawl_conn,
)


def test_invalid_key_connection():
    """Testing an invalid key should return (False, description)."""
    ok, msg = check_firecrawl_conn("invalid_test_key_xyz")
    assert ok is False
    assert "Invalid API key" in msg or "HTTP 401" in msg


def test_search_local_directory():
    """Curated directory search should find relevant matches in local CSV files."""
    hits = search_local_directory("delhi architecture", limit=5)
    assert len(hits) > 0
    assert all(isinstance(h, SearchHit) for h in hits)
    assert any("delhi" in h.description.lower() or "delhi" in h.title.lower() for h in hits)


def test_search_local_directory_bengaluru():
    hits = search_local_directory("bengaluru design studios", limit=5)
    assert len(hits) > 0
    assert any("bengaluru" in h.description.lower() or "bengaluru" in h.title.lower() for h in hits)
    # Check that structured fields are populated on local directory hits
    first = hits[0]
    assert first.organisation != ""
    assert first.city == "Bengaluru"
    assert first.verification_status == "Verified"


def test_extract_structured_fields_leadership_and_contacts():
    from scraper.firecrawl_client import extract_structured_fields_from_hit

    url = "https://www.morphogenesis.org"
    title = "Morphogenesis | Leading Architecture Firm India"
    description = "Morphogenesis is an architecture practice based in New Delhi."
    markdown = """
    # Morphogenesis Architecture & Urban Design
    Founded in 1996 by Sonali Rastogi and Manit Rastogi, Morphogenesis is a global design practice.
    Our team of 85 architects delivers sustainable masterplanning and residential architecture.
    Contact us at studio@morphogenesis.org or reach our Delhi office at +91 11 41828070.
    Visit our [LinkedIn](https://www.linkedin.com/company/morphogenesis) and [Instagram](https://instagram.com/morphogenesis.official).
    """
    res = extract_structured_fields_from_hit(url, title, description, markdown)

    assert res["organisation"] == "Morphogenesis"
    assert "Sonali Rastogi" in res["owner_name"]
    assert "Manit Rastogi" in res["owner_name"]
    assert "Principal Architect" in res["designation"] or "Founder" in res["designation"]
    assert res["city"] == "Delhi NCR"
    assert "studio@morphogenesis.org" in res["emails"]
    assert any("41828070" in p for p in res["phones"])
    assert "linkedin" in res["socials"]
    assert "51-200" in res["org_size"]
    assert "Architecture" in res["services"]
    assert res["verification_status"] == "Verified Live Lead"


def test_save_structured_lead_to_db(tmp_path):
    from services.company_service import save_structured_lead_to_db, get_leads

    db_file = tmp_path / "test_leads.db"
    lead_info = {
        "url": "https://www.studiolotus.in",
        "organisation": "Studio Lotus",
        "owner_name": "Ambrish Arora & Sidhartha Talwar",
        "designation": "Founding Partners & Principal Architects",
        "city": "Delhi NCR",
        "emails": ["info@studiolotus.in"],
        "phones": ["+91 11 40570808"],
        "socials": {"instagram": "https://instagram.com/studiolotus"},
        "org_size": "51-200 team members",
        "services": ["Architecture", "Interior Design"],
        "clean_summary": "Studio Lotus is a multidisciplinary design practice in Delhi NCR.",
    }

    res = save_structured_lead_to_db(lead_info, db_path=db_file)
    assert res["ok"] is True
    assert res["organisation"] == "Studio Lotus"

    saved = get_leads(db_path=db_file)
    assert len(saved) == 1
    assert saved[0]["organisation"] == "Studio Lotus"
    assert "Ambrish Arora" in saved[0]["owner_name"]
    assert saved[0]["city"] == "Delhi NCR"
    assert saved[0]["email"] == "info@studiolotus.in"

