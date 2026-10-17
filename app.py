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
from services.company_service import run_scrape, export_csv
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
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "intel_results": [],
    "intel_running": False,
    "scrape_log": [],
    "active_intel_idx": None,
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
            "city": intel.get("city"),
            "website": intel.get("website"),
            "description": intel.get("description"),
        }
        for field, val in field_map.items():
            if val:
                db.upsert_evidence(conn, company_id, field, val, intel["url"],
                                   None, "structured", now)
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
        ["🎯 Competitor Analyser", "📊 Dashboard", "🔍 Saved Companies", "🔬 Evidence", "⚙️ Bulk Scrape"],
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
        CEO-facing competitor intelligence for Indian architecture & interior design firms —
        enter any company's website to instantly analyse their services, portfolio, social presence, and contact details.
    </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Competitor Analyser (PRIMARY)
# ═══════════════════════════════════════════════════════════════════════════════
if nav == "🎯 Competitor Analyser":

    # ── Input Panel ──────────────────────────────────────────────────────────
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown('<div class="input-card-title">🎯 Analyse a Competitor</div>', unsafe_allow_html=True)

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
