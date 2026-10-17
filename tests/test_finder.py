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
