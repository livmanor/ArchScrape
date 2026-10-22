"""
server.py — FastAPI REST Backend for ArchScale Intelligence Platform.
Wraps the existing Python scraping pipeline, Firecrawl client, and SQLite database
to serve the React frontend without modifying any underlying business logic.
"""

import csv
import io
import logging
import os
import pathlib
import asyncio
import json
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

ROOT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Automatically load environment variables from .env if present
load_dotenv(ROOT_DIR / ".env", override=True)

from database import db
from scraper.finder import resolve_company_url, get_city_seed_companies
from scraper.firecrawl_client import (
    is_available as fc_available,
    firecrawl_search,
    search_local_directory,
    test_firecrawl_connection,
)
from services.company_service import (
    find_and_extract_company_lead,
    save_structured_lead_to_db,
    get_leads,
)
from scraper.lookup_pipeline import lookup_company
from scraper.rate_limiter import check_ip_rate_limit, QuotaExceededError

logger = logging.getLogger("archscale_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")

DB_PATH = ROOT_DIR / "data" / "archscale.db"

app = FastAPI(
    title="ArchScale Intelligence API",
    description="REST backend for Company Discovery, Website Resolution, and Lead Intelligence",
    version="2.0.0",
)

# Restrict CORS to specified origins or Vercel preview/production domains
raw_cors = os.getenv("CORS_ORIGINS", "").strip()
if raw_cors == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed_origins = [o.strip() for o in raw_cors.split(",") if o.strip()] if raw_cors else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ─── Request / Response Models ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    target_input: Optional[str] = Field(default=None, description="Company name, domain, or website URL")
    target: Optional[str] = Field(default=None, description="Alias for target_input")
    category: str = Field(default="architecture", description="Industry category: architecture | interior | other")
    market_city: Optional[str] = Field(default="", description="Optional city hint for location matching")
    deep: Optional[bool] = Field(default=True, description="Perform deep internal page crawl")


class LookupRequest(BaseModel):
    name: str = Field(description="Company name to look up (e.g. 'design cafe')")
    refresh: bool = Field(default=False, description="Bypass cache and force fresh lookup")
    website_override: Optional[str] = Field(default=None, description="Optional website URL override")


class SaveLeadRequest(BaseModel):
    url: Optional[str] = None
    website: Optional[str] = None
    organisation: Optional[str] = None
    company_name: Optional[str] = None
    owner_name: Optional[str] = None
    designation: Optional[str] = None
    city: Optional[str] = None
    org_size: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    emails: list[str] = []
    phones: list[str] = []
    socials: dict[str, str] = {}
    social_links: dict[str, str] = {}
    services: list[str] = []
    clean_summary: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = "architecture"


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/health")
@app.get("/api/health")
def health_check():
    """System health, SQLite status, and Firecrawl integration availability."""
    db_ok = False
    metrics = {}
    try:
        db.init_db(DB_PATH)
        with db.get_connection(DB_PATH) as conn:
            metrics = db.get_summary_metrics(conn)
        db_ok = True
    except Exception as exc:
        logger.warning("Database health check issue: %s", exc)

    return {
        "status": "healthy",
        "database_connected": db_ok,
        "firecrawl_available": fc_available(),
        "metrics": metrics,
    }


