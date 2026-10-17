-- ArchScale Intelligence Platform — SQLite Schema
-- Version 1.0

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─────────────────────────────────────────────
-- Scraping runs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    status          TEXT    NOT NULL DEFAULT 'running',  -- running | done | failed
    urls_attempted  INTEGER NOT NULL DEFAULT 0,
    urls_succeeded  INTEGER NOT NULL DEFAULT 0,
    urls_failed     INTEGER NOT NULL DEFAULT 0,
    notes           TEXT
);

-- ─────────────────────────────────────────────
-- Companies
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_key      TEXT    NOT NULL UNIQUE,   -- normalised domain used as dedup key
    seed_url        TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT 'architecture',  -- architecture | interior | other
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    last_scraped_at TEXT,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain_key);
CREATE INDEX IF NOT EXISTS idx_companies_category ON companies(category);

-- ─────────────────────────────────────────────
-- Field-level evidence
-- Each row = one candidate value for one field of one company.
-- Multiple candidates per field are allowed (e.g., two phone numbers found).
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    field_name      TEXT    NOT NULL,   -- e.g. owner_name, email, phone, website …
    extracted_value TEXT,               -- NULL when field is genuinely absent
    source_url      TEXT    NOT NULL,
    supporting_text TEXT,               -- surrounding HTML snippet or JSON-LD context
    extraction_method TEXT,             -- html_meta | json_ld | html_content | structured
    extracted_at    TEXT    NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'Extracted',
                                        -- Extracted | Source checked | Cross-verified
                                        --            | Not found | Needs review
    is_primary      INTEGER NOT NULL DEFAULT 1,  -- 1 = preferred candidate
    reviewer_note   TEXT,
    reviewed_at     TEXT,
    UNIQUE(company_id, field_name, extracted_value, source_url)
);

CREATE INDEX IF NOT EXISTS idx_evidence_company   ON evidence(company_id);
CREATE INDEX IF NOT EXISTS idx_evidence_field     ON evidence(company_id, field_name);
CREATE INDEX IF NOT EXISTS idx_evidence_status    ON evidence(verification_status);

-- ─────────────────────────────────────────────
-- Scrape errors
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    company_id      INTEGER REFERENCES companies(id),
    url             TEXT    NOT NULL,
    error_type      TEXT    NOT NULL,   -- http_error | timeout | ssrf_blocked | robots_blocked | parse_error
    error_detail    TEXT,
    occurred_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_errors_run ON scrape_errors(scrape_run_id);

-- ─────────────────────────────────────────────
-- Review history (optional audit trail)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id     INTEGER NOT NULL REFERENCES evidence(id),
    action          TEXT    NOT NULL,  -- approved | rejected | flagged
    previous_status TEXT,
    new_status      TEXT,
    reviewer_note   TEXT,
    acted_at        TEXT    NOT NULL
);
