"""
tests/test_leads.py — Unit tests for the CEO Leads data model, migrations, and exports.
"""

import pathlib
import pytest
from database import db
from services.company_service import get_leads, export_leads_csv, export_leads_excel


@pytest.fixture
def tmp_leads_db(tmp_path):
    """Provide an isolated temporary database for leads testing."""
    db_path = tmp_path / "test_leads.db"
    db.init_db(db_path)
    return db_path


class TestLeadsMigration:
    def test_migration_creates_new_columns(self, tmp_leads_db):
        """Verify that migrate_db creates owner_name, designation, org_size, org_size_basis, city columns."""
        with db.get_connection(tmp_leads_db) as conn:
            cur = conn.execute("PRAGMA table_info(companies)")
            cols = {row[1] for row in cur.fetchall()}

        for expected in ("owner_name", "designation", "org_size", "org_size_basis", "city"):
            assert expected in cols, f"Column {expected} must exist in companies table."

    def test_migration_is_idempotent(self, tmp_leads_db):
        with db.get_connection(tmp_leads_db) as conn:
            db.migrate_db(conn)
            db.migrate_db(conn)


class TestLeadsRetrieval:
    def _seed_sample_lead(self, conn, db_path):
        cid = db.upsert_company(conn, "hcp.co.in", "https://www.hcp.co.in", "architecture", "2024-01-01")
        db.upsert_evidence(conn, cid, "org_name", "HCP Design", "https://www.hcp.co.in", "Title", "html_meta", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "owner_name", "Dr. Bimal Patel", "https://www.hcp.co.in/about", "Founder", "html_content", "2024-01-01", verification_status="Needs review")
        db.upsert_evidence(conn, cid, "designation", "President and Managing Director", "https://www.hcp.co.in/about", "MD", "html_content", "2024-01-01", verification_status="Needs review")
        db.upsert_evidence(conn, cid, "org_size", "51-200", "https://www.hcp.co.in/about", "Over 100", "html_content", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "org_size_basis", "stated", "https://www.hcp.co.in/about", "Over 100", "html_content", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "phone", "+91 79 2755 0875", "https://www.hcp.co.in/contact", "Phone", "html_content", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "email", "hcpahd@hcp.co.in", "https://www.hcp.co.in/contact", "Email", "html_content", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "city", "Ahmedabad", "https://www.hcp.co.in/contact", "Ahmedabad, Gujarat", "html_content", "2024-01-01", verification_status="Extracted")
        db.upsert_evidence(conn, cid, "linkedin", "https://www.linkedin.com/company/hcp-design", "https://www.hcp.co.in", "Social", "html_content", "2024-01-01", verification_status="Extracted")
        conn.commit()
        return cid

    def test_get_leads_exact_fields_present(self, tmp_leads_db):
        with db.get_connection(tmp_leads_db) as conn:
            self._seed_sample_lead(conn, tmp_leads_db)

        leads = get_leads(tmp_leads_db)
        assert len(leads) == 1
        lead = leads[0]

        # Exact required fields
        expected_fields = [
            "owner_name", "organisation", "designation", "org_size",
            "mobile", "email", "city", "source_urls", "social_links"
        ]
        for f in expected_fields:
            assert f in lead, f"Field '{f}' must be present in lead dictionary."

        assert lead["owner_name"] == "Dr. Bimal Patel"
        assert lead["organisation"] == "HCP Design"
        assert lead["designation"] == "President and Managing Director"
        assert lead["org_size"] == "51-200"
        assert "+91 79 2755 0875" in lead["mobile"]
        assert "hcpahd@hcp.co.in" in lead["email"]
        assert lead["city"] == "Ahmedabad"
        assert "https://www.hcp.co.in" in lead["source_urls"]
        assert "linkedin" in lead["social_links"]

    def test_get_leads_not_found_handling(self, tmp_leads_db):
        """When fields are absent, returns 'Not found' and never guesses."""
        with db.get_connection(tmp_leads_db) as conn:
            db.upsert_company(conn, "empty.com", "https://empty.com", "architecture", "2024-01-01")
            conn.commit()

        leads = get_leads(tmp_leads_db)
        assert len(leads) == 1
        lead = leads[0]
        assert lead["owner_name"] == "Not found"
        assert lead["designation"] == "Not found"
        assert lead["org_size"] == "Not found"
        assert lead["mobile"] == "Not found"
        assert lead["email"] == "Not found"
        assert lead["city"] == "Not found"

    def test_export_leads_csv(self, tmp_leads_db):
        with db.get_connection(tmp_leads_db) as conn:
            self._seed_sample_lead(conn, tmp_leads_db)

        leads = get_leads(tmp_leads_db)
        csv_str = export_leads_csv(leads)
        assert "owner_name,organisation,designation,org_size,mobile,email,city,source_urls,social_links" in csv_str
        assert "Dr. Bimal Patel" in csv_str
        assert "Ahmedabad" in csv_str

    def test_export_leads_excel(self, tmp_leads_db):
        with db.get_connection(tmp_leads_db) as conn:
            self._seed_sample_lead(conn, tmp_leads_db)

        leads = get_leads(tmp_leads_db)
        excel_bytes = export_leads_excel(leads)
        assert len(excel_bytes) > 100
        # Check ZIP / XLSX signature (PK..)
        assert excel_bytes.startswith(b"PK")
