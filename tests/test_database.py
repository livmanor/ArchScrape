"""
tests/test_database.py — Unit tests for the SQLite persistence layer.

Uses an in-memory database so no files are written during test runs.
"""

import pathlib
import sqlite3
import tempfile
import pytest

from database import db


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a fresh temporary database for each test."""
    db_path = tmp_path / "test_archscale.db"
    db.init_db(db_path)
    return db_path


class TestInitDB:
    def test_creates_tables(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "companies" in tables
        assert "evidence" in tables
        assert "scrape_runs" in tables
        assert "scrape_errors" in tables
        assert "review_history" in tables

    def test_idempotent(self, tmp_db):
        """Calling init_db twice must not raise or duplicate schema."""
        db.init_db(tmp_db)


class TestUpsertCompany:
    def test_insert_new_company(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = db.upsert_company(conn, "example.com", "https://example.com", "architecture", "2024-01-01T00:00:00")
        assert cid is not None and cid > 0

    def test_upsert_does_not_duplicate(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid1 = db.upsert_company(conn, "example.com", "https://example.com", "architecture", "2024-01-01T00:00:00")
            cid2 = db.upsert_company(conn, "example.com", "https://example.com", "architecture", "2024-01-02T00:00:00")
        assert cid1 == cid2, "Same domain_key must not create two company rows."

    def test_different_domains_create_separate_rows(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid1 = db.upsert_company(conn, "alpha.com", "https://alpha.com", "architecture", "2024-01-01")
            cid2 = db.upsert_company(conn, "beta.com", "https://beta.com", "interior", "2024-01-01")
        assert cid1 != cid2

    def test_category_stored(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = db.upsert_company(conn, "studio.in", "https://studio.in", "interior", "2024-01-01")
            comp = db.get_company(conn, cid)
        assert comp["category"] == "interior"


class TestUpsertEvidence:
    def _make_company(self, conn, tmp_db):
        return db.upsert_company(conn, "test.com", "https://test.com", "architecture", "2024-01-01")

    def test_inserts_evidence(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = self._make_company(conn, tmp_db)
            eid = db.upsert_evidence(
                conn, cid, "email", "info@test.com",
                "https://test.com", "Found in footer", "html_content", "2024-01-01"
            )
        assert eid > 0

    def test_no_duplicate_evidence(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = self._make_company(conn, tmp_db)
            eid1 = db.upsert_evidence(
                conn, cid, "email", "info@test.com",
                "https://test.com", "snippet", "html_content", "2024-01-01"
            )
            eid2 = db.upsert_evidence(
                conn, cid, "email", "info@test.com",
                "https://test.com", "updated snippet", "html_content", "2024-01-02"
            )
        assert eid1 == eid2, "Re-scraping the same value+source must not create a duplicate evidence row."

    def test_different_values_create_separate_rows(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = self._make_company(conn, tmp_db)
            eid1 = db.upsert_evidence(
                conn, cid, "phone", "+91 98765 43210", "https://test.com",
                None, "html_content", "2024-01-01"
            )
            eid2 = db.upsert_evidence(
                conn, cid, "phone", "+91 11111 22222", "https://test.com",
                None, "html_content", "2024-01-01"
            )
        assert eid1 != eid2

    def test_null_value_stored(self, tmp_db):
        """A None value (field not found) must be storable."""
        with db.get_connection(tmp_db) as conn:
            cid = self._make_company(conn, tmp_db)
            eid = db.upsert_evidence(
                conn, cid, "owner_name", None,
                "https://test.com", "No owner found", "html_content", "2024-01-01",
                verification_status="Not found"
            )
        assert eid > 0

    def test_verification_status_stored(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = self._make_company(conn, tmp_db)
            eid = db.upsert_evidence(
                conn, cid, "owner_name", "Jane Test",
                "https://test.com/about", "Found in about", "html_content", "2024-01-01",
                verification_status="Needs review"
            )
            rows = db.get_evidence_for_company(conn, cid)
        statuses = [r["verification_status"] for r in rows]
        assert "Needs review" in statuses


class TestScrapeRuns:
    def test_start_and_finish_run(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            run_id = db.start_scrape_run(conn, "2024-01-01T00:00:00")
            conn.commit()

        with db.get_connection(tmp_db) as conn:
            db.finish_scrape_run(conn, run_id, "2024-01-01T00:05:00", 5, 4, 1, "done")

        with db.get_connection(tmp_db) as conn:
            run = conn.execute("SELECT * FROM scrape_runs WHERE id=?", (run_id,)).fetchone()
        assert run["status"] == "done"
        assert run["urls_attempted"] == 5
        assert run["urls_succeeded"] == 4
        assert run["urls_failed"] == 1


class TestSummaryMetrics:
    def test_metrics_on_empty_db(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            metrics = db.get_summary_metrics(conn)
        assert metrics["total_companies"] == 0
        assert metrics["total_evidence"] == 0

    def test_metrics_after_insert(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            cid = db.upsert_company(conn, "x.com", "https://x.com", "architecture", "2024-01-01")
            db.upsert_evidence(conn, cid, "email", "a@x.com", "https://x.com", None, "html_content", "2024-01-01")
            db.upsert_evidence(conn, cid, "owner_name", "Test Person", "https://x.com/about", None, "html_content", "2024-01-01", verification_status="Needs review")

        with db.get_connection(tmp_db) as conn:
            metrics = db.get_summary_metrics(conn)

        assert metrics["total_companies"] == 1
        assert metrics["total_evidence"] == 2
        assert metrics["needs_review"] == 1


class TestListCompanies:
    def test_returns_all_companies(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            db.upsert_company(conn, "a.com", "https://a.com", "architecture", "2024-01-01")
            db.upsert_company(conn, "b.com", "https://b.com", "interior", "2024-01-01")

        with db.get_connection(tmp_db) as conn:
            companies = db.list_companies(conn)
        assert len(companies) == 2

    def test_filter_by_category(self, tmp_db):
        with db.get_connection(tmp_db) as conn:
            db.upsert_company(conn, "a.com", "https://a.com", "architecture", "2024-01-01")
            db.upsert_company(conn, "b.com", "https://b.com", "interior", "2024-01-01")

        with db.get_connection(tmp_db) as conn:
            arch = db.list_companies(conn, category="architecture")
        assert len(arch) == 1
        assert arch[0]["category"] == "architecture"
