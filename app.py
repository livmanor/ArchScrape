"""
app.py — ArchScale Intelligence Platform
CEO-facing Competitor Intelligence Dashboard for Indian Architecture & Interior Design Firms.

Run with:   py -m streamlit run app.py
"""

import datetime
import logging
import pathlib
import sys
import time
from typing import Optional

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import db
from services.company_service import (
    run_scrape, export_csv, get_leads, export_leads_csv, export_leads_excel,
    find_and_extract_company_lead
)
from scraper.validator import URLValidationError, validate_url, normalise_domain
from scraper.fetcher import fetch, discover_internal_pages, get_session
from scraper.extractor import extract, classify_page_role

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH  = ROOT / "data" / "archscale.db"
SEED_CSV = ROOT / "data" / "seed_urls.csv"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ArchScale Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1525 55%, #080d18 100%);
    min-height: 100vh;
}

/* ── Header ── */
.arch-header {
    background: linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(16,185,129,0.08) 100%);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 20px;
    padding: 32px 36px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.arch-header::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle at 30% 50%, rgba(99,102,241,0.06) 0%, transparent 60%);
    pointer-events: none;
}
.arch-header h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.2rem; font-weight: 700;
    background: linear-gradient(135deg, #a5b4fc 0%, #34d399 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0;
}
.arch-header .subtitle { color: #64748b; font-size: 0.95rem; margin-top: 6px; }

/* ── Input card ── */
.input-card {
    background: rgba(255,255,255,0.035);
    border: 1px solid rgba(99,102,241,0.2);
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 24px;
}
.input-card-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem; font-weight: 600;
    color: #a5b4fc; margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
}

