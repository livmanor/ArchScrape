"""
services/company_service.py — Orchestrates scraping, extraction, and persistence.

This is the single entry point that ties together:
    Discovery → Fetch → Extract → Persist → Report
"""

import datetime
import logging
import pathlib
from typing import Callable, Optional

from database import db
from scraper.discovery import DiscoveryEngine, SeedCSVSource
from scraper.extractor import extract, classify_page_role
from scraper.fetcher import fetch, discover_internal_pages, get_session
from scraper.validator import normalise_domain, URLValidationError

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_scrape(
    seed_csv_path: pathlib.Path | None = None,
    db_path: pathlib.Path | None = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Full scraping pipeline.

    1. Initialise DB
    2. Discover URLs (seed CSV)
    3. For each URL:
       a. Fetch homepage
       b. Discover and fetch sub-pages (about, contact, team)
       c. Extract candidates from each page
       d. Persist evidence with deduplication
    4. Close scrape run and return summary

    Parameters
    ----------
    seed_csv_path: Override path for the seed CSV.
    db_path:       Override path for the SQLite database.
    progress_callback: Called with status string messages during scraping.

    Returns
    -------
    dict with keys: run_id, urls_attempted, urls_succeeded, urls_failed, errors
    """
    def log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Initialise DB
    db.init_db(db_path)

    session = get_session()
    errors: list[dict] = []
    urls_attempted = 0
    urls_succeeded = 0
    urls_failed = 0

    with db.get_connection(db_path) as conn:
        run_id = db.start_scrape_run(conn, _now_iso())
        conn.commit()

    # Discover URLs
    engine = DiscoveryEngine(sources=[
        SeedCSVSource(seed_csv_path) if seed_csv_path else SeedCSVSource()
    ])
    discovered = engine.discover_all()

    if not discovered:
        log("⚠️  No URLs discovered. Check that data/seed_urls.csv exists and has content.")
        with db.get_connection(db_path) as conn:
            db.finish_scrape_run(conn, run_id, _now_iso(), 0, 0, 0, "done", "No URLs found")
        return {"run_id": run_id, "urls_attempted": 0, "urls_succeeded": 0,
                "urls_failed": 0, "errors": []}

    log(f"🔍 Discovered {len(discovered)} URLs to scrape.")

    for item in discovered:
        urls_attempted += 1
        url = item.url
        category = item.category
        domain_key = normalise_domain(url)

        log(f"[{urls_attempted}/{len(discovered)}] Scraping: {url}")

        # ── Fetch homepage ────────────────────────────────────────────────
        result = fetch(url, session=session)

        with db.get_connection(db_path) as conn:
            company_id = db.upsert_company(
                conn, domain_key, url, category, _now_iso(), run_id
            )
            conn.commit()

        if not result.ok:
            log(f"  ✗ Failed ({result.error_type}): {result.error_detail}")
            with db.get_connection(db_path) as conn:
                db.log_scrape_error(
                    conn, run_id, company_id, url,
                    result.error_type or "unknown",
                    result.error_detail, _now_iso(),
                )
                # Record a "Not found" evidence row so the company appears in UI
                db.upsert_evidence(
                    conn, company_id, "fetch_status",
                    f"Failed: {result.error_type}",
                    url, result.error_detail, "structured",
                    _now_iso(), "Not found",
                )
                conn.commit()
            urls_failed += 1
            errors.append({"url": url, "error": result.error_type, "detail": result.error_detail})
            continue

        urls_succeeded += 1

        # ── Extract from homepage ─────────────────────────────────────────
        page_role = classify_page_role(result.url)
        homepage_candidates = extract(result.html, result.url, page_role)
        _persist_candidates(homepage_candidates, company_id, db_path)

        # ── Discover sub-pages ────────────────────────────────────────────
        sub_pages = discover_internal_pages(result.url, result.html, session=session)
        log(f"  → Found {len(sub_pages)} sub-page(s): {sub_pages}")

        for sub_url in sub_pages:
            log(f"     Fetching sub-page: {sub_url}")
            sub_result = fetch(sub_url, session=session)
            if not sub_result.ok:
                log(f"     ✗ Sub-page failed ({sub_result.error_type})")
                with db.get_connection(db_path) as conn:
                    db.log_scrape_error(
                        conn, run_id, company_id, sub_url,
                        sub_result.error_type or "unknown",
                        sub_result.error_detail, _now_iso(),
                    )
                    conn.commit()
                continue

            sub_role = classify_page_role(sub_result.url)
            sub_candidates = extract(sub_result.html, sub_result.url, sub_role)
            _persist_candidates(sub_candidates, company_id, db_path)
            log(f"     ✓ Extracted {len(sub_candidates)} candidates from {sub_url}")

        log(f"  ✓ Done — {len(homepage_candidates)} homepage candidates stored.")

    # ── Close run ─────────────────────────────────────────────────────────
    with db.get_connection(db_path) as conn:
        db.finish_scrape_run(
            conn, run_id, _now_iso(),
            urls_attempted, urls_succeeded, urls_failed,
            status="done" if not errors else "done_with_errors",
            notes=f"{len(errors)} URL(s) failed." if errors else None,
        )
        conn.commit()

    log(f"🏁 Scrape run {run_id} complete. "
        f"{urls_succeeded}/{urls_attempted} succeeded, {urls_failed} failed.")

    return {
        "run_id": run_id,
        "urls_attempted": urls_attempted,
        "urls_succeeded": urls_succeeded,
        "urls_failed": urls_failed,
        "errors": errors,
    }


def _persist_candidates(candidates, company_id: int, db_path) -> None:
    """Write a list of Candidate objects into the evidence table."""
    if not candidates:
        return
    with db.get_connection(db_path) as conn:
        for c in candidates:
            try:
                db.upsert_evidence(
                    conn,
                    company_id=company_id,
                    field_name=c.field_name,
                    extracted_value=c.value,
                    source_url=c.source_url,
                    supporting_text=c.supporting_text,
                    extraction_method=c.method,
                    extracted_at=_now_iso(),
                    verification_status=c.verification_status,
                )
            except Exception as exc:
                logger.warning("Failed to persist candidate %s=%s: %s", c.field_name, c.value, exc)
        conn.commit()


def export_csv(
    db_path: pathlib.Path | None = None,
    search: str = "",
    category: str = "",
    city: str = "",
    status: str = "",
) -> "str":
    """
    Return CSV string of the filtered company list.
    Used by the dashboard export feature.
    """
    import io
    import pandas as pd

    with db.get_connection(db_path) as conn:
        rows = db.list_companies(conn, search=search, category=category, city=city, status=status)

    if not rows:
        return ""

    records = [dict(r) for r in rows]
    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()
