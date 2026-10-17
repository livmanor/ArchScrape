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
from scraper.finder import resolve_company_url

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


def _persist_candidates(candidates, company_id: int, db_path=None, conn=None) -> None:
    """Write a list of Candidate objects into the evidence table."""
    if not candidates:
        return
    if conn is not None:
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
    else:
        with db.get_connection(db_path) as c_conn:
            for c in candidates:
                try:
                    db.upsert_evidence(
                        c_conn,
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
            c_conn.commit()


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


LEADS_EXPORT_COLUMNS = [
    "owner_name", "organisation", "designation", "org_size",
    "mobile", "email", "city", "source_urls", "social_links"
]


def get_leads(
    db_path: pathlib.Path | None = None,
    search: str = "",
    city: str = "",
    org_size: str = "",
) -> list[dict]:
    """
    Returns one row per company with the exact leads fields:
    owner_name, organisation, designation, org_size, mobile, email, city, source_urls, social_links.
    """
    with db.get_connection(db_path) as conn:
        return db.get_leads_data(conn, search=search, city=city, org_size=org_size)


def export_leads_csv(leads: list[dict]) -> str:
    """Return CSV formatted string of leads table with the exact columns."""
    import io
    import pandas as pd

    rows = []
    for l in leads:
        rows.append({
            "owner_name": l.get("owner_name", "Not found"),
            "organisation": l.get("organisation", ""),
            "designation": l.get("designation", "Not found"),
            "org_size": l.get("org_size", "Not found"),
            "mobile": l.get("mobile", "Not found"),
            "email": l.get("email", "Not found"),
            "city": l.get("city", "Not found"),
            "source_urls": l.get("source_urls", ""),
            "social_links": l.get("social_links_str", "Not found"),
        })
    df = pd.DataFrame(rows, columns=LEADS_EXPORT_COLUMNS)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def export_leads_excel(leads: list[dict]) -> bytes:
    """Return Excel bytes of leads table with the exact columns."""
    import io
    import pandas as pd

    rows = []
    for l in leads:
        rows.append({
            "owner_name": l.get("owner_name", "Not found"),
            "organisation": l.get("organisation", ""),
            "designation": l.get("designation", "Not found"),
            "org_size": l.get("org_size", "Not found"),
            "mobile": l.get("mobile", "Not found"),
            "email": l.get("email", "Not found"),
            "city": l.get("city", "Not found"),
            "source_urls": l.get("source_urls", ""),
            "social_links": l.get("social_links_str", "Not found"),
        })
    df = pd.DataFrame(rows, columns=LEADS_EXPORT_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
    return buf.getvalue()


def find_and_extract_company_lead(
    target_input: str,
    db_path: pathlib.Path | None = None,
    category: str = "architecture",
    progress_callback: Optional[Callable[[str], None]] = None,
    market_city: Optional[str] = None,
) -> dict:
    """
    Complete end-to-end real company lead finder and source tracer.

    1. Resolves user-entered target company name or domain to its official URL without mocking.
    2. Fetches the homepage and discovers internal subpages (About, Contact, Team, Services, Work).
    3. Extracts all lead fields (Owner, Designation, Email, Mobile, City, Org Size, Social, Services, Projects).
    4. Traces every single field back to the exact source URL and supporting context snippet.
    5. Persists the lead into the database.
    6. Returns rich structured lead intelligence with complete source attribution.
    """
    def log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Ensure database is initialised
    db.init_db(db_path)
    session = get_session()

    log(f"🔎 Resolving target company: '{target_input}'...")

    with db.get_connection(db_path) as conn:
        resolution = resolve_company_url(target_input, db_conn=conn, progress_callback=log)

    if not resolution["found"] or not resolution["url"]:
        log(f"❌ {resolution['notes']}")
        return {
            "ok": False,
            "target_input": target_input,
            "error": resolution["notes"],
            "resolution": resolution,
            "sources_summary": [],
            "field_sources": {},
        }

    target_url = resolution["url"]
    domain = resolution["domain"] or normalise_domain(target_url)
    log(f"🌐 Target URL confirmed: {target_url} (Domain: {domain})")

    # Fetch homepage
    log(f"📥 Fetching official homepage: {target_url} ...")
    hp = fetch(target_url, session=session)
    if not hp.ok:
        err_msg = f"Failed to fetch {target_url}: {hp.error_type} - {hp.error_detail}"
        log(f"❌ {err_msg}")
        return {
            "ok": False,
            "target_input": target_input,
            "error": err_msg,
            "resolution": resolution,
            "sources_summary": [],
            "field_sources": {},
        }

    log(f"✓ Homepage retrieved ({len(hp.html or '')} bytes). Extracting intelligence...")

    all_candidates = []
    pages_scraped = []
    sources_summary = []

    # 1. Homepage extraction
    hp_role = classify_page_role(hp.url)
    hp_candidates = extract(hp.html, hp.url, hp_role, market_city=market_city)
    all_candidates.extend(hp_candidates)
    pages_scraped.append(hp.url)
    sources_summary.append({
        "url": hp.url,
        "page_role": hp_role,
        "status_code": hp.status_code,
        "candidates_count": len(hp_candidates),
        "fields": sorted(list({c.field_name for c in hp_candidates})),
    })

    # 2. Discover subpages
    sub_urls = discover_internal_pages(hp.url, hp.html, session=session)
    log(f"📂 Discovered {len(sub_urls)} sub-pages to crawl for complete executive details...")

    for i, sub_url in enumerate(sub_urls[:8], start=1):
        log(f"   [{i}/{min(len(sub_urls), 8)}] Crawling: {sub_url} ...")
        sub_res = fetch(sub_url, session=session)
        if sub_res.ok and sub_res.html:
            role = classify_page_role(sub_res.url)
            sub_candidates = extract(sub_res.html, sub_res.url, role, market_city=market_city)
            all_candidates.extend(sub_candidates)
            pages_scraped.append(sub_res.url)
            sources_summary.append({
                "url": sub_res.url,
                "page_role": role,
                "status_code": sub_res.status_code,
                "candidates_count": len(sub_candidates),
                "fields": sorted(list({c.field_name for c in sub_candidates})),
            })
            log(f"     ✓ Extracted {len(sub_candidates)} items from {sub_url}")

    # 3. Assemble Lead Fields & Source Tracking
    field_sources: dict[str, list[dict]] = {}
    for c in all_candidates:
        if not c.value:
            continue
        field_sources.setdefault(c.field_name, []).append({
            "value": c.value,
            "source_url": c.source_url,
            "method": c.method,
            "supporting_text": c.supporting_text,
            "verification_status": c.verification_status,
        })

    # Core fields selection
    org_name = None
    if resolution.get("notes") and not resolution["notes"].startswith("http"):
        clean_note = resolution["notes"].split(" - ")[0].strip()
        if clean_note and len(clean_note) >= 3:
            org_name = clean_note
    elif target_input and len(target_input.strip()) >= 3 and "." not in target_input:
        org_name = target_input.strip()

    if not org_name:
        for item in field_sources.get("org_name", []):
            val = item["value"]
            if val and val.lower() not in ("about us", "contact us", "our team", "home", "portfolio", "services"):
                org_name = val
                break
    org_name = org_name or domain

    owner_item = (field_sources.get("owner_name") or [None])[0]
    owner_name = owner_item["value"] if owner_item else "Not found"
    owner_status = owner_item["verification_status"] if owner_item else "Not found"

    desig_item = (field_sources.get("designation") or [None])[0]
    designation = desig_item["value"] if desig_item else "Not found"

    size_item = (field_sources.get("org_size") or [None])[0]
    org_size = size_item["value"] if size_item else "Not found"

    basis_item = (field_sources.get("org_size_basis") or [None])[0]
    org_size_basis = basis_item["value"] if basis_item else "not_found"

    city_item = (field_sources.get("city") or [None])[0]
    city = city_item["value"] if city_item else "Not found"

    # Emails
    emails = []
    for item in field_sources.get("email", []):
        if item["value"] not in emails:
            emails.append(item["value"])

    # Phones
    phones = []
    for item in field_sources.get("phone", []):
        if item["value"] not in phones:
            phones.append(item["value"])

    # Social links
    socials: dict[str, str] = {}
    for sd in ["linkedin", "instagram", "facebook", "twitter", "youtube", "houzz", "behance"]:
        items = field_sources.get(sd, [])
        if items and items[0]["value"]:
            socials[sd] = items[0]["value"]

    # Services
    services = []
    for item in field_sources.get("service", []):
        if item["value"] not in services:
            services.append(item["value"])

    # Projects
    projects = []
    for item in field_sources.get("project", []):
        if item["value"] not in projects:
            projects.append(item["value"])

    # Gallery images
    gallery = []
    for item in field_sources.get("gallery_image", []):
        if item["value"] not in gallery:
            gallery.append(item["value"])

    # Description
    desc_item = (field_sources.get("description") or [None])[0]
    description = desc_item["value"] if desc_item else None

    # Source URLs list
    all_source_urls = sorted(list(set(pages_scraped)))

    # 4. Persist to Database
    now = _now_iso()
    with db.get_connection(db_path) as conn:
        run_id = db.start_scrape_run(conn, now)
        company_id = db.upsert_company(
            conn, domain, target_url, category, now, run_id
        )

        # Update company columns
        conn.execute(
            """
            UPDATE companies
            SET owner_name = ?, designation = ?, org_size = ?, org_size_basis = ?, city = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                owner_name if owner_name != "Not found" else None,
                designation if designation != "Not found" else None,
                org_size if org_size != "Not found" else None,
                org_size_basis if org_size_basis != "not_found" else None,
                city if city != "Not found" else None,
                now,
                company_id,
            ),
        )

        # Save candidates without reopening connection
        _persist_candidates(all_candidates, company_id, conn=conn)
        db.finish_scrape_run(conn, run_id, now, 1, 1, 0, "done")
        conn.commit()

    log(f"✅ Lead intelligence extraction complete for {org_name}! All source links captured.")

    lead_dict = {
        "ok": True,
        "target_input": target_input,
        "company_id": company_id,
        "domain": domain,
        "url": target_url,
        "category": category,
        "organisation": org_name,
        "owner_name": owner_name,
        "owner_status": owner_status,
        "designation": designation,
        "org_size": org_size,
        "org_size_basis": org_size_basis,
        "city": city,
        "mobile": ", ".join(phones) if phones else "Not found",
        "mobile_list": phones,
        "email": ", ".join(emails) if emails else "Not found",
        "email_list": emails,
        "social_links": socials,
        "social_links_str": ", ".join(f"{k}: {v}" for k, v in socials.items()) if socials else "Not found",
        "services": services,
        "projects": projects,
        "gallery": gallery,
        "description": description,
        "source_urls": ", ".join(all_source_urls),
        "source_urls_list": all_source_urls,
        "sources_summary": sources_summary,
        "field_sources": field_sources,
        "resolution": resolution,
        "scraped_at": now,
    }

    return lead_dict