/* ── Company Intelligence Card ── */
.intel-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 20px;
    transition: all 0.25s;
}
.intel-card:hover {
    border-color: rgba(99,102,241,0.35);
    background: rgba(99,102,241,0.06);
    transform: translateY(-1px);
}
.intel-card-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 16px;
}
.company-name-big {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.35rem; font-weight: 700; color: #e2e8f0;
}
.company-domain-tag {
    font-size: 0.8rem; color: #818cf8; font-weight: 500;
    background: rgba(99,102,241,0.12); padding: 3px 10px; border-radius: 999px;
}
.intel-section-label {
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: #475569; margin: 14px 0 8px;
}
.service-tag {
    display: inline-block;
    background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.2);
    color: #34d399; padding: 3px 12px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 500; margin: 3px;
}
.project-tag {
    display: inline-block;
    background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2);
    color: #c084fc; padding: 3px 12px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 500; margin: 3px;
}
.social-link {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
    color: #94a3b8; padding: 5px 14px; border-radius: 8px; margin: 3px;
    text-decoration: none; font-size: 0.82rem; font-weight: 500;
    transition: all 0.2s;
}
.social-link:hover { background: rgba(99,102,241,0.15); color: #a5b4fc; }
.contact-item { font-size: 0.85rem; color: #94a3b8; margin: 4px 0; }
.contact-item a { color: #818cf8; }
.city-badge {
    font-size: 0.78rem; font-weight: 600;
    background: rgba(245,158,11,0.12); color: #fbbf24;
    padding: 2px 10px; border-radius: 999px;
}
.not-found { color: #374151; font-style: italic; font-size: 0.82rem; }

/* ── Gallery grid ── */
.gallery-grid { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.gallery-img {
    width: 110px; height: 75px;
    object-fit: cover; border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.08);
    transition: transform 0.2s;
}
.gallery-img:hover { transform: scale(1.05); }

/* ── Metric pills ── */
.metric-pill {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    padding: 8px 16px; border-radius: 10px; font-size: 0.85rem;
    color: #94a3b8;
}
.metric-pill strong { color: #a5b4fc; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: rgba(8,13,24,0.98) !important;
    border-right: 1px solid rgba(99,102,241,0.15);
}

/* ── Inputs ── */
.stTextInput > div > input, .stTextArea textarea, .stSelectbox > div {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important; color: #e2e8f0 !important;
}
.stTextInput > div > input:focus {
    border-color: rgba(99,102,241,0.6) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.15) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    letter-spacing: 0.02em !important; padding: 10px 24px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 24px rgba(99,102,241,0.45) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.06) !important;
    color: #94a3b8 !important;
    box-shadow: none !important;
}

/* ── Progress ── */
.stProgress > div > div { background: linear-gradient(90deg, #6366f1, #34d399) !important; }

hr { border-color: rgba(255,255,255,0.06) !important; }
.stAlert { border-radius: 12px !important; }
.stDataFrame { border-radius: 12px; overflow: hidden; }

/* ── Lead Badges & Cards ── */
.badge-extracted {
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 0.72rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.badge-review {
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 0.72rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.badge-notfound {
    background: rgba(100, 116, 139, 0.12);
    color: #64748b;
    border: 1px solid rgba(100, 116, 139, 0.25);
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 0.72rem;
    font-style: italic;
}
.badge-basis {
    background: rgba(99, 102, 241, 0.15);
    color: #a5b4fc;
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 6px;
    padding: 1px 6px;
    font-size: 0.68rem;
    margin-left: 4px;
}
.lead-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 16px 20px;
    margin-bottom: 14px;
    transition: all 0.2s;
}
.lead-card:hover {
    border-color: rgba(99, 102, 241, 0.35);
    background: rgba(255, 255, 255, 0.045);
}
.source-card {
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(99, 102, 241, 0.22);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 12px;
    transition: all 0.2s;
}
.source-card:hover {
    border-color: rgba(99, 102, 241, 0.45);
    background: rgba(15, 23, 42, 0.85);
}
.source-link-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.35);
    color: #a5b4fc !important;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.76rem;
    font-weight: 500;
    text-decoration: none;
    word-break: break-all;
}
.source-link-badge:hover {
    background: rgba(99, 102, 241, 0.28);
    color: #c7d2fe !important;
}
.quote-snippet {
    background: rgba(0, 0, 0, 0.25);
    border-left: 3px solid #6366f1;
    border-radius: 4px;
    padding: 6px 10px;
    font-family: monospace;
    font-size: 0.75rem;
    color: #cbd5e1;
    margin-top: 6px;
    word-break: break-word;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "current_lead": None,
    "target_company_search": "",
    "target_city_hint": "",
    "lead_finder_log": [],
    "intel_results": [],
    "intel_running": False,
    "scrape_log": [],
    "active_intel_idx": None,
    "intel_urls_input": "",
    "intel_city": "Ahmedabad",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── DB init ───────────────────────────────────────────────────────────────────
try:
    db.init_db(DB_PATH)
except Exception as exc:
    st.error(f"❌ Database error: {exc}")
    st.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_primary(evidence_rows, field: str) -> Optional[str]:
    for e in evidence_rows:
        if e["field_name"] == field and e["is_primary"] == 1 and e["extracted_value"]:
            return e["extracted_value"]
    return None


def _get_all(evidence_rows, field: str) -> list[str]:
    return [e["extracted_value"] for e in evidence_rows
            if e["field_name"] == field and e["extracted_value"]]


def _social_icon(platform: str) -> str:
    icons = {
        "linkedin": "💼", "instagram": "📸", "facebook": "👍",
        "twitter": "🐦", "youtube": "▶️", "houzz": "🏠", "behance": "🎨",
    }
    return icons.get(platform, "🔗")


def _scrape_single_url(url: str, category: str = "architecture") -> dict:
    """
    Scrape a single URL and return a structured intelligence dict.
    Does NOT write to the database — used for live competitor analysis.
    """
    session = get_session()
    result = fetch(url, session=session)

    intel = {
        "url": url,
        "final_url": url,
        "domain": normalise_domain(url),
        "category": category,
        "ok": False,
        "error": None,
        "org_name": None,
        "owner_name": None,
        "designation": None,
        "org_size": None,
        "org_size_basis": None,
        "city": None,
        "phone": [],
        "email": [],
        "website": None,
        "description": None,
        "services": [],
        "projects": [],
        "gallery": [],
        "awards": [],
        "social": {},
        "pages_scraped": [],
        "scraped_at": _now(),
    }

    if not result.ok:
        intel["error"] = f"{result.error_type}: {result.error_detail}"
        return intel

    intel["ok"] = True
    intel["final_url"] = result.url

    # Extract from homepage
    role = classify_page_role(result.url)
    candidates = extract(result.html, result.url, role)
    intel["pages_scraped"].append(result.url)

    # Discover sub-pages
    sub_urls = discover_internal_pages(result.url, result.html, session=session)
    for sub_url in sub_urls[:8]:
        sub = fetch(sub_url, session=session)
        if sub.ok:
            sub_role = classify_page_role(sub.url)
            candidates.extend(extract(sub.html, sub.url, sub_role))
            intel["pages_scraped"].append(sub.url)

    # Build structured intel from candidates
    for c in candidates:
        fn = c.field_name
        val = c.value
        if not val:
            continue
        if fn == "org_name" and not intel["org_name"]:
            intel["org_name"] = val
        elif fn == "owner_name" and not intel["owner_name"]:
            intel["owner_name"] = val
        elif fn == "designation" and not intel["designation"]:
            intel["designation"] = val
        elif fn == "org_size" and not intel["org_size"]:
            intel["org_size"] = val
        elif fn == "org_size_basis" and not intel["org_size_basis"]:
            intel["org_size_basis"] = val
        elif fn == "city" and not intel["city"]:
            intel["city"] = val
        elif fn == "description" and not intel["description"]:
            intel["description"] = val
        elif fn == "website" and not intel["website"]:
            intel["website"] = val
        elif fn == "phone" and val not in intel["phone"]:
            intel["phone"].append(val)
        elif fn == "email" and val not in intel["email"]:
            intel["email"].append(val)
        elif fn == "service" and val not in intel["services"]:
            intel["services"].append(val)
        elif fn == "project" and val not in intel["projects"]:
            intel["projects"].append(val)
        elif fn == "gallery_image" and val not in intel["gallery"]:
            intel["gallery"].append(val)
        elif fn == "award" and val not in intel["awards"]:
            intel["awards"].append(val)
        elif fn in ("linkedin", "instagram", "facebook", "twitter",
                    "youtube", "houzz", "behance"):
            if fn not in intel["social"]:
                intel["social"][fn] = val

    intel["org_name"] = intel["org_name"] or intel["domain"]
    return intel


def _save_intel_to_db(intel: dict) -> None:
    """Persist a live intel result to the database for future reference."""
    now = _now()
    with db.get_connection(DB_PATH) as conn:
        run_id = db.start_scrape_run(conn, now)
        company_id = db.upsert_company(
            conn, intel["domain"], intel["url"],
            intel["category"], now, run_id,
        )
        field_map = {
            "org_name": intel.get("org_name"),
            "owner_name": intel.get("owner_name"),
            "designation": intel.get("designation"),
            "org_size": intel.get("org_size"),
            "org_size_basis": intel.get("org_size_basis"),
            "city": intel.get("city"),
            "website": intel.get("website"),
            "description": intel.get("description"),
        }
        for field, val in field_map.items():
            if val:
                status = "Needs review" if field in ("owner_name", "designation") else ("Extracted" if val != "Not found" else "Not found")
                db.upsert_evidence(conn, company_id, field, val, intel["url"],
                                   None, "structured", now, verification_status=status)
        for ph in intel.get("phone", []):
            db.upsert_evidence(conn, company_id, "phone", ph, intel["url"],
                               None, "html_content", now)
        for em in intel.get("email", []):
            db.upsert_evidence(conn, company_id, "email", em, intel["url"],
                               None, "html_content", now)
        for svc in intel.get("services", []):
            db.upsert_evidence(conn, company_id, "service", svc, intel["url"],
                               None, "html_content", now)
        for proj in intel.get("projects", []):
            db.upsert_evidence(conn, company_id, "project", proj, intel["url"],
                               None, "html_content", now)
        for platform, link in intel.get("social", {}).items():
            db.upsert_evidence(conn, company_id, platform, link, intel["url"],
                               None, "html_content", now)
        db.finish_scrape_run(conn, run_id, _now(), 1, 1 if intel["ok"] else 0,
                             0 if intel["ok"] else 1)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:16px 0 20px'>
        <div style='font-size:2.8rem'>🏛️</div>
        <div style='font-family:Space Grotesk,sans-serif;font-weight:700;
             font-size:1.15rem;color:#a5b4fc;margin-top:4px'>ArchScale Intel</div>
        <div style='font-size:0.72rem;color:#334155;margin-top:2px'>
        Competitor Intelligence Platform</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    nav = st.radio(
        "Navigation",
        ["🎯 Find Company Leads", "💼 Executive Leads Directory", "📊 Dashboard", "🔍 Saved Companies", "🔬 Evidence", "⚙️ Bulk Scrape"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Quick metrics
    try:
        with db.get_connection(DB_PATH) as conn:
            m = db.get_summary_metrics(conn)
        st.markdown(f"""
        <div style='font-size:0.72rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px'>Saved Database</div>
        <div style='display:flex;flex-direction:column;gap:6px'>
            <div style='display:flex;justify-content:space-between;font-size:0.83rem'>
                <span style='color:#475569'>Companies</span>
                <span style='color:#a5b4fc;font-weight:600'>{m.get("total_companies",0)}</span>
            </div>
            <div style='display:flex;justify-content:space-between;font-size:0.83rem'>
                <span style='color:#fbbf24'>Needs review</span>
                <span style='color:#fbbf24;font-weight:600'>{m.get("needs_review",0)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.68rem;color:#1e293b;text-align:center;line-height:1.5'>"
        "Data sourced from public web pages only. "
        "robots.txt compliance enforced. No data is fabricated."
        "</div>", unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="arch-header">
    <h1>🏛️ ArchScale Intelligence</h1>
    <div class="subtitle">
        CEO-facing intelligence platform for Indian architecture & interior design firms —
        discover qualified executive leads with verified contacts, owner/founder titles, organisation sizes, and social footprints.
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: 🎯 Find Company Leads (Instant Target Company Lead & Sources Finder)
# ═══════════════════════════════════════════════════════════════════════════════
if nav == "🎯 Find Company Leads":
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown('<div class="input-card-title">🎯 Instant Company Lead & Sources Finder</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.88rem;color:#94a3b8;margin-bottom:14px'>"
        "Enter any target company name or website. The engine discovers its official online presence in real-time, "
        "crawls verified public web pages, extracts executive leads, and shows the <strong>exact sources it retrieved each data point from</strong>. "
        "<strong>Zero mockups. 100% verified live data.</strong>"
        "</div>",
        unsafe_allow_html=True,
    )

    # 1-click Quick Presets
    st.markdown("<div style='font-size:0.8rem;color:#cbd5e1;margin-bottom:8px'>⚡ <strong>Quick Presets:</strong> Click any company to instantly find leads & sources:</div>", unsafe_allow_html=True)
    p1, p2, p3, p4, p5, p6 = st.columns(6)
    with p1:
        if st.button("🏛️ Morphogenesis", use_container_width=True, key="btn_pre_morph"):
            st.session_state["target_company_search"] = "Morphogenesis"
            st.session_state["target_city_hint"] = "Delhi"
            st.session_state["trigger_auto_find"] = True
            st.rerun()
    with p2:
        if st.button("🏛️ Studio Lotus", use_container_width=True, key="btn_pre_lotus"):
            st.session_state["target_company_search"] = "Studio Lotus"
            st.session_state["target_city_hint"] = "Delhi"
            st.session_state["trigger_auto_find"] = True
            st.rerun()
    with p3:
        if st.button("🏛️ HCP Design", use_container_width=True, key="btn_pre_hcp"):
            st.session_state["target_company_search"] = "HCP Design"
            st.session_state["target_city_hint"] = "Ahmedabad"
            st.session_state["trigger_auto_find"] = True
            st.rerun()
    with p4:
        if st.button("🏛️ INI Design", use_container_width=True, key="btn_pre_ini"):
            st.session_state["target_company_search"] = "INI Design Studio"
            st.session_state["target_city_hint"] = "Ahmedabad"
            st.session_state["trigger_auto_find"] = True
            st.rerun()
    with p5:
        if st.button("🏛️ Modo Designs", use_container_width=True, key="btn_pre_modo"):
            st.session_state["target_company_search"] = "Modo Designs"
            st.session_state["target_city_hint"] = "Ahmedabad"
            st.session_state["trigger_auto_find"] = True
            st.rerun()
    with p6:
        if st.button("🏛️ Sanjay Puri", use_container_width=True, key="btn_pre_puri"):
            st.session_state["target_company_search"] = "Sanjay Puri Architects"
            st.session_state["target_city_hint"] = "Mumbai"
            st.session_state["trigger_auto_find"] = True
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    col_q, col_cat, col_city = st.columns([3, 1.4, 1.4])
    with col_q:
        target_query = st.text_input(
            "🏢 Target Company Name or Website",
            value=st.session_state.get("target_company_search", ""),
            placeholder="e.g. Morphogenesis, Studio Lotus, HCP Design, inidesignstudio.com, Modo Designs...",
            help="Type the company name or paste their website URL. No mocking — live web discovery and scraping will be executed.",
            key="input_target_company_box",
        )
    with col_cat:
        category = st.selectbox(
            "Industry Category",
            ["architecture", "interior", "other"],
            key="find_lead_category",
        )
    with col_city:
        city_hint = st.text_input(
            "Market City (Optional)",
            value=st.session_state.get("target_city_hint", ""),
            placeholder="e.g. Ahmedabad, Mumbai",
            key="find_lead_city_hint",
        )

    btn_col1, btn_col2, btn_col3 = st.columns([2.5, 1, 3.5])
    with btn_col1:
        find_btn = st.button("🚀 Find Leads & Sources", type="primary", use_container_width=True, key="btn_run_lead_find")
    with btn_col2:
        clear_btn = st.button("🗑️ Clear", use_container_width=True, key="btn_clear_lead_find")

    st.markdown('</div>', unsafe_allow_html=True)

    if clear_btn:
        st.session_state["current_lead"] = None
        st.session_state["target_company_search"] = ""
        st.session_state["target_city_hint"] = ""
        st.session_state["lead_finder_log"] = []
        if "trigger_auto_find" in st.session_state:
            del st.session_state["trigger_auto_find"]
        st.rerun()

    should_find = find_btn or st.session_state.get("trigger_auto_find", False)
    if should_find:
        if "trigger_auto_find" in st.session_state:
            del st.session_state["trigger_auto_find"]

        query_to_run = (target_query or "").strip()
        if not query_to_run:
            st.warning("⚠️ Please enter a target company name or website.")
        else:
            st.session_state["target_company_search"] = query_to_run
            progress = st.progress(0)
            log_box = st.empty()
            log_lines: list[str] = []

            def log_callback(msg: str):
                log_lines.append(msg)
                log_box.markdown(
                    f"<div style='background:rgba(0,0,0,0.4);border-radius:10px;padding:12px 16px;"
                    f"font-family:monospace;font-size:0.8rem;color:#94a3b8;max-height:170px;overflow-y:auto;border:1px solid rgba(99,102,241,0.2)'>"
                    + "<br>".join(log_lines[-10:]) +
                    "</div>", unsafe_allow_html=True
                )

            progress.progress(15)
            lead_result = find_and_extract_company_lead(
                target_input=query_to_run,
                db_path=DB_PATH,
                category=category,
                progress_callback=log_callback,
                market_city=city_hint,
            )
            progress.progress(100)
            st.session_state["current_lead"] = lead_result
            st.session_state["lead_finder_log"] = log_lines
            time.sleep(0.5)
            log_box.empty()
            st.rerun()

    # ── Display Found Lead & Detailed Sources ─────────────────────────────────
    lead = st.session_state.get("current_lead")
    if not lead:
        st.markdown("""
        <div style='text-align:center;padding:50px 20px;color:#334155'>
            <div style='font-size:3.5rem'>🎯</div>
            <div style='font-family:Space Grotesk,sans-serif;font-size:1.25rem;color:#94a3b8;margin-top:12px;font-weight:600'>
            Ready to find leads for any target company</div>
            <div style='font-size:0.88rem;color:#64748b;margin-top:8px;max-width:550px;margin-left:auto;margin-right:auto'>
            Enter a company name above or click one of the quick presets. Our live engine will crawl public pages, extract executive contacts, and show every source URL it retrieved from.
            </div>
        </div>
        """, unsafe_allow_html=True)
    elif not lead.get("ok"):
        st.error(f"❌ {lead.get('error', 'Could not retrieve leads for this company')}")
    else:
        domain = lead["domain"]
        org = lead["organisation"]
        website = lead["url"]
        owner = lead["owner_name"]
        owner_status = lead["owner_status"]
        desig = lead["designation"]
        emails_list = lead.get("email_list", [])
        phones_list = lead.get("mobile_list", [])
        city = lead.get("city", "Not found")
        org_size = lead.get("org_size", "Not found")
        org_size_basis = lead.get("org_size_basis", "not_found")
        res_source = lead.get("resolution", {}).get("source", "web_resolution")
        sources_summary = lead.get("sources_summary", [])
        field_sources = lead.get("field_sources", {})
        services = lead.get("services", [])
        projects = lead.get("projects", [])
        gallery = lead.get("gallery", [])
        socials = lead.get("social_links", {})

        # ─── Master Company Header ──────────────────────────────────────────
        st.markdown(f"""
        <div class="intel-card" style="border-color:rgba(99,102,241,0.4);background:rgba(99,102,241,0.06);margin-bottom:20px">
            <div class="intel-card-header">
                <div>
                    <div style="font-size:0.75rem;font-weight:700;color:#34d399;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">
                        ✓ Verified Lead Found & Sourced
                    </div>
                    <div class="company-name-big" style="font-size:1.6rem">{org}</div>
                    <div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                        <span class="company-domain-tag">🌐 {domain}</span>
                        <span class="city-badge">📍 {city}</span>
                        <span style="font-size:0.75rem;background:rgba(255,255,255,0.06);color:#94a3b8;padding:2px 8px;border-radius:6px">
                            Discovered via: {res_source.replace('_', ' ').title()}
                        </span>
                        <span style="font-size:0.75rem;background:rgba(16,185,129,0.1);color:#34d399;padding:2px 8px;border-radius:6px">
                            {len(lead.get('source_urls_list', []))} Pages Crawled
                        </span>
                    </div>
                </div>
                <a href="{website}" target="_blank"
                   style="background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.4);
                          color:#a5b4fc;padding:10px 18px;border-radius:10px;text-decoration:none;
                          font-size:0.85rem;font-weight:600;white-space:nowrap;display:inline-flex;align-items:center;gap:6px">
                   🌐 Visit Official Site ↗
                </a>
            </div>
            {f'<div style="font-size:0.88rem;color:#94a3b8;margin-top:10px;line-height:1.6">{lead.get("description", "")[:280]}...</div>' if lead.get("description") else ""}
        </div>
        """, unsafe_allow_html=True)

        # ─── Executive Lead Badges Grid ─────────────────────────────────────
        st.markdown("<div style='font-size:0.78rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px'>Executive Lead Profile</div>", unsafe_allow_html=True)
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.markdown(f"""
            <div class="source-card">
                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;font-weight:700">👤 Owner / Founder</div>
                <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin:4px 0">
                    {owner}
                    <span class="badge-{'review' if owner_status == 'Needs review' else ('extracted' if owner != 'Not found' else 'notfound')}">
                        {owner_status}
                    </span>
                </div>
                <div style="font-size:0.8rem;color:#94a3b8">💼 {desig}</div>
            </div>
            """, unsafe_allow_html=True)

        with m_col2:
            email_html = ", ".join(f'<a href="mailto:{e}" style="color:#818cf8;text-decoration:none;font-weight:600">{e}</a>' for e in emails_list) if emails_list else '<span class="badge-notfound">Not found</span>'
            phone_html = ", ".join(f'<a href="tel:{p}" style="color:#34d399;text-decoration:none;font-weight:600">{p}</a>' for p in phones_list) if phones_list else '<span class="badge-notfound">Not found</span>'
            st.markdown(f"""
            <div class="source-card">
                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;font-weight:700">✉️ Business Email</div>
                <div style="font-size:0.88rem;margin:4px 0 8px">{email_html}</div>
                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;font-weight:700">📞 Phone / Mobile</div>
                <div style="font-size:0.88rem;margin-top:2px">{phone_html}</div>
            </div>
            """, unsafe_allow_html=True)

        with m_col3:
            st.markdown(f"""
            <div class="source-card">
                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;font-weight:700">📍 Location / City</div>
                <div style="font-size:1.05rem;font-weight:600;color:#fbbf24;margin:4px 0">{city}</div>
                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;font-weight:700;margin-top:6px">👥 Organisation Size</div>
                <div style="font-size:0.88rem;color:#cbd5e1;margin-top:2px">
                    <strong>{org_size}</strong>
                    <span class="badge-basis">{org_size_basis}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Export & DB save status ──────────────────────────────────────────
        exp_col1, exp_col2, exp_col3 = st.columns([1.5, 1.5, 3])
        with exp_col1:
            csv_lead_data = export_leads_csv([lead])
            st.download_button(
                "⬇️ Download Lead CSV",
                data=csv_lead_data,
                file_name=f"{domain}_lead.csv",
                mime="text/csv",
                use_container_width=True,
                key="btn_dl_lead_csv",
            )
        with exp_col2:
            excel_lead_data = export_leads_excel([lead])
            st.download_button(
                "⬇️ Download Lead Excel",
                data=excel_lead_data,
                file_name=f"{domain}_lead.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_dl_lead_excel",
            )
        with exp_col3:
            st.markdown(f"<div style='font-size:0.8rem;color:#34d399;margin-top:8px'>💾 <em>Lead automatically persisted to database (Company ID #{lead.get('company_id', 'N/A')}).</em></div>", unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # ═════════════════════════════════════════════════════════════════════
        # 📍 SOURCES IT HAS RETRIEVED FROM (Core User Requirement)
        # ═════════════════════════════════════════════════════════════════════
        st.markdown(f"""
        <div style="margin:20px 0 12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.25rem;font-weight:700;color:#a5b4fc;display:flex;align-items:center;gap:8px">
                📍 Sources It Has Retrieved From
            </div>
            <div style="font-size:0.8rem;color:#94a3b8">
                Strict Verifiable Evidence: <strong>{len(lead.get('source_urls_list', []))}</strong> public URLs crawled
            </div>
        </div>
        """, unsafe_allow_html=True)

        field_labels = [
            ("owner_name", "👤 Owner / Founder", lead.get("owner_name")),
            ("designation", "💼 Designation", lead.get("designation")),
            ("email", "✉️ Business Email", lead.get("email")),
            ("phone", "📞 Phone / Mobile", lead.get("mobile")),
            ("city", "📍 City / Location", lead.get("city")),
            ("org_size", "👥 Organisation Size", lead.get("org_size")),
            ("website", "🌐 Official Website", lead.get("url")),
            ("linkedin", "💼 LinkedIn Profile", socials.get("linkedin")),
            ("instagram", "📸 Instagram Profile", socials.get("instagram")),
            ("facebook", "👍 Facebook Page", socials.get("facebook")),
        ]

        for f_key, f_label, f_current_val in field_labels:
            candidates_for_field = field_sources.get(f_key, [])
            if not candidates_for_field:
                continue

            primary_c = candidates_for_field[0]
            src_url = primary_c.get("source_url") or website
            method = primary_c.get("method", "html_content")
            snippet = primary_c.get("supporting_text") or "Direct extraction from page structure"
            status = primary_c.get("verification_status", "Extracted")

            st.markdown(f"""
            <div class="source-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px">
                    <div>
                        <span style="font-size:0.82rem;font-weight:700;color:#e2e8f0">{f_label}:</span>
                        <span style="font-size:0.9rem;font-weight:600;color:#a5b4fc;margin-left:6px">{primary_c.get('value')}</span>
                    </div>
                    <div>
                        <span class="badge-{'review' if status == 'Needs review' else ('extracted' if status == 'Extracted' else 'notfound')}">
                            {status}
                        </span>
                        <span style="font-size:0.72rem;background:rgba(255,255,255,0.06);color:#94a3b8;padding:2px 7px;border-radius:4px;margin-left:4px">
                            Method: {method}
                        </span>
                    </div>
                </div>
                <div style="margin-top:8px">
                    <span style="font-size:0.75rem;color:#64748b;font-weight:600">RETRIEVED FROM SOURCE:</span><br>
                    <a href="{src_url}" target="_blank" class="source-link-badge" style="margin-top:3px">
                        🔗 {src_url} ↗
                    </a>
                </div>
                <div class="quote-snippet">
                    "{snippet}"
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Expandable Crawl Matrix ──────────────────────────────────────────
        with st.expander(f"🔍 Complete Crawl Matrix ({len(sources_summary)} pages crawled with status & fields)", expanded=False):
            if sources_summary:
                crawl_table_data = []
                for s in sources_summary:
                    crawl_table_data.append({
                        "Source URL": s["url"],
                        "Page Role": s["page_role"].title(),
                        "Status": f"HTTP {s['status_code']}",
                        "Items Extracted": s["candidates_count"],
                        "Discovered Fields": ", ".join(s["fields"][:6]) + ("..." if len(s["fields"]) > 6 else ""),
                    })
                st.dataframe(pd.DataFrame(crawl_table_data), use_container_width=True, hide_index=True)

        # ── Deep Dive Offerings & Portfolio Tabs ─────────────────────────────
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        tab_svc, tab_proj, tab_soc, tab_gal = st.tabs(["🛠 Services & Offerings", "🏗 Portfolio Projects", "🔗 Social Media Channels", "🖼 Visual Gallery"])

        with tab_svc:
            if services:
                st.markdown('<div class="intel-section-label">Services / Specialities</div>', unsafe_allow_html=True)
                st.markdown("".join(f'<span class="service-tag">{s}</span>' for s in services), unsafe_allow_html=True)
            else:
                st.caption("No specific service taxonomies identified on public pages.")

        with tab_proj:
            if projects:
                st.markdown('<div class="intel-section-label">Projects & Portfolio Mentions</div>', unsafe_allow_html=True)
                st.markdown("".join(f'<span class="project-tag">📐 {p}</span>' for p in projects), unsafe_allow_html=True)
            else:
                st.caption("No portfolio project names found in public page markup.")

        with tab_soc:
            if socials:
                links_html = ""
                for platform, link in socials.items():
                    icon = _social_icon(platform)
                    links_html += f'<a href="{link}" target="_blank" class="social-link">{icon} {platform.title()} ↗</a>'
                st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:6px">{links_html}</div>', unsafe_allow_html=True)
            else:
                st.caption("No public social channels detected.")

        with tab_gal:
            if gallery:
                cols = st.columns(min(4, len(gallery)))
                for img_idx, img_url in enumerate(gallery[:12]):
                    with cols[img_idx % 4]:
                        try:
                            st.image(img_url, use_container_width=True)
                        except Exception:
                            st.markdown(f'<a href="{img_url}" target="_blank">Image {img_idx+1}</a>', unsafe_allow_html=True)
            else:
                st.caption("No gallery images found.")

    st.markdown("<hr style='margin:28px 0'>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: 💼 Executive Leads Directory
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "💼 Executive Leads Directory":
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown('<div class="input-card-title">💼 Executive Leads Directory</div>', unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.85rem;color:#94a3b8;margin-bottom:16px'>"
        "Single executive table of discovered firms with verified business contacts, senior leadership, and public social footprints. "
        "Strict traceability with zero fabricated data."
        "</div>", unsafe_allow_html=True,
    )

    all_leads = get_leads(DB_PATH)

    # ── Completeness Summary ─────────────────────────────────────────────────
    total_leads = len(all_leads)
    if total_leads > 0:
        email_cnt = sum(1 for l in all_leads if l["email"] != "Not found")
        mobile_cnt = sum(1 for l in all_leads if l["mobile"] != "Not found")
        owner_cnt = sum(1 for l in all_leads if l["owner_name"] != "Not found")
        city_cnt = sum(1 for l in all_leads if l["city"] != "Not found")
        size_cnt = sum(1 for l in all_leads if l["org_size"] != "Not found")

        st.markdown(f"""
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">
            <div class="metric-pill">📋 Total Leads: <strong>{total_leads}</strong></div>
            <div class="metric-pill">✉️ Email: <strong>{email_cnt}/{total_leads}</strong> ({int(email_cnt/total_leads*100)}%)</div>
            <div class="metric-pill">📞 Mobile: <strong>{mobile_cnt}/{total_leads}</strong> ({int(mobile_cnt/total_leads*100)}%)</div>
            <div class="metric-pill">👤 Owner: <strong>{owner_cnt}/{total_leads}</strong> ({int(owner_cnt/total_leads*100)}%)</div>
            <div class="metric-pill">📍 City: <strong>{city_cnt}/{total_leads}</strong> ({int(city_cnt/total_leads*100)}%)</div>
            <div class="metric-pill">👥 Org Size: <strong>{size_cnt}/{total_leads}</strong> ({int(size_cnt/total_leads*100)}%)</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Filter & Export Bar ──────────────────────────────────────────────────
    f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([2.4, 1.4, 1.4, 1, 1])
    with f_col1:
        leads_kw = st.text_input("🔍 Search Leads", placeholder="Search owner, firm, designation, city...", key="leads_search_kw")
    with f_col2:
        cities = ["All"] + sorted(list({l["city"] for l in all_leads if l["city"] != "Not found"}))
        sel_city = st.selectbox("📍 City Filter", cities, key="leads_city_sel")
    with f_col3:
        sizes = ["All", "1-10", "11-50", "51-200", "200+", "Not found"]
        sel_size = st.selectbox("👥 Org Size Filter", sizes, key="leads_size_sel")

    # Filtered dataset
    filtered_leads = get_leads(
        DB_PATH,
        search=leads_kw,
        city="" if sel_city == "All" else sel_city,
        org_size="" if sel_size == "All" else sel_size,
    )

    with f_col4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        csv_data = export_leads_csv(filtered_leads)
        st.download_button(
            "⬇️ Export CSV",
            data=csv_data,
            file_name=f"archscale_leads_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with f_col5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        excel_data = export_leads_excel(filtered_leads)
        st.download_button(
            "⬇️ Export Excel",
            data=excel_data,
            file_name=f"archscale_leads_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Leads Directory Table ────────────────────────────────────────────────
    if not filtered_leads:
        st.info("No leads found matching the filters. Enter competitor URLs in 'Competitor Analyser' or run a 'Bulk Scrape' to discover companies.")
    else:
        st.markdown(f"<div style='font-size:0.85rem;color:#64748b;margin:12px 0 16px'>Showing <strong>{len(filtered_leads)}</strong> lead record(s):</div>", unsafe_allow_html=True)

        for l in filtered_leads:
            owner_val   = l.get("owner_name", "Not found")
            org_val     = l.get("organisation", "")
            desig_val   = l.get("designation", "Not found")
            size_val    = l.get("org_size", "Not found")
            size_basis  = l.get("org_size_basis", "not_found")
            mobile_val  = l.get("mobile", "Not found")
            email_val   = l.get("email", "Not found")
            city_val    = l.get("city", "Not found")
            city_stat   = l.get("city_status", "Not found")
            source_list = l.get("source_urls_list", [])
            socials     = l.get("social_links", {})

            # Owner badge & formatting
            if owner_val != "Not found":
                owner_html = f"<div style='font-weight:600;color:#f1f5f9;font-size:0.95rem'>{owner_val} <span class='badge-review'>⚠️ needs review</span></div>"
                if desig_val != "Not found":
                    owner_html += f"<div style='font-size:0.8rem;color:#94a3b8;margin-top:2px'>💼 {desig_val}</div>"
            else:
                owner_html = "<span class='badge-notfound'>Not found</span>"

            # Mobile badge & formatting
            if mobile_val != "Not found":
                m_links = " ".join([f"<a href='tel:{p.strip()}' style='color:#38bdf8;text-decoration:none;margin-right:6px'>📞 {p.strip()}</a>" for p in mobile_val.split(",")])
                mobile_html = f"{m_links} <span class='badge-extracted'>✅ extracted</span>"
            else:
                mobile_html = "<span class='badge-notfound'>Not found</span>"

            # Email badge & formatting
            if email_val != "Not found":
                e_links = " ".join([f"<a href='mailto:{em.strip()}' style='color:#818cf8;text-decoration:none;margin-right:6px'>✉️ {em.strip()}</a>" for em in email_val.split(",")])
                email_html = f"{e_links} <span class='badge-extracted'>✅ extracted</span>"
            else:
                email_html = "<span class='badge-notfound'>Not found</span>"

            # City badge & formatting
            if city_val != "Not found":
                if city_stat == "Needs review" or "inferred" in city_stat.lower():
                    city_html = f"📍 {city_val} <span class='badge-review'>⚠️ inferred</span>"
                else:
                    city_html = f"📍 {city_val} <span class='badge-extracted'>✅ extracted</span>"
            else:
                city_html = "<span class='badge-notfound'>Not found</span>"

            # Org size
            if size_val != "Not found":
                size_html = f"👥 <strong>{size_val}</strong> <span class='badge-basis'>{size_basis}</span>"
            else:
                size_html = "<span class='badge-notfound'>Not found</span>"

            # Source URLs (clickable)
            src_links = " ".join([f"<a href='{u}' target='_blank' style='color:#a5b4fc;text-decoration:none;font-size:0.75rem;margin-right:6px;background:rgba(99,102,241,0.1);padding:3px 8px;border-radius:6px;border:1px solid rgba(99,102,241,0.2)'>🌐 {normalise_domain(u)} ↗</a>" for u in source_list[:3]])

            # Social channels (clickable icons)
            if socials:
                soc_links = " ".join([f"<a href='{u}' target='_blank' style='text-decoration:none;margin-right:8px;font-size:0.95rem' title='{plat.title()}'>{_social_icon(plat)}</a>" for plat, u in socials.items()])
            else:
                soc_links = "<span class='badge-notfound'>None</span>"

            st.markdown(f"""
            <div class="lead-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
                    <div style="flex:1.2;min-width:230px">
                        <div style="font-size:1.1rem;font-weight:700;color:#e2e8f0">{org_val}</div>
                        <div style="margin-top:6px">{owner_html}</div>
                    </div>
                    <div style="flex:1.4;min-width:270px;display:flex;flex-direction:column;gap:5px">
                        <div>{email_html}</div>
                        <div>{mobile_html}</div>
                    </div>
                    <div style="flex:1;min-width:180px;display:flex;flex-direction:column;gap:5px">
                        <div>{city_html}</div>
                        <div>{size_html}</div>
                    </div>
                    <div style="flex:1.2;min-width:180px;text-align:right">
                        <div style="margin-bottom:6px">{soc_links}</div>
                        <div>{src_links}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Competitor Analyser
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🎯 Competitor Analyser":

    # ── Input Panel ──────────────────────────────────────────────────────────
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown('<div class="input-card-title">🎯 Analyse a Competitor</div>', unsafe_allow_html=True)

    # 1-click presets
    st.markdown("<div style='font-size:0.8rem;color:#94a3b8;margin-bottom:8px'>⚡ <strong>Quick Presets:</strong> Click to load competitor websites:</div>", unsafe_allow_html=True)
    p_col1, p_col2, p_col3, p_col4 = st.columns([1, 1, 1, 1])
    with p_col1:
        if st.button("📍 Ahmedabad Firms", use_container_width=True, help="Load Ahmedabad firms (HCP, INI Design Studio)"):
            st.session_state["intel_urls_input"] = "https://www.hcp.co.in\nhttps://www.inidesignstudio.com"
            st.session_state["intel_city"] = "Ahmedabad"
            st.rerun()
    with p_col2:
        if st.button("📍 Mumbai Firms", use_container_width=True, help="Load Mumbai firms (Edifice, Sanjay Puri)"):
            st.session_state["intel_urls_input"] = "https://www.edifice.co.in\nhttps://www.sanjaypuriarchitects.com"
            st.session_state["intel_city"] = "Mumbai"
            st.rerun()
    with p_col3:
        if st.button("📍 Delhi NCR Firms", use_container_width=True, help="Load Delhi firms (Morphogenesis, Studio Lotus)"):
            st.session_state["intel_urls_input"] = "https://www.morphogenesis.org\nhttps://studiolotus.in"
            st.session_state["intel_city"] = "Delhi"
            st.rerun()
    with p_col4:
        if st.button("📍 Interior Studio", use_container_width=True, help="Load Interior Design firms"):
            st.session_state["intel_urls_input"] = "https://www.thecrossboundaries.com\nhttps://www.studiolagom.in"
            st.session_state["intel_city"] = "Ahmedabad"
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    col_url, col_city, col_cat = st.columns([3, 1.5, 1.5])
    with col_url:
        raw_urls = st.text_area(
            "Competitor Website URLs",
            placeholder="https://www.competitor1.com\nhttps://www.competitor2.com\n(one URL per line)",
            height=100,
            help="Paste one or more competitor website URLs. The scraper will extract their services, portfolio, social links, and contact info.",
            key="intel_urls_input",
        )
    with col_city:
        city_hint = st.text_input(
            "Your Market City",
            placeholder="e.g. Ahmedabad",
            key="intel_city",
            help="Used to filter companies in your market. Not mandatory for scraping.",
        )
        category = st.selectbox(
            "Company Type",
            ["architecture", "interior", "other"],
            key="intel_category",
        )
    with col_cat:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        analyse_btn = st.button("🚀 Analyse Now", type="primary", use_container_width=True)
        clear_btn   = st.button("🗑️ Clear Results", use_container_width=True)
        save_btn    = st.button("💾 Save to Database", use_container_width=True,
                                help="Persist current results to the local database for future reference.")

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Clear ─────────────────────────────────────────────────────────────────
    if clear_btn:
        st.session_state.intel_results = []
        st.session_state.scrape_log = []
        st.rerun()

    # ── Save to DB ────────────────────────────────────────────────────────────
    if save_btn and st.session_state.intel_results:
        saved = 0
        for intel in st.session_state.intel_results:
            if intel.get("ok"):
                try:
                    _save_intel_to_db(intel)
                    saved += 1
                except Exception as exc:
                    st.warning(f"Could not save {intel['domain']}: {exc}")
        st.success(f"✅ Saved {saved} company/companies to the local database.")

    # ── Analyse ───────────────────────────────────────────────────────────────
    if analyse_btn:
        urls_raw = [u.strip() for u in (raw_urls or "").splitlines() if u.strip()]
        if not urls_raw:
            st.warning("Please enter at least one URL.")
        else:
            # Validate URLs first
            valid_urls = []
            for u in urls_raw:
                try:
                    clean = validate_url(u, resolve_ip=False)
                    valid_urls.append(clean)
                except URLValidationError as e:
                    st.error(f"❌ Invalid URL `{u}`: {e}")

            if valid_urls:
                st.session_state.intel_results = []
                progress = st.progress(0)
                log_box  = st.empty()
                log_lines: list[str] = []

                def log(msg: str):
                    log_lines.append(msg)
                    log_box.markdown(
                        f"<div style='background:rgba(0,0,0,0.3);border-radius:8px;padding:12px;"
                        f"font-family:monospace;font-size:0.78rem;color:#64748b;max-height:160px;overflow-y:auto'>"
                        + "<br>".join(log_lines[-10:]) +
                        "</div>", unsafe_allow_html=True
                    )

                for i, url in enumerate(valid_urls):
                    log(f"🔍 [{i+1}/{len(valid_urls)}] Scraping {url} …")
                    progress.progress((i) / len(valid_urls))

                    try:
                        intel = _scrape_single_url(url, category)
                        intel["market_city"] = city_hint
                        st.session_state.intel_results.append(intel)
                        pages = len(intel.get("pages_scraped", []))
                        svc_count = len(intel.get("services", []))
                        social_count = len(intel.get("social", {}))
                        if intel["ok"]:
                            log(f"   ✅ {intel['org_name']} — {pages} page(s), {svc_count} service(s), {social_count} social link(s)")
                        else:
                            log(f"   ❌ {url} — {intel.get('error','failed')}")
                    except Exception as exc:
                        log(f"   ❌ Exception on {url}: {exc}")
                        logger.exception("Intel scrape failed for %s", url)

                progress.progress(100)
                st.session_state.scrape_log = log_lines
                log("✅ Analysis complete!")
                time.sleep(0.5)
                log_box.empty()
                st.rerun()

    # ── Results ───────────────────────────────────────────────────────────────
    results = st.session_state.intel_results
    if not results:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px;color:#1e293b'>
            <div style='font-size:4rem'>🎯</div>
            <div style='font-family:Space Grotesk,sans-serif;font-size:1.2rem;color:#334155;margin-top:12px;font-weight:600'>
            Enter a competitor URL above to begin analysis</div>
            <div style='font-size:0.88rem;color:#1e293b;margin-top:8px'>
            The system will extract their services, portfolio, social links, team information, and contact details from publicly available pages.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Summary bar
        ok_count = sum(1 for r in results if r["ok"])
        city_filter_active = bool(city_hint)
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">'
            f'<div class="metric-pill">✅ <strong>{ok_count}</strong> analysed</div>'
            f'<div class="metric-pill">📋 <strong>{len(results)}</strong> requested</div>'
            f'{"<div class=\"metric-pill\">📍 Market: <strong>" + city_hint + "</strong></div>" if city_filter_active else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

        for idx, intel in enumerate(results):
            domain = intel["domain"]
            org = intel.get("org_name") or domain
            city = intel.get("city") or intel.get("market_city") or "—"
            website = intel.get("website") or intel.get("final_url") or intel.get("url")
            desc = intel.get("description") or ""
            phones = intel.get("phone", [])
            emails = intel.get("email", [])
            services = intel.get("services", [])
            projects = intel.get("projects", [])
            gallery  = intel.get("gallery", [])
            awards   = intel.get("awards", [])
            social   = intel.get("social", {})
            pages_scraped = intel.get("pages_scraped", [])

            if not intel.get("ok"):
                st.markdown(f"""
                <div class="intel-card" style="border-color:rgba(239,68,68,0.25)">
                    <div class="intel-card-header">
                        <div>
                            <div class="company-name-big" style="color:#f87171">❌ {domain}</div>
                            <div style="font-size:0.82rem;color:#ef4444;margin-top:4px">{intel.get("error","Fetch failed")}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                continue

            # ─── Company Card ─────────────────────────────────────────────
            with st.container():
                st.markdown(f"""
                <div class="intel-card" id="company-{idx}">
                    <div class="intel-card-header">
                        <div>
                            <div class="company-name-big">{org}</div>
                            <div style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                                <span class="company-domain-tag">{domain}</span>
                                {"<span class='city-badge'>📍 " + city + "</span>" if city != "—" else ""}
                                <span style="font-size:0.75rem;color:#334155">{len(pages_scraped)} page(s) scanned</span>
                            </div>
                        </div>
                        <a href="{website}" target="_blank"
                           style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);
                                  color:#a5b4fc;padding:8px 16px;border-radius:8px;text-decoration:none;
                                  font-size:0.82rem;font-weight:600;white-space:nowrap">
                           🌐 Visit Website ↗
                        </a>
                    </div>
                    {f'<div style="font-size:0.87rem;color:#64748b;margin-bottom:8px;line-height:1.6">{desc[:300]}</div>' if desc else ""}
                </div>
                """, unsafe_allow_html=True)

                # Tabs for each intel category
                tabs = st.tabs(["🛠 Services & Offerings", "🏗 Portfolio & Projects",
                                 "🔗 Social Presence", "📞 Contact Details",
                                 "🖼 Visual Gallery", "🏆 Awards & Recognition"])

                # ── Services ────────────────────────────────────────────────
                with tabs[0]:
                    if services:
                        tags = "".join(f'<span class="service-tag">{s}</span>' for s in services)
                        st.markdown(
                            f'<div class="intel-section-label">Services / Offerings ({len(services)} found)</div>'
                            f'<div>{tags}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown('<div class="not-found">No services found on publicly accessible pages.</div>', unsafe_allow_html=True)

                # ── Projects ────────────────────────────────────────────────
                with tabs[1]:
                    if projects:
                        tags = "".join(f'<span class="project-tag">📐 {p}</span>' for p in projects)
                        st.markdown(
                            f'<div class="intel-section-label">Portfolio / Projects ({len(projects)} found)</div>'
                            f'<div>{tags}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown('<div class="not-found">No portfolio entries found. The company may use JavaScript to render their portfolio.</div>', unsafe_allow_html=True)

                # ── Social ──────────────────────────────────────────────────
                with tabs[2]:
                    if social:
                        st.markdown('<div class="intel-section-label">Social Media Profiles</div>', unsafe_allow_html=True)
                        links_html = ""
                        for platform, link in social.items():
                            icon = _social_icon(platform)
                            links_html += f'<a href="{link}" target="_blank" class="social-link">{icon} {platform.title()}</a>'
                        st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px">{links_html}</div>', unsafe_allow_html=True)
                        st.markdown(
                            "<div style='font-size:0.75rem;color:#334155;margin-top:12px'>⚠️ Social profile URLs extracted from website. "
                            "Actual post content requires platform API access.</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown('<div class="not-found">No social media links found on public pages.</div>', unsafe_allow_html=True)

                # ── Contact ──────────────────────────────────────────────────
                with tabs[3]:
                    has_contact = phones or emails
                    if phones:
                        st.markdown('<div class="intel-section-label">Phone Numbers</div>', unsafe_allow_html=True)
                        for ph in phones:
                            st.markdown(f'<div class="contact-item">📞 <a href="tel:{ph}">{ph}</a></div>', unsafe_allow_html=True)
                    if emails:
                        st.markdown('<div class="intel-section-label">Email Addresses</div>', unsafe_allow_html=True)
                        for em in emails:
                            st.markdown(f'<div class="contact-item">✉️ <a href="mailto:{em}">{em}</a></div>', unsafe_allow_html=True)
                    if not has_contact:
                        st.markdown('<div class="not-found">No public contact details found.</div>', unsafe_allow_html=True)
                    st.markdown(
                        "<div style='font-size:0.73rem;color:#1e293b;margin-top:10px'>"
                        "Only publicly listed business contact details are shown.</div>",
                        unsafe_allow_html=True,
                    )

                # ── Gallery ──────────────────────────────────────────────────
                with tabs[4]:
                    if gallery:
                        st.markdown(f'<div class="intel-section-label">Portfolio Images ({len(gallery)} found)</div>', unsafe_allow_html=True)
                        # Display as a Streamlit columns grid
                        cols = st.columns(min(4, len(gallery)))
                        for img_idx, img_url in enumerate(gallery[:12]):
                            with cols[img_idx % 4]:
                                try:
                                    st.image(img_url, use_container_width=True)
                                except Exception:
                                    st.markdown(f'<a href="{img_url}" target="_blank" style="color:#6366f1;font-size:0.75rem">Image {img_idx+1}</a>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="not-found">No portfolio images found.</div>', unsafe_allow_html=True)

                # ── Awards ──────────────────────────────────────────────────
                with tabs[5]:
                    if awards:
                        for aw in awards:
                            st.markdown(f'<div style="font-size:0.85rem;color:#fbbf24;margin:6px 0">🏆 {aw}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="not-found">No awards or recognitions found on public pages.</div>', unsafe_allow_html=True)

                st.markdown('<hr style="margin:16px 0 24px">', unsafe_allow_html=True)

    # ── Competitive comparison (when multiple results) ─────────────────────
    ok_results = [r for r in results if r.get("ok")]
    if len(ok_results) > 1:
        st.markdown("### 📊 Competitive Comparison")
        comp_data = []
        for r in ok_results:
            comp_data.append({
                "Company": r.get("org_name") or r["domain"],
                "City": r.get("city") or "—",
                "Services Found": len(r.get("services", [])),
                "Projects Found": len(r.get("projects", [])),
                "Social Channels": len(r.get("social", {})),
                "Images Found": len(r.get("gallery", [])),
                "Has Email": "✅" if r.get("email") else "❌",
                "Has Phone": "✅" if r.get("phone") else "❌",
                "Pages Scanned": len(r.get("pages_scraped", [])),
                "Website": r.get("website") or "—",
            })
        df_comp = pd.DataFrame(comp_data)
        st.dataframe(df_comp, use_container_width=True, height=200)

        # Export comparison
        csv_io = __import__("io").StringIO()
        df_comp.to_csv(csv_io, index=False)
        st.download_button(
            "⬇️ Export Comparison CSV",
            data=csv_io.getvalue(),
            file_name=f"archscale_comparison_{datetime.date.today()}.csv",
            mime="text/csv",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "📊 Dashboard":
    try:
        with db.get_connection(DB_PATH) as conn:
            metrics = db.get_summary_metrics(conn)
    except Exception:
        metrics = {}

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("🏢 Companies", metrics.get("total_companies", 0))
    with c2: st.metric("📋 Evidence Rows", metrics.get("total_evidence", 0))
    with c3: st.metric("🟡 Needs Review", metrics.get("needs_review", 0))
    with c4: st.metric("⬜ Not Found", metrics.get("not_found", 0))
    with c5:
        last = metrics.get("last_run")
        st.metric("🔄 Last Run", last["status"].title() if last else "Never")

    st.markdown("---")
    col_l, col_r = st.columns([2, 1])

    with col_l:
        st.markdown("#### Recently Saved Companies")
        try:
            with db.get_connection(DB_PATH) as conn:
                companies = db.list_companies(conn)
        except Exception:
            companies = []

        if not companies:
            st.info("No companies saved yet. Use **🎯 Competitor Analyser** and click **💾 Save to Database**.")
        else:
            for comp in list(companies)[:8]:
                org   = comp["org_name"] or comp["domain_key"]
                city  = comp["city"] or "—"
                cat   = "🏗️ Arch" if comp["category"] == "architecture" else "🛋️ Interior"
                st.markdown(f"""
                <div class="intel-card" style="padding:16px 20px">
                    <div class="company-name-big" style="font-size:1rem">{org}</div>
                    <div style="font-size:0.8rem;color:#475569;margin-top:4px">
                        <span class="company-domain-tag">{comp["domain_key"]}</span>
                        &nbsp;{cat}&nbsp;·&nbsp;📍 {city}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with col_r:
        st.markdown("#### Data Quality")
        try:
            with db.get_connection(DB_PATH) as conn:
                sc = conn.execute(
                    "SELECT verification_status, COUNT(*) c FROM evidence GROUP BY verification_status"
                ).fetchall()
            if sc:
                df_q = pd.DataFrame([dict(r) for r in sc]).set_index("verification_status")
                st.bar_chart(df_q["c"])
        except Exception:
            st.info("Run a scrape to see quality metrics.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Saved Companies
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🔍 Saved Companies":
    st.markdown("#### Saved Company Intelligence")

    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
    with fc1: search   = st.text_input("Search", placeholder="Company, owner, email…", key="search_saved")
    with fc2: cat_f    = st.selectbox("Category", ["", "architecture", "interior", "other"], key="cat_saved")
    with fc3: city_f   = st.text_input("City", placeholder="e.g. Ahmedabad", key="city_saved")
    with fc4: status_f = st.selectbox("Status", ["", "Extracted", "Source checked", "Cross-verified", "Not found", "Needs review"], key="status_saved")

    try:
        with db.get_connection(DB_PATH) as conn:
            companies = db.list_companies(conn, search=search, category=cat_f, city=city_f, status=status_f)
    except Exception as exc:
        st.error(f"DB error: {exc}")
        companies = []

    if not companies:
        st.info("No companies match the filters, or none saved yet.")
    else:
        st.caption(f"{len(companies)} company/companies")
        rows = [{
            "Organisation": c["org_name"] or "—", "Domain": c["domain_key"],
            "Category": c["category"].title(), "City": c["city"] or "—",
            "Email": c["email"] or "—", "Phone": c["phone"] or "—",
            "Website": c["website"] or "—", "LinkedIn": c["linkedin"] or "—",
            "Last Scraped": (c["last_scraped_at"] or "")[:10],
            "⚠ Review": c["needs_review_count"] or 0,
        } for c in companies]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=400)

        # Export
        if st.button("⬇️ Export to CSV"):
            csv_data = export_csv(DB_PATH, search=search, category=cat_f, city=city_f, status=status_f)
            if csv_data:
                st.download_button("📥 Download CSV", data=csv_data,
                                   file_name="archscale_saved.csv", mime="text/csv")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Evidence Inspector
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "🔬 Evidence":
    st.markdown("#### Field-Level Evidence Inspector")
    st.caption("Every value has a traceable source URL and extraction timestamp.")

    try:
        with db.get_connection(DB_PATH) as conn:
            companies = db.list_companies(conn)
    except Exception:
        companies = []

    if not companies:
        st.info("No companies saved. Run the Competitor Analyser and save results first.")
    else:
        options = [f"{c['org_name'] or c['domain_key']} ({c['domain_key']})" for c in companies]
        cmap = {f"{c['org_name'] or c['domain_key']} ({c['domain_key']})": c for c in companies}
        sel = st.selectbox("Company", ["— select —"] + options)

        if sel and sel != "— select —":
            comp = cmap[sel]
            try:
                with db.get_connection(DB_PATH) as conn:
                    evidence = db.get_evidence_for_company(conn, comp["id"])
            except Exception as exc:
                st.error(str(exc))
                evidence = []

            fields: dict[str, list] = {}
            for ev in evidence:
                fields.setdefault(ev["field_name"], []).append(ev)

            for field_name, rows in fields.items():
                with st.expander(f"**{field_name}** ({len(rows)} candidate(s))"):
                    for ev in rows:
                        status = ev["verification_status"]
                        val    = ev["extracted_value"] or "*Not found*"
                        src    = ev["source_url"]
                        ts     = (ev["extracted_at"] or "")[:19].replace("T", " ")
                        st.markdown(
                            f"**Value:** `{val}`  \n"
                            f"**Source:** [{src[:70]}]({src})  \n"
                            f"**Method:** {ev['extraction_method'] or '—'}  \n"
                            f"**Status:** `{status}`  \n"
                            f"**Extracted:** {ts}",
                        )
                        if ev["supporting_text"]:
                            with st.expander("Supporting text"):
                                st.code(ev["supporting_text"][:800])

                        new_status = st.selectbox(
                            "Update status",
                            ["Extracted","Source checked","Cross-verified","Not found","Needs review"],
                            index=["Extracted","Source checked","Cross-verified","Not found","Needs review"].index(status)
                            if status in ["Extracted","Source checked","Cross-verified","Not found","Needs review"] else 0,
                            key=f"ev_status_{ev['id']}",
                        )
                        note = st.text_input("Note", key=f"ev_note_{ev['id']}")
                        if st.button("Save", key=f"ev_save_{ev['id']}"):
                            try:
                                with db.get_connection(DB_PATH) as conn:
                                    db.update_evidence_status(conn, ev["id"], new_status, note or None, _now())
                                st.success("Saved")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                        st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Bulk Scrape (seed CSV based)
# ═══════════════════════════════════════════════════════════════════════════════
elif nav == "⚙️ Bulk Scrape":
    st.markdown("#### Bulk Scrape from Approved URL List")
    st.caption("Scrape multiple companies from `data/seed_urls.csv` and save all results to the database.")

    col_s, col_i = st.columns([2, 1])
    with col_s:
        st.markdown("**Current Seed List** (`data/seed_urls.csv`)")
        if SEED_CSV.exists():
            try:
                df_seed = pd.read_csv(SEED_CSV)
                st.dataframe(df_seed, use_container_width=True, height=250)
                st.caption(f"{len(df_seed)} URL(s)")
            except Exception as exc:
                st.error(str(exc))
        else:
            st.warning("seed_urls.csv not found.")

    with col_i:
        st.markdown("**Upload additional URLs**")
        upl = st.file_uploader("CSV (url, category, notes)", type=["csv"])
        if upl:
            try:
                new_df = pd.read_csv(upl)
                if "url" not in new_df.columns:
                    st.error("CSV must have a 'url' column.")
                else:
                    existing = pd.read_csv(SEED_CSV) if SEED_CSV.exists() else pd.DataFrame(columns=["url","category","notes"])
                    merged = pd.concat([existing, new_df]).drop_duplicates(subset=["url"])
                    merged.to_csv(SEED_CSV, index=False)
                    st.success(f"Merged. {len(merged)} total URL(s).")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("---")
    if st.button("🚀 Start Bulk Scrape", type="primary"):
        log_box = st.empty()
        log_lines: list[str] = []

        def log(msg):
            log_lines.append(msg)
            log_box.text_area("Log", value="\n".join(log_lines[-25:]), height=260, disabled=True, key="bulk_log")

        try:
            result = run_scrape(seed_csv_path=SEED_CSV, db_path=DB_PATH, progress_callback=log)
            st.success(f"✅ Run #{result['run_id']}: {result['urls_succeeded']}/{result['urls_attempted']} succeeded.")
            if result["errors"]:
                with st.expander(f"⚠️ {len(result['errors'])} error(s)"):
                    for e in result["errors"]:
                        st.markdown(f"- `{e['url']}` — {e['error']}: {e.get('detail','')}")
        except Exception as exc:
            st.error(f"Scrape failed: {exc}")
            logger.exception("Bulk scrape failed")

    st.markdown("---")
    st.markdown("#### Run History")
    try:
        with db.get_connection(DB_PATH) as conn:
            runs = conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 10").fetchall()
        if runs:
            st.dataframe(pd.DataFrame([dict(r) for r in runs]), use_container_width=True)
        else:
            st.info("No runs yet.")
    except Exception as exc:
        st.error(str(exc))
