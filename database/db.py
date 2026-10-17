"""
database/db.py — SQLite persistence layer for ArchScale Intelligence Platform.

All SQL uses parameterised queries to prevent injection. Deduplication is
enforced at the database level (UNIQUE constraints) and at the service level.
"""

import sqlite3
import pathlib
import logging
import datetime
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

_DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "archscale.db"
_SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"


def get_db_path() -> pathlib.Path:
    return _DB_PATH


def migrate_db(conn: sqlite3.Connection) -> None:
    """
    Safely apply schema migrations to the companies table without dropping data.
    Ensures owner_name, designation, org_size, org_size_basis, city columns exist.
    """
    cur = conn.execute("PRAGMA table_info(companies)")
    existing_cols = {row[1] for row in cur.fetchall()}
    new_cols = [
        ("owner_name", "TEXT"),
        ("designation", "TEXT"),
        ("org_size", "TEXT"),
        ("org_size_basis", "TEXT"),
        ("city", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}")
            logger.info("Migrated companies table: added column %s", col_name)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(city)")
    except Exception:
        pass
    conn.commit()


def init_db(db_path: pathlib.Path | None = None) -> pathlib.Path:
    """Create the database file and apply the schema if not already applied."""
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(str(path)) as conn:
        conn.executescript(schema_sql)
        migrate_db(conn)
        conn.commit()

    logger.info("Database initialised at %s", path)
    return path


@contextmanager
def get_connection(db_path: pathlib.Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with row_factory set and foreign keys enabled."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Company operations
# ──────────────────────────────────────────────

def upsert_company(
    conn: sqlite3.Connection,
    domain_key: str,
    seed_url: str,
    category: str,
    now: str,
    scrape_run_id: int | None = None,
) -> int:
    """
    Insert the company or update its updated_at / last_scraped_at timestamp.
    Returns the company id.
    """
    existing = conn.execute(
        "SELECT id FROM companies WHERE domain_key = ?", (domain_key,)
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE companies
            SET updated_at = ?, last_scraped_at = ?, scrape_run_id = ?
            WHERE domain_key = ?
            """,
            (now, now, scrape_run_id, domain_key),
        )
        return existing["id"]

    cur = conn.execute(
        """
        INSERT INTO companies (domain_key, seed_url, category, created_at, updated_at,
                               last_scraped_at, scrape_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (domain_key, seed_url, category, now, now, now, scrape_run_id),
    )
    return cur.lastrowid


def get_company(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM companies WHERE id = ?", (company_id,)
    ).fetchone()


def list_companies(
    conn: sqlite3.Connection,
    search: str = "",
    category: str = "",
    city: str = "",
    status: str = "",
) -> list[sqlite3.Row]:
    """
    Return companies joined with their primary evidence values so the dashboard
    can display a flat table without N+1 queries.
    """
    # We pivot the evidence table into columns using aggregate subqueries.
    query = """
    SELECT
        c.id,
        c.domain_key,
        c.seed_url,
        c.category,
        c.last_scraped_at,
        c.created_at,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'org_name'
           AND e.is_primary = 1 LIMIT 1) AS org_name,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'owner_name'
           AND e.is_primary = 1 LIMIT 1) AS owner_name,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'designation'
           AND e.is_primary = 1 LIMIT 1) AS designation,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'org_size'
           AND e.is_primary = 1 LIMIT 1) AS org_size,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'phone'
           AND e.is_primary = 1 LIMIT 1) AS phone,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'email'
           AND e.is_primary = 1 LIMIT 1) AS email,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'city'
           AND e.is_primary = 1 LIMIT 1) AS city,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'website'
           AND e.is_primary = 1 LIMIT 1) AS website,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'linkedin'
           AND e.is_primary = 1 LIMIT 1) AS linkedin,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'instagram'
           AND e.is_primary = 1 LIMIT 1) AS instagram,
        (SELECT e.extracted_value FROM evidence e
         WHERE e.company_id = c.id AND e.field_name = 'facebook'
           AND e.is_primary = 1 LIMIT 1) AS facebook,
        (SELECT COUNT(*) FROM evidence e
         WHERE e.company_id = c.id
           AND e.verification_status = 'Needs review') AS needs_review_count,
        (SELECT COUNT(*) FROM evidence e
         WHERE e.company_id = c.id) AS total_fields
    FROM companies c
    WHERE 1=1
    """
    params: list[Any] = []

    if search:
        query += """
        AND (
            c.domain_key LIKE ?
            OR EXISTS (SELECT 1 FROM evidence e2
                       WHERE e2.company_id = c.id
                         AND e2.extracted_value LIKE ?)
        )
        """
        like = f"%{search}%"
        params.extend([like, like])

    if category:
        query += " AND c.category = ?"
        params.append(category)

    if city:
        query += """
        AND EXISTS (
            SELECT 1 FROM evidence e3
            WHERE e3.company_id = c.id
              AND e3.field_name = 'city'
              AND e3.extracted_value LIKE ?
        )
        """
        params.append(f"%{city}%")

    if status:
        query += """
        AND EXISTS (
            SELECT 1 FROM evidence e4
            WHERE e4.company_id = c.id
              AND e4.verification_status = ?
        )
        """
        params.append(status)

    query += " ORDER BY c.updated_at DESC"
    return conn.execute(query, params).fetchall()


# ──────────────────────────────────────────────
# Evidence operations
# ──────────────────────────────────────────────

def upsert_evidence(
    conn: sqlite3.Connection,
    company_id: int,
    field_name: str,
    extracted_value: str | None,
    source_url: str,
    supporting_text: str | None,
    extraction_method: str,
    extracted_at: str,
    verification_status: str = "Extracted",
    is_primary: int = 1,
) -> int:
    """
    Insert evidence or update supporting_text / timestamp if the same
    (company_id, field_name, extracted_value, source_url) already exists.
    Returns the evidence row id.
    """
    existing = conn.execute(
        """
        SELECT id FROM evidence
        WHERE company_id = ? AND field_name = ? AND extracted_value IS ? AND source_url = ?
        """,
        (company_id, field_name, extracted_value, source_url),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE evidence
            SET supporting_text = ?, extracted_at = ?, verification_status = ?
            WHERE id = ?
            """,
            (supporting_text, extracted_at, verification_status, existing["id"]),
        )
        return existing["id"]

    cur = conn.execute(
        """
        INSERT INTO evidence
            (company_id, field_name, extracted_value, source_url, supporting_text,
             extraction_method, extracted_at, verification_status, is_primary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id, field_name, extracted_value, source_url, supporting_text,
            extraction_method, extracted_at, verification_status, is_primary,
        ),
    )
    return cur.lastrowid


def get_evidence_for_company(
    conn: sqlite3.Connection, company_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM evidence WHERE company_id = ? ORDER BY field_name, is_primary DESC",
        (company_id,),
    ).fetchall()


def update_evidence_status(
    conn: sqlite3.Connection,
    evidence_id: int,
    new_status: str,
    reviewer_note: str | None,
    now: str,
) -> None:
    old = conn.execute(
        "SELECT verification_status FROM evidence WHERE id = ?", (evidence_id,)
    ).fetchone()
    if not old:
        return

    conn.execute(
        "UPDATE evidence SET verification_status = ?, reviewer_note = ?, reviewed_at = ? WHERE id = ?",
        (new_status, reviewer_note, now, evidence_id),
    )
    conn.execute(
        """
        INSERT INTO review_history (evidence_id, action, previous_status, new_status, reviewer_note, acted_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (evidence_id, new_status, old["verification_status"], new_status, reviewer_note, now),
    )


# ──────────────────────────────────────────────
# Scrape run operations
# ──────────────────────────────────────────────

def start_scrape_run(conn: sqlite3.Connection, now: str) -> int:
    cur = conn.execute(
        "INSERT INTO scrape_runs (started_at, status) VALUES (?, 'running')",
        (now,),
    )
    return cur.lastrowid


def finish_scrape_run(
    conn: sqlite3.Connection,
    run_id: int,
    now: str,
    urls_attempted: int,
    urls_succeeded: int,
    urls_failed: int,
    status: str = "done",
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE scrape_runs
        SET finished_at = ?, status = ?, urls_attempted = ?,
            urls_succeeded = ?, urls_failed = ?, notes = ?
        WHERE id = ?
        """,
        (now, status, urls_attempted, urls_succeeded, urls_failed, notes, run_id),
    )


def log_scrape_error(
    conn: sqlite3.Connection,
    run_id: int | None,
    company_id: int | None,
    url: str,
    error_type: str,
    error_detail: str | None,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO scrape_errors (scrape_run_id, company_id, url, error_type, error_detail, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, company_id, url, error_type, error_detail, now),
    )


def get_summary_metrics(conn: sqlite3.Connection) -> dict:
    total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    total_evidence  = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    needs_review    = conn.execute(
        "SELECT COUNT(*) FROM evidence WHERE verification_status = 'Needs review'"
    ).fetchone()[0]
    not_found       = conn.execute(
        "SELECT COUNT(*) FROM evidence WHERE verification_status = 'Not found'"
    ).fetchone()[0]
    last_run        = conn.execute(
        "SELECT started_at, status FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    errors_last_run = 0
    if last_run:
        run = conn.execute(
            "SELECT id FROM scrape_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if run:
            errors_last_run = conn.execute(
                "SELECT COUNT(*) FROM scrape_errors WHERE scrape_run_id = ?",
                (run["id"],),
            ).fetchone()[0]

    return {
        "total_companies": total_companies,
        "total_evidence": total_evidence,
        "needs_review": needs_review,
        "not_found": not_found,
        "last_run": dict(last_run) if last_run else None,
        "errors_last_run": errors_last_run,
    }


def get_leads_data(
    conn: sqlite3.Connection,
    search: str = "",
    city: str = "",
    org_size: str = "",
) -> list[dict]:
    """
    Returns one row per company formatted as a Lead record with:
    owner_name, organisation, designation, org_size, mobile, email, city, source_urls, social_links.
    Also returns metadata for UI badges (owner_status, email_status, mobile_status, org_size_basis).
    """
    companies = conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall()
    leads = []

    for c in companies:
        c_id = c["id"]
        ev_rows = conn.execute(
            "SELECT * FROM evidence WHERE company_id = ? ORDER BY is_primary DESC, id ASC",
            (c_id,),
        ).fetchall()

        # Gather fields
        org_name = None
        c_cols = c.keys()
        owner_name = c["owner_name"] if "owner_name" in c_cols and c["owner_name"] else None
        designation = c["designation"] if "designation" in c_cols and c["designation"] else None
        c_org_size = c["org_size"] if "org_size" in c_cols and c["org_size"] else None
        org_size_basis = c["org_size_basis"] if "org_size_basis" in c_cols and c["org_size_basis"] else None
        c_city = c["city"] if "city" in c_cols and c["city"] else None

        phones = []
        emails = []
        socials = {}
        source_urls = set()
        if c["seed_url"]:
            source_urls.add(c["seed_url"])

        owner_status = "Not found"
        email_status = "Not found"
        mobile_status = "Not found"
        city_status = "Not found"

        for row in ev_rows:
            fn = row["field_name"]
            val = row["extracted_value"]
            src = row["source_url"]
            stat = row["verification_status"]
            if src:
                source_urls.add(src)

            if fn == "org_name" and not org_name and val:
                org_name = val
            elif fn == "owner_name" and not owner_name and val:
                owner_name = val
                owner_status = stat
            elif fn == "owner_name" and val:
                owner_status = stat
            elif fn == "designation" and not designation and val:
                designation = val
            elif fn == "org_size" and not c_org_size and val:
                c_org_size = val
            elif fn == "org_size_basis" and not org_size_basis and val:
                org_size_basis = val
            elif fn == "city" and not c_city and val:
                c_city = val
                city_status = stat
            elif fn == "city" and val:
                city_status = stat
            elif fn in ("phone", "mobile") and val:
                if val not in phones:
                    phones.append(val)
                mobile_status = stat
            elif fn == "email" and val:
                if val not in emails:
                    emails.append(val)
                email_status = stat
            elif fn in ("linkedin", "instagram", "facebook", "twitter", "youtube", "houzz", "behance") and val:
                if fn not in socials:
                    socials[fn] = val

        if not org_name or org_name.lower() in ("about us", "contact us", "our team", "home", "portfolio", "services"):
            org_name = c["domain_key"]
        owner_name = owner_name or "Not found"
        designation = designation or "Not found"
        c_org_size = c_org_size or "Not found"
        org_size_basis = org_size_basis or "not_found"
        c_city = c_city or "Not found"
        mobile_str = ", ".join(phones) if phones else "Not found"
        email_str = ", ".join(emails) if emails else "Not found"
        source_urls_list = sorted(list(source_urls))
        source_urls_str = ", ".join(source_urls_list)

        lead = {
            "id": c_id,
            "owner_name": owner_name,
            "organisation": org_name,
            "designation": designation,
            "org_size": c_org_size,
            "mobile": mobile_str,
            "email": email_str,
            "city": c_city,
            "source_urls": source_urls_str,
            "source_urls_list": source_urls_list,
            "social_links": socials,
            "social_links_str": ", ".join(f"{k}: {v}" for k, v in socials.items()) if socials else "Not found",
            "owner_status": owner_status if owner_name != "Not found" else "Not found",
            "email_status": email_status if email_str != "Not found" else "Not found",
            "mobile_status": mobile_status if mobile_str != "Not found" else "Not found",
            "city_status": city_status if c_city != "Not found" else "Not found",
            "org_size_basis": org_size_basis,
        }

        # Filtering
        if search:
            s = search.lower()
            if not any(s in str(v).lower() for v in (owner_name, org_name, designation, c_city, mobile_str, email_str)):
                continue
        if city and city.lower() != "all":
            if city.lower() not in c_city.lower():
                continue
        if org_size and org_size.lower() != "all":
            if org_size.lower() != c_org_size.lower():
                continue

        leads.append(lead)

    return leads


def update_lead_fields(
    conn: sqlite3.Connection,
    company_id: int,
    owner_name: str | None = None,
    designation: str | None = None,
    email: str | None = None,
    mobile: str | None = None,
    city: str | None = None,
    org_size: str | None = None,
) -> None:
    """Manually update or correct lead fields in the companies table and record user-verified evidence."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE companies
        SET owner_name = COALESCE(?, owner_name),
            designation = COALESCE(?, designation),
            city = COALESCE(?, city),
            org_size = COALESCE(?, org_size),
            updated_at = ?
        WHERE id = ?
        """,
        (owner_name, designation, city, org_size, now, company_id),
    )
    if owner_name:
        upsert_evidence(conn, company_id, "owner_name", owner_name, "user_override", "Manually verified by user", "user_verified", now, "Verified", 1)
    if designation:
        upsert_evidence(conn, company_id, "designation", designation, "user_override", "Manually verified by user", "user_verified", now, "Verified", 1)
    if email:
        upsert_evidence(conn, company_id, "email", email, "user_override", "Manually verified by user", "user_verified", now, "Verified", 1)
    if mobile:
        upsert_evidence(conn, company_id, "phone", mobile, "user_override", "Manually verified by user", "user_verified", now, "Verified", 1)
    if city:
        upsert_evidence(conn, company_id, "city", city, "user_override", "Manually verified by user", "user_verified", now, "Verified", 1)
    conn.commit()

