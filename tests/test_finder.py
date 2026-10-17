"""
tests/test_finder.py — Unit tests for company resolution and lead source attribution.
"""

import pathlib
import pytest
from scraper.finder import resolve_company_url
from services.company_service import find_and_extract_company_lead


class TestCompanyResolution:
    def test_direct_url_input(self):
        res = resolve_company_url("https://www.morphogenesis.org")
        assert res["found"] is True
        assert res["url"] == "https://www.morphogenesis.org"
        assert res["source"] == "direct_url"

    def test_direct_domain_input(self):
        res = resolve_company_url("studiolotus.in")
        assert res["found"] is True
        assert "studiolotus.in" in res["url"]
        assert res["source"] == "direct_domain"

    def test_known_registry_resolution(self):
        res = resolve_company_url("Modo Designs")
        assert res["found"] is True
        assert "mododesigns.co.in" in res["url"]
        assert res["source"] == "verified_registry"

    def test_empty_input(self):
        res = resolve_company_url("")
        assert res["found"] is False
        assert res["url"] is None


class TestLeadSourcesExtraction:
    def test_sources_present_in_extracted_lead(self, tmp_path):
        db_path = tmp_path / "test_leads.db"
        # Test with a known local seed
        res = find_and_extract_company_lead("Modo Designs", db_path=db_path)
        assert res["ok"] is True
        assert res["organisation"] != ""
        assert "source_urls_list" in res
        assert len(res["source_urls_list"]) > 0
        assert "field_sources" in res
        assert "email" in res["field_sources"] or "website" in res["field_sources"]
        # Verify source attribution structure
        for field, c_list in res["field_sources"].items():
            for c in c_list:
                assert "source_url" in c
                assert "value" in c
                assert "method" in c


class TestCitySeedDiscovery:
    def test_chennai_seed_companies_count(self):
        from scraper.finder import get_city_seed_companies
        firms = get_city_seed_companies("Chennai", limit=50)
        assert len(firms) == 50, f"Expected 50 Chennai firms, got {len(firms)}"
        assert all("url" in f for f in firms)
        assert any("ponniarchitects.com" in f["url"] for f in firms)
        assert any("shilpaarchitects.com" in f["url"] for f in firms)

    def test_ahmedabad_seed_companies_count(self):
        from scraper.finder import get_city_seed_companies
        firms = get_city_seed_companies("Ahmedabad", limit=10)
        assert len(firms) >= 5
        assert any("hcp.co.in" in f["url"] for f in firms)

    def test_delhi_seed_companies_count(self):
        from scraper.finder import get_city_seed_companies
        firms = get_city_seed_companies("Delhi", limit=50)
        assert len(firms) == 50, f"Expected 50 Delhi firms, got {len(firms)}"
        assert any("morphogenesis.org" in f["url"] for f in firms)
        assert any("studiolotus.in" in f["url"] for f in firms)

    def test_hyderabad_seed_companies_count(self):
        from scraper.finder import get_city_seed_companies
        firms = get_city_seed_companies("Hyderabad", limit=50)
        assert len(firms) == 50, f"Expected 50 Hyderabad firms, got {len(firms)}"
        assert any("fhdindia.com" in f["url"] for f in firms)
        assert any("genesisplanners.in" in f["url"] for f in firms)


class TestLeadUpdateVerification:
    def test_update_lead_fields_persists(self, tmp_path):
        from database import db
        test_db = tmp_path / "test_update.db"
        db.init_db(test_db)
        with db.get_connection(test_db) as conn:
            run_id = db.start_scrape_run(conn, "2026-01-01T00:00:00Z")
            cid = db.upsert_company(conn, "testfirm.in", "https://testfirm.in", "architecture", "2026-01-01T00:00:00Z", run_id)
            db.update_lead_fields(
                conn,
                company_id=cid,
                owner_name="Correct Architect",
                designation="Principal Architect",
                email="contact@testfirm.in",
                city="Chennai",
            )
            # Verify update
            row = conn.execute("SELECT owner_name, designation, city FROM companies WHERE id = ?", (cid,)).fetchone()
            assert row["owner_name"] == "Correct Architect"
            assert row["designation"] == "Principal Architect"
            assert row["city"] == "Chennai"
            # Verify evidence
            ev = conn.execute("SELECT extracted_value, verification_status FROM evidence WHERE company_id = ? AND field_name = 'owner_name'", (cid,)).fetchone()
            assert ev["extracted_value"] == "Correct Architect"
            assert ev["verification_status"] == "Verified"

