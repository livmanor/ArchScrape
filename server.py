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
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

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

logger = logging.getLogger("archscale_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")

DB_PATH = ROOT_DIR / "data" / "archscale.db"

app = FastAPI(
    title="ArchScale Intelligence API",
    description="REST backend for Company Discovery, Website Resolution, and Lead Intelligence",
    version="2.0.0",
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response Models ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    target_input: str = Field(..., description="Company name, domain, or website URL")
    category: str = Field(default="architecture", description="Industry category: architecture | interior | other")
    market_city: Optional[str] = Field(default="", description="Optional city hint for location matching")


class SaveLeadRequest(BaseModel):
    url: str
    organisation: Optional[str] = None
    owner_name: Optional[str] = None
    designation: Optional[str] = None
    city: Optional[str] = None
    org_size: Optional[str] = None
    emails: list[str] = []
    phones: list[str] = []
    socials: dict[str, str] = {}
    services: list[str] = []
    clean_summary: Optional[str] = None
    category: Optional[str] = "architecture"


# ─── API Endpoints ────────────────────────────────────────────────────────────

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
    engine: str = Query("auto", description="auto | firecrawl | directory"),
    live: Optional[bool] = Query(None, description="Toggle for live Firecrawl search"),
    limit: int = Query(10, ge=1, le=50, description="Max results to return"),
):
    """
    Discover candidate companies from live web (Firecrawl) or curated offline directory.
    Returns structured candidate leads with official site resolution status.
    """
    search_term = (query or q or "").strip()
    if not search_term:
        search_term = city or "architects"

    clean_q = search_term
    if city and city.strip() and city.lower() not in clean_q.lower() and city.lower() != "all":
        full_q = f"{clean_q} {city.strip()}"
    else:
        full_q = clean_q

    hits = []
    actual_engine = engine

    # Determine engine
    has_fc = fc_available()
    if live is False:
        use_fc = False
    elif live is True:
        use_fc = has_fc
    elif engine == "auto":
        use_fc = has_fc
    elif engine == "firecrawl":
        use_fc = has_fc
    else:
        use_fc = False

    error_msg = None
    if use_fc:
        try:
            actual_engine = "firecrawl"
            hits = firecrawl_search(full_q, limit=limit, scrape_content=True)
            if not hits:
                # Fallback to local directory
                local_hits = search_local_directory(full_q, limit=limit)
                if local_hits:
                    hits = local_hits
                    actual_engine = "directory_fallback"
        except Exception as exc:
            logger.warning("[Search] Firecrawl failed: %s. Falling back to curated directory.", exc)
            error_msg = str(exc)
            hits = search_local_directory(full_q, limit=limit)
            actual_engine = "directory_fallback"
    else:
        actual_engine = "directory"
        hits = search_local_directory(full_q, limit=limit)

    # Filter by category if requested
    filtered_records = []
    for h in hits:
        d = h.to_dict()
        if category and category.lower() != "all":
            # Check services or category
            srvs = [s.lower() for s in d.get("services", [])]
            cat_lower = category.lower()
            if cat_lower == "interior" and not any("interior" in s for s in srvs):
                continue
            if cat_lower == "architecture" and not any("architect" in s for s in srvs):
                continue
        filtered_records.append(d)

    return {
        "ok": True,
        "query": query,
        "city": city or "",
        "engine": actual_engine,
        "total": len(filtered_records),
        "error": error_msg,
        "results": filtered_records,
    }


@app.post("/api/analyze")
def analyze_company(req: AnalyzeRequest):
    """
    Deep crawl and extract comprehensive business intelligence for a company.
    Provides diagnostic transparency into:
    - Candidate website vs verified official website
    - Resolution source
    - Pages successfully scraped
    - Crawl coverage
    - Supporting source URLs for each extracted fact
    """
    target = req.target_input.strip()
    if not target:
        raise HTTPException(status_code=400, detail="target_input cannot be empty")

    logger.info("[API Analyze] Starting deep crawl for: %s", target)
    try:
        result = find_and_extract_company_lead(
            target_input=target,
            db_path=DB_PATH,
            category=req.category,
            market_city=req.market_city or "",
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error", "Website resolution or crawl failed"),
                "resolution": result.get("resolution", {}),
                "target_input": target,
            }
        return result
    except Exception as exc:
        logger.exception("[API Analyze] Failed for %s", target)
        raise HTTPException(status_code=500, detail=str(exc))


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
    res = save_structured_lead_to_db(req.dict(), db_path=DB_PATH, category=req.category or "architecture")
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