@app.get("/api/search")
def search_companies(
    query: Optional[str] = Query(None, description="Company name, keywords, or query"),
    q: Optional[str] = Query(None, description="Alias for query"),
    city: Optional[str] = Query(None, description="Filter or target city"),
    category: Optional[str] = Query(None, description="Industry category filter"),
    engine: str = Query("firecrawl", description="Always firecrawl"),
    live: Optional[bool] = Query(True, description="Always live Firecrawl search"),
    limit: int = Query(10, ge=1, le=50, description="Max results to return"),
):
    """
    Discover candidate companies via Firecrawl live web search.
    Returns structured candidate leads with official site resolution status.
    """
    search_term = (query or q or "").strip()
    if not search_term:
        search_term = city or "architects"

    # Use the query exactly as entered — no city appending (req. 9)
    full_q = search_term

    hits = []
    actual_engine = "firecrawl"
    error_msg = None

    try:
        hits = firecrawl_search(full_q, limit=limit, scrape_content=True)
    except Exception as exc:
        logger.warning("[Search] Firecrawl failed: %s", exc)
        error_msg = str(exc)
        hits = []

    # Serialize and filter hits
    filtered_records = []
    from urllib.parse import urlparse
    for h in hits:
        # Support objects with to_dict() and plain dicts
        try:
            d = h.to_dict() if hasattr(h, "to_dict") else (h if isinstance(h, dict) else vars(h))
        except Exception:
            continue

        # Only apply category filter when there is service data to check;
        # Firecrawl hits often have no services list — don't silently drop them
        if category and category.lower() not in ("", "all"):
            srvs = [s.lower() for s in d.get("services", [])]
            if srvs:
                cat_lower = category.lower()
                if cat_lower == "interior" and not any("interior" in s for s in srvs):
                    continue
                if cat_lower == "architecture" and not any("architect" in s for s in srvs):
                    continue

        # Normalize fields for UI
        name = d.get("name") or d.get("organisation") or d.get("title") or "Unnamed Practice"
        snippet = d.get("snippet") or d.get("clean_summary") or d.get("description") or ""
        v_stat = (d.get("verification_status") or "candidate").lower()
        if "verified" in v_stat or "extracted" in v_stat:
            norm_status = "verified"
            is_ver = True
        elif "candidate" in v_stat or "review" in v_stat:
            norm_status = "candidate"
            is_ver = False
        else:
            norm_status = "not_found"
            is_ver = False

        u = d.get("url") or ""
        dom = d.get("domain") or (urlparse(u).netloc if u else "")

        d["name"] = name
        d["snippet"] = snippet
        d["domain"] = dom
        d["verified"] = is_ver
        d["verification_status"] = norm_status
        d["category"] = d.get("category") or (d.get("services", ["Architecture"])[0] if d.get("services") else "Architecture")

        filtered_records.append(d)

    return {
        "ok": True,
        "query": full_q,
        "city": city or "",
        "engine": actual_engine,
        "source": actual_engine,
        "count": len(filtered_records),
        "total": len(filtered_records),
        "error": error_msg,
        "results": filtered_records,
    }


@app.post("/api/analyze")
async def analyze_company(req: AnalyzeRequest):
    """
    Deep crawl and extract comprehensive business intelligence for a company.
    Uses Google Places + OpenRouter verification first, falling back to legacy crawler if needed.
    """
    target = (req.target_input or req.target or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="target cannot be empty")

    logger.info("[API Analyze] Starting deep crawl for: %s", target)
    try:
        # 1. Try modern OpenRouter lookup pipeline with match guard
        lookup_res = await lookup_company(name=target, db_path=DB_PATH)
        if lookup_res.get("match_status") == "matched":
            org_name = lookup_res.get("organisation_name", {}).get("value") or target
            ceo_obj = lookup_res.get("ceo", {})
            owner = ceo_obj.get("name", {}).get("value")
            desig = ceo_obj.get("designation", {}).get("value")
            website_url = lookup_res.get("website", {}).get("value") or target
            city = lookup_res.get("city", {}).get("value")
            email = lookup_res.get("email", {}).get("value")
            phone = lookup_res.get("mobile", {}).get("value")
            socials = {k: v["value"] for k, v in lookup_res.get("socials", {}).items() if v.get("value")}
            services = [s["value"] for s in lookup_res.get("services", []) if s.get("value")]

            return {
                "ok": True,
                "company_name": org_name if org_name != "not found" else target,
                "website": website_url if website_url != "not found" else target,
                "verification_status": "Verified",
                "verification_score": 0.95,
                "city": city if city != "not found" else (req.market_city or ""),
                "owner_name": owner if owner != "not found" else "Not found",
                "designation": desig if desig != "not found" else "Not found",
                "org_size": lookup_res.get("company_size", {}).get("value", "Not stated"),
                "email": email if email != "not found" else "Not found",
                "phone": phone if phone != "not found" else "Not found",
                "social_links": socials,
                "services": services,
                "description": f"Verified via Google Places and OpenRouter ({len(lookup_res.get('people', []))} team members verified).",
                "source_urls": [p["source"] for p in lookup_res.get("people", []) if p.get("source")],
                "resolution_info": {
                    "resolution_source": "Google Places + OpenRouter",
                    "original_url": target,
                    "verified_url": website_url,
                    "pages_scraped": [p["source"] for p in lookup_res.get("people", []) if p.get("source")],
                    "verification_notes": ["Domain and entity verified via Google Places & OpenRouter"],
                    "scrape_errors": [],
                },
                "field_evidence": [
                    {
                        "field_name": "owner_name",
                        "extracted_value": owner,
                        "verification_status": "Verified",
                        "source_url": ceo_obj.get("name", {}).get("source", ""),
                        "context_text": f"Leader role: {desig}",
                    }
                ] if owner and owner != "not found" else [],
            }
        elif lookup_res.get("match_status") == "ambiguous":
            return {
                "ok": False,
                "company_name": target,
                "website": target,
                "verification_status": "Ambiguous",
                "verification_score": 0.0,
                "city": req.market_city or "",
                "owner_name": "Not found",
                "designation": "Not found",
                "org_size": "Not stated",
                "email": "Not found",
                "phone": "Not found",
                "social_links": {},
                "services": [],
                "description": lookup_res.get("ambiguity_reason", "Multiple matching branches or website did not match business name (aggregator rejected)."),
                "source_urls": [],
                "resolution_info": {
                    "resolution_source": "Ambiguous Match Guard",
                    "original_url": target,
                    "verified_url": "",
                    "pages_scraped": [],
                    "verification_notes": ["Aggregator domain or ambiguous entity detected; rejected."],
                    "scrape_errors": [],
                },
                "field_evidence": [],
            }

        # 2. Fallback to legacy extractor
        result = find_and_extract_company_lead(
            target_input=target,
            db_path=DB_PATH,
            category=req.category,
            market_city=req.market_city or "",
        )
        if not result.get("ok"):
            res_info = result.get("resolution", {})
            return {
                "ok": False,
                "company_name": target,
                "website": res_info.get("url") or target,
                "verification_status": "Not Found",
                "verification_score": 0.0,
                "city": req.market_city or "",
                "owner_name": "Not found",
                "designation": "Not found",
                "org_size": "Not stated",
                "email": "Not found",
                "phone": "Not found",
                "social_links": {},
                "services": [],
                "description": result.get("error", "Website could not be reached or verified"),
                "source_urls": [],
                "resolution_info": {
                    "resolution_source": res_info.get("method") or "heuristic",
                    "original_url": target,
                    "verified_url": "",
                    "pages_scraped": [],
                    "verification_notes": [result.get("error", "Failed to resolve official domain")],
                    "scrape_errors": [result.get("error", "Crawl unreachable")],
                },
                "field_evidence": [],
            }

        # Standardize structured CompanyLead response
        org_name = result.get("organisation") or result.get("domain") or target
        website_url = result.get("url") or (f"https://{result['domain']}" if result.get("domain") else target)
        res_info = result.get("resolution", {})
        is_verified = bool(res_info.get("found"))

        field_evidence = []
        for fname, items in result.get("field_sources", {}).items():
            for it in items:
                field_evidence.append({
                    "field_name": fname,
                    "extracted_value": str(it.get("value", "")),
                    "verification_status": it.get("verification_status", "Extracted"),
                    "source_url": it.get("source_url", ""),
                    "context_text": it.get("context", ""),
                })

        return {
            "ok": True,
            "company_name": org_name,
            "website": website_url,
            "verification_status": "Verified" if is_verified else "Candidate",
            "verification_score": 0.95 if is_verified else 0.5,
            "city": result.get("city") or "",
            "owner_name": result.get("owner_name") or "",
            "designation": result.get("designation") or "",
            "org_size": result.get("org_size") or "",
            "email": result.get("email") or "",
            "phone": result.get("mobile") or "",
            "social_links": result.get("social_links") or {},
            "services": result.get("services") or [],
            "description": result.get("description") or "",
            "source_urls": result.get("source_urls_list") or [],
            "resolution_info": {
                "resolution_source": res_info.get("method") or "heuristic",
                "original_url": res_info.get("input_query") or target,
                "verified_url": website_url,
                "pages_scraped": result.get("source_urls_list", []),
                "verification_notes": [res_info.get("notes", "Domain confirmed via DNS and content heuristics")],
                "scrape_errors": [],
            },
            "field_evidence": field_evidence,
        }
    except Exception as exc:
        logger.exception("[API Analyze] Failed for %s", target)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
@app.get("/api/health")
def health_endpoint():
    """
    Returns deployment readiness status and configured keys (booleans only).
    Never exposes API key values.
    """
    return {
        "status": "healthy",
        "keys_configured": {
            "google_places": bool((os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()),
            "firecrawl": bool((os.getenv("FIRECRAWL_API_KEY") or "").strip()),
            "openrouter": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
        },
    }


@app.post("/api/lookup")
async def lookup_company_endpoint(req: LookupRequest, request: Request):
    """
    Unified company lookup pipeline with rate limiting, in-flight deduplication, and SQLite caching.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        await check_ip_rate_limit(client_ip)
    except QuotaExceededError as qe:
        raise HTTPException(status_code=429, detail=qe.message)

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="'name' must not be empty.")

    logger.info("[API Lookup] Starting lookup for '%s' from IP %s (refresh=%s).", name, client_ip, req.refresh)
    try:
        result = await lookup_company(
            name=name,
            db_path=DB_PATH,
            refresh=req.refresh,
            website_override=req.website_override,
        )
        return result
    except QuotaExceededError as qe:
        raise HTTPException(status_code=429, detail=qe.message)
    except Exception as exc:
        logger.exception("[API Lookup] Unhandled error for '%s'", name)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/lookup/stream")
async def stream_lookup_endpoint(
    name: str = Query(..., description="Company name to look up"),
    refresh: bool = Query(False, description="Bypass cache"),
    website_override: Optional[str] = Query(None, description="Optional website URL override"),
    request: Request = None,
):
    """
    Streaming SSE endpoint emitting pipeline events as fields arrive:
    event: places -> {organisation_name, city, mobile, website, match_status}
    event: website -> {pages_scraped, email, socials}
    event: intelligence -> {ceo, people, services, locations, company_size}
    event: done -> full_result
    """
    client_ip = request.client.host if request and request.client else "127.0.0.1"
    try:
        await check_ip_rate_limit(client_ip)
    except QuotaExceededError as qe:
        raise HTTPException(status_code=429, detail=qe.message)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="'name' must not be empty.")

    queue: asyncio.Queue = asyncio.Queue()

    def callback(event: str, data: Any) -> None:
        queue.put_nowait((event, data))

    async def event_generator():
        # Launch lookup in background
        task = asyncio.create_task(
            lookup_company(
                name=clean_name,
                db_path=DB_PATH,
                refresh=refresh,
                website_override=website_override.strip() if website_override else None,
                progress_callback=callback,
            )
        )

        while not task.done() or not queue.empty():
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=0.3)
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        try:
            res = await task
            yield f"event: done\ndata: {json.dumps(res, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/companies")
def list_saved_companies(
    search: Optional[str] = Query(None, description="Search term for company or owner"),
    city: Optional[str] = Query(None, description="Filter by city"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Verification status filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List persisted company leads from SQLite database with filtering."""
    try:
        leads = get_leads(
            db_path=DB_PATH,
            search=search or "",
            city=city or "",
        )
        if category and category.lower() != "all":
            leads = [l for l in leads if category.lower() in str(l.get("category", "")).lower()]
        if status and status.lower() != "all":
            leads = [l for l in leads if status.lower() in str(l.get("owner_status", "")).lower() or status.lower() in str(l.get("email_status", "")).lower()]
        total = len(leads)
        paged = leads[offset : offset + limit]
        return {
            "ok": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "companies": paged,
        }
    except Exception as exc:
        logger.exception("[API Companies] Listing failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/companies/{company_id}")
def get_company_detail(company_id: int):
    """Retrieve full company evidence and provenance for a single saved company."""
    with db.get_connection(DB_PATH) as conn:
        company = db.get_company(conn, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        evidence = db.get_evidence_for_company(conn, company_id)

    return {
        "ok": True,
        "company": dict(company) if company else None,
        "evidence": [dict(e) for e in evidence],
    }


@app.post("/api/leads/save")
def save_lead(req: SaveLeadRequest):
    """Persist an extracted lead directly to the SQLite database."""
    target_url = req.url or req.website or ""
    org = req.organisation or req.company_name or ""
    emails = req.emails or ([req.email] if req.email else [])
    phones = req.phones or ([req.phone] if req.phone else [])
    socials = req.socials or req.social_links or {}
    summary = req.clean_summary or req.description or ""

    lead_dict = {
        "url": target_url,
        "organisation": org,
        "owner_name": req.owner_name or "Not found",
        "designation": req.designation or "Not found",
        "city": req.city or "Not found",
        "org_size": req.org_size or "Not found",
        "emails": emails,
        "phones": phones,
        "socials": socials,
        "services": req.services or [],
        "clean_summary": summary,
    }
    res = save_structured_lead_to_db(lead_dict, db_path=DB_PATH, category=req.category or "architecture")
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Save failed"))
    return res


@app.get("/api/presets")
def get_search_presets():
    """Return preset queries, target cities, and featured sample firms."""
    return {
        "cities": [
            "Delhi NCR", "Mumbai", "Bengaluru", "Chennai", "Hyderabad",
            "Pune", "Ahmedabad", "Kolkata", "Jaipur", "Coimbatore"
        ],
        "categories": [
            {"id": "all", "label": "All Disciplines"},
            {"id": "architecture", "label": "Architecture Firms"},
            {"id": "interior", "label": "Interior Design Studios"},
        ],
        "quick_searches": [
            {"label": "🏙️ Chennai Interiors", "query": "top interior design studios Chennai", "city": "Chennai", "category": "interior"},
            {"label": "🏙️ Delhi Architects", "query": "leading architecture firms Delhi", "city": "Delhi NCR", "category": "architecture"},
            {"label": "🏙️ Bengaluru Studios", "query": "best architecture and interior studios Bengaluru", "city": "Bengaluru", "category": "all"},
            {"label": "🏙️ Mumbai Practices", "query": "top architecture practices Mumbai", "city": "Mumbai", "category": "architecture"},
            {"label": "🏙️ Hyderabad Firms", "query": "best architecture design Hyderabad", "city": "Hyderabad", "category": "architecture"},
        ],
        "sample_companies": [
            {"name": "Morphogenesis", "city": "Delhi NCR", "domain": "morphogenesis.org"},
            {"name": "Studio Lotus", "city": "Delhi NCR", "domain": "studiolotus.in"},
            {"name": "Modo Designs", "city": "Ahmedabad", "domain": "mododesigns.co.in"},
            {"name": "Bizzoppo Interiors", "city": "Chennai", "domain": "bizzoppo.com"},
            {"name": "Anbre Interiors", "city": "Chennai", "domain": "anbre.in"},
        ],
    }


@app.get("/api/export")
def export_leads_csv(
    search: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
):
    """Export filtered leads directory as downloadable CSV."""
    leads = get_leads(
        db_path=DB_PATH,
        search=search or "",
        city=city or "",
    )
    if category and category.lower() != "all":
        leads = [l for l in leads if category.lower() in str(l.get("category", "")).lower()]
    if status and status.lower() != "all":
        leads = [l for l in leads if status.lower() in str(l.get("owner_status", "")).lower() or status.lower() in str(l.get("email_status", "")).lower()]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Organisation", "Owner / Founder", "Designation", "City",
        "Email", "Phone", "Website", "Team Size", "Services", "Verification Status"
    ])
    for l in leads:
        writer.writerow([
            l.get("organisation", ""),
            l.get("owner_name", ""),
            l.get("designation", ""),
            l.get("city", ""),
            l.get("email", ""),
            l.get("phone", ""),
            l.get("website", ""),
            l.get("org_size", ""),
            l.get("services", ""),
            l.get("verification_status", ""),
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=archscale_leads.csv"},
    )


# Mount built React SPA frontend if present
_FRONTEND_DIST = pathlib.Path(__file__).parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="API route not found")
        target_file = _FRONTEND_DIST / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
