"""
app.py — ArchScale Intelligence Platform
Streamlit dashboard for company research and web scraping.

Run with:   streamlit run app.py
"""

import logging
import pathlib
import sys
import threading
import time
from typing import Optional

import pandas as pd
import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import db
from services.company_service import run_scrape, export_csv

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH = ROOT / "data" / "archscale.db"
SEED_CSV = ROOT / "data" / "seed_urls.csv"

VERIFICATION_COLORS = {
    "Extracted": "#3b82f6",
    "Source checked": "#8b5cf6",
    "Cross-verified": "#10b981",
    "Not found": "#6b7280",
    "Needs review": "#f59e0b",
}

FIELD_LABELS = {
    "org_name": "Organisation",
    "owner_name": "Owner / Founder",
    "designation": "Designation",
    "org_size": "Org Size",
    "phone": "Phone",
    "email": "Email",
    "city": "City",
    "website": "Website",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "twitter": "Twitter",
    "youtube": "YouTube",
    "houzz": "Houzz",
    "behance": "Behance",
    "address": "Address",
    "description": "Description",
    "page_title": "Page Title",
    "fetch_status": "Fetch Status",
}


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ArchScale Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #141d30 50%, #0a1628 100%);
    min-height: 100vh;
}

/* ── Header ── */
.arch-header {
    background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(16,185,129,0.10) 100%);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 24px;
    backdrop-filter: blur(12px);
}
.arch-header h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #a5b4fc 0%, #34d399 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
}
.arch-header p {
    color: #94a3b8;
    margin: 6px 0 0;
    font-size: 0.95rem;
}

/* ── Metric cards ── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
}
.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px 22px;
    text-align: center;
    transition: transform 0.2s, border-color 0.2s;
}
.metric-card:hover { transform: translateY(-2px); border-color: rgba(99,102,241,0.4); }
.metric-number {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #a5b4fc;
    line-height: 1;
}
.metric-label {
    font-size: 0.78rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 6px;
}

/* ── Status badges ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.badge-extracted    { background: rgba(59,130,246,0.18); color: #60a5fa; }
.badge-checked      { background: rgba(139,92,246,0.18); color: #c084fc; }
.badge-verified     { background: rgba(16,185,129,0.18); color: #34d399; }
.badge-notfound     { background: rgba(107,114,128,0.18); color: #9ca3af; }
.badge-review       { background: rgba(245,158,11,0.18); color: #fbbf24; }

/* ── Company card ── */
.company-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
    transition: all 0.2s;
    cursor: pointer;
}
.company-card:hover {
    background: rgba(99,102,241,0.08);
    border-color: rgba(99,102,241,0.35);
}
.company-name {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 4px;
}
.company-meta {
    font-size: 0.82rem;
    color: #64748b;
}
.company-domain { color: #818cf8; font-weight: 500; }

/* ── Evidence panel ── */
.evidence-row {
    background: rgba(255,255,255,0.025);
    border-left: 3px solid rgba(99,102,241,0.4);
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin-bottom: 8px;
}
.evidence-field { font-size: 0.78rem; font-weight: 600; color: #818cf8; text-transform: uppercase; letter-spacing: 0.05em; }
.evidence-value { font-size: 0.92rem; color: #e2e8f0; margin: 4px 0; word-break: break-word; }
.evidence-source { font-size: 0.75rem; color: #475569; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: rgba(15,12,41,0.95) !important;
    border-right: 1px solid rgba(99,102,241,0.2);
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 20px rgba(99,102,241,0.4) !important;
}

/* ── Dataframe ── */
.stDataFrame { border-radius: 10px; overflow: hidden; }

/* ── Search / filter inputs ── */
.stTextInput > div > input, .stSelectbox > div {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}

/* ── Info / warning banners ── */
.stAlert { border-radius: 10px; }

/* ── Divider ── */
hr { border-color: rgba(255,255,255,0.08) !important; }
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────
if "scrape_running" not in st.session_state:
    st.session_state.scrape_running = False
if "scrape_log" not in st.session_state:
    st.session_state.scrape_log = []
if "scrape_result" not in st.session_state:
    st.session_state.scrape_result = None
if "selected_company_id" not in st.session_state:
    st.session_state.selected_company_id = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "dashboard"


# ── DB initialisation ─────────────────────────────────────────────────────────
try:
    db.init_db(DB_PATH)
except Exception as exc:
    st.error(f"❌ Failed to initialise database: {exc}")
    st.stop()


# ── Helper functions ──────────────────────────────────────────────────────────

def badge_html(status: str) -> str:
    cls_map = {
        "Extracted": "badge-extracted",
        "Source checked": "badge-checked",
        "Cross-verified": "badge-verified",
        "Not found": "badge-notfound",
        "Needs review": "badge-review",
    }
    cls = cls_map.get(status, "badge-notfound")
    return f'<span class="badge {cls}">{status}</span>'


def icon_for_field(field: str) -> str:
    icons = {
        "org_name": "🏢", "owner_name": "👤", "designation": "🎖️",
        "org_size": "👥", "phone": "📞", "email": "✉️", "city": "📍",
        "website": "🌐", "linkedin": "💼", "instagram": "📸",
        "facebook": "👍", "twitter": "🐦", "address": "🗺️",
        "description": "📝", "page_title": "🏷️", "fetch_status": "⚠️",
        "youtube": "▶️", "houzz": "🏠", "behance": "🎨",
    }
    return icons.get(field, "📌")


def display_value(field: str, value: Optional[str]) -> str:
    if not value:
        return "<em style='color:#4b5563'>Not found</em>"
    if field in ("website", "linkedin", "instagram", "facebook", "twitter",
                 "youtube", "houzz", "behance"):
        return f'<a href="{value}" target="_blank" style="color:#818cf8">{value}</a>'
    if field == "email":
        return f'<a href="mailto:{value}" style="color:#818cf8">{value}</a>'
    if field == "phone":
        return f'<a href="tel:{value}" style="color:#818cf8">{value}</a>'
    return f"<span style='color:#e2e8f0'>{value}</span>"


def get_metrics():
    try:
        with db.get_connection(DB_PATH) as conn:
            return db.get_summary_metrics(conn)
    except Exception:
        return {}


def get_companies(search="", category="", city="", status=""):
    try:
        with db.get_connection(DB_PATH) as conn:
            return db.list_companies(conn, search=search, category=category, city=city, status=status)
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return []


def get_evidence(company_id: int):
    try:
        with db.get_connection(DB_PATH) as conn:
            return db.get_evidence_for_company(conn, company_id)
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return []


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 12px 0 20px'>
        <div style='font-size:2.5rem'>🏛️</div>
        <div style='font-family: Space Grotesk, sans-serif; font-weight:700;
             font-size:1.1rem; color:#a5b4fc'>ArchScale Intel</div>
        <div style='font-size:0.75rem; color:#475569'>Company Research Platform</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    nav_choice = st.radio(
        "Navigation",
        ["📊 Dashboard", "🔍 Browse Companies", "🔬 Evidence Inspector", "⚙️ Scrape Control"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Quick stats in sidebar
    metrics = get_metrics()
    st.markdown(f"""
    <div style='font-size:0.78rem; color:#475569; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px'>
    Quick Stats
    </div>
    <div style='display:flex; flex-direction:column; gap:8px'>
        <div style='display:flex; justify-content:space-between; font-size:0.85rem'>
            <span style='color:#64748b'>Companies</span>
            <span style='color:#a5b4fc; font-weight:600'>{metrics.get("total_companies", 0)}</span>
        </div>
        <div style='display:flex; justify-content:space-between; font-size:0.85rem'>
            <span style='color:#64748b'>Evidence rows</span>
            <span style='color:#a5b4fc; font-weight:600'>{metrics.get("total_evidence", 0)}</span>
        </div>
        <div style='display:flex; justify-content:space-between; font-size:0.85rem'>
            <span style='color:#fbbf24'>Needs review</span>
            <span style='color:#fbbf24; font-weight:600'>{metrics.get("needs_review", 0)}</span>
        </div>
        <div style='display:flex; justify-content:space-between; font-size:0.85rem'>
            <span style='color:#9ca3af'>Not found</span>
            <span style='color:#9ca3af; font-weight:600'>{metrics.get("not_found", 0)}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.7rem; color:#334155; text-align:center'>"
        "All data sourced from publicly available pages. "
        "No records are fabricated or inferred."
        "</div>",
        unsafe_allow_html=True,
    )


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="arch-header">
    <h1>🏛️ ArchScale Intelligence Platform</h1>
    <p>Company research & web intelligence for Indian architecture and interior design firms</p>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ═══════════════════════════════════════════════════════════════════════════════
if nav_choice == "📊 Dashboard":
    metrics = get_metrics()

    # Metric grid
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🏢 Companies", metrics.get("total_companies", 0))
    with col2:
        st.metric("📋 Evidence Rows", metrics.get("total_evidence", 0))
    with col3:
        st.metric("🟡 Needs Review", metrics.get("needs_review", 0))
    with col4:
        st.metric("⬜ Not Found", metrics.get("not_found", 0))
    with col5:
        last = metrics.get("last_run")
        st.metric("🔄 Last Run", last["status"].title() if last else "Never")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Recent companies quick view
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### Recently Scraped Companies")
        companies = get_companies()

        if not companies:
            st.info(
                "📭 No companies scraped yet.\n\n"
                "Go to **⚙️ Scrape Control** to run your first scrape, or check that "
                "`data/seed_urls.csv` contains valid URLs."
            )
        else:
            for comp in list(companies)[:8]:
                org = comp["org_name"] or comp["domain_key"]
                owner = comp["owner_name"] or "—"
                city = comp["city"] or "—"
                cat_badge = "🏗️ Arch" if comp["category"] == "architecture" else "🛋️ Interior"
                review_count = comp["needs_review_count"] or 0

                review_note = f' <span style="color:#fbbf24">⚠ {review_count} to review</span>' if review_count else ""

                st.markdown(f"""
                <div class="company-card" onclick="">
                    <div class="company-name">{org}</div>
                    <div class="company-meta">
                        <span class="company-domain">{comp["domain_key"]}</span>
                        &nbsp;·&nbsp; {cat_badge}
                        &nbsp;·&nbsp; 📍 {city}
                        &nbsp;·&nbsp; 👤 {owner}
                        {review_note}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with col_right:
        st.markdown("#### Data Quality Overview")

        if metrics.get("total_evidence", 0) == 0:
            st.info("Run a scrape to populate quality metrics.")
        else:
            try:
                with db.get_connection(DB_PATH) as conn:
                    status_counts = conn.execute(
                        "SELECT verification_status, COUNT(*) as cnt FROM evidence GROUP BY verification_status"
                    ).fetchall()

                labels = [r["verification_status"] for r in status_counts]
                values = [r["cnt"] for r in status_counts]

                df_chart = pd.DataFrame({"Status": labels, "Count": values})
                st.bar_chart(df_chart.set_index("Status"))
            except Exception:
                st.warning("Unable to load chart data.")

        st.markdown("---")
        st.markdown("#### Verification Status Key")
        for status, color in VERIFICATION_COLORS.items():
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<div style="width:10px;height:10px;border-radius:50%;background:{color}"></div>'
                f'<span style="font-size:0.82rem;color:#94a3b8">{status}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Browse Companies
# ═══════════════════════════════════════════════════════════════════════════════
elif nav_choice == "🔍 Browse Companies":
    st.markdown("#### Company Intelligence Table")

    # Filters
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([3, 2, 2, 2])
    with filter_col1:
        search = st.text_input("🔍 Search", placeholder="Company, owner, email, city…", key="search_input")
    with filter_col2:
        category_filter = st.selectbox("Category", ["", "architecture", "interior", "other"], key="cat_filter")
    with filter_col3:
        city_filter = st.text_input("City", placeholder="e.g. Mumbai", key="city_filter")
    with filter_col4:
        status_filter = st.selectbox(
            "Verification Status",
            ["", "Extracted", "Source checked", "Cross-verified", "Not found", "Needs review"],
            key="status_filter",
        )

    companies = get_companies(
        search=search,
        category=category_filter,
        city=city_filter,
        status=status_filter,
    )

    if not companies:
        if search or category_filter or city_filter or status_filter:
            st.warning("No companies match the current filters.")
        else:
            st.info(
                "📭 No companies found. Run a scrape from **⚙️ Scrape Control** first."
            )
    else:
        st.caption(f"Showing {len(companies)} company/companies")

        # Table display
        table_data = []
        for comp in companies:
            table_data.append({
                "Organisation": comp["org_name"] or "—",
                "Domain": comp["domain_key"],
                "Category": comp["category"].title(),
                "Owner / Founder": comp["owner_name"] or "—",
                "Designation": comp["designation"] or "—",
                "City": comp["city"] or "—",
                "Email": comp["email"] or "—",
                "Phone": comp["phone"] or "—",
                "Website": comp["website"] or "—",
                "LinkedIn": comp["linkedin"] or "—",
                "Last Scraped": (comp["last_scraped_at"] or "")[:10],
                "⚠ Review": comp["needs_review_count"] or 0,
            })

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, height=420)

        st.markdown("---")

        # Company detail viewer
        st.markdown("#### Company Detail View")
        company_names = [
            f"{comp['org_name'] or comp['domain_key']} ({comp['domain_key']})"
            for comp in companies
        ]
        comp_map = {
            f"{comp['org_name'] or comp['domain_key']} ({comp['domain_key']})": comp
            for comp in companies
        }

        selected_name = st.selectbox("Select company to inspect:", ["— select —"] + company_names, key="detail_select")
        if selected_name and selected_name != "— select —":
            comp = comp_map[selected_name]
            st.session_state.selected_company_id = comp["id"]

            # Header
            col_a, col_b = st.columns([3, 1])
            with col_a:
                org = comp["org_name"] or comp["domain_key"]
                st.markdown(f"### {org}")
                if comp["website"]:
                    st.markdown(f"🌐 [{comp['website']}]({comp['website']})")
            with col_b:
                cat = comp["category"].title()
                st.markdown(f"**Category:** {cat}")
                st.markdown(f"**Last scraped:** {(comp['last_scraped_at'] or '')[:10]}")

            # Key fields
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                st.markdown(f"**👤 Owner/Founder:** {comp['owner_name'] or '—'}")
                st.markdown(f"**🎖️ Designation:** {comp['designation'] or '—'}")
            with fc2:
                st.markdown(f"**📞 Phone:** {comp['phone'] or '—'}")
                st.markdown(f"**✉️ Email:** {comp['email'] or '—'}")
            with fc3:
                st.markdown(f"**📍 City:** {comp['city'] or '—'}")
                st.markdown(f"**👥 Org Size:** {comp['org_size'] or '—'}")

            # Social links
            socials = []
            for f, label in [("linkedin", "LinkedIn"), ("instagram", "Instagram"),
                             ("facebook", "Facebook"), ("twitter", "Twitter")]:
                if comp[f]:
                    socials.append(f"[{label}]({comp[f]})")
            if socials:
                st.markdown("**Social Links:** " + " · ".join(socials))

            if comp["needs_review_count"]:
                st.warning(f"⚠️ {comp['needs_review_count']} field(s) need manual review before this record can be considered verified.")

            st.markdown("---")
            st.caption(
                "ℹ️ All values above come from publicly accessible web pages. "
                "Owner/founder information is marked 'Needs review' and requires manual confirmation."
            )

        # Export
        st.markdown("---")
        st.markdown("#### Export")
        if st.button("⬇️ Export filtered results to CSV"):
            csv_data = export_csv(
                db_path=DB_PATH,
                search=search,
                category=category_filter,
                city=city_filter,
                status=status_filter,
            )
            if csv_data:
                st.download_button(
                    "📥 Download CSV",
                    data=csv_data,
                    file_name="archscale_companies.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No data to export with current filters.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Evidence Inspector
# ═══════════════════════════════════════════════════════════════════════════════
elif nav_choice == "🔬 Evidence Inspector":
    st.markdown("#### Field-Level Evidence Inspector")
    st.caption(
        "Every extracted value retains its source URL, supporting text, extraction method, "
        "and verification status. Use this view to inspect provenance and approve/reject values."
    )

    companies = get_companies()
    if not companies:
        st.info("No companies available. Run a scrape first.")
    else:
        company_options = [
            f"{comp['org_name'] or comp['domain_key']} ({comp['domain_key']})"
            for comp in companies
        ]
        comp_map = {
            f"{comp['org_name'] or comp['domain_key']} ({comp['domain_key']})": comp
            for comp in companies
        }

        sel = st.selectbox("Select Company", ["— select —"] + company_options, key="evidence_select")

        if sel and sel != "— select —":
            comp = comp_map[sel]
            company_id = comp["id"]

            evidence_rows = get_evidence(company_id)

            if not evidence_rows:
                st.warning("No evidence found for this company.")
            else:
                # Group by field
                fields_seen: dict[str, list] = {}
                for ev in evidence_rows:
                    fn = ev["field_name"]
                    fields_seen.setdefault(fn, []).append(ev)

                st.markdown(f"**{len(evidence_rows)} evidence record(s) across {len(fields_seen)} field(s)**")

                for field_name, rows in fields_seen.items():
                    label = FIELD_LABELS.get(field_name, field_name)
                    icon = icon_for_field(field_name)

                    with st.expander(f"{icon} {label}  ({len(rows)} candidate(s))", expanded=(field_name in ("org_name", "owner_name", "email", "phone"))):
                        for ev in rows:
                            status = ev["verification_status"]
                            value = ev["extracted_value"] or "*Not found*"
                            source_url = ev["source_url"]
                            method = ev["extraction_method"] or "unknown"
                            snippet = ev["supporting_text"] or ""
                            extracted_at = (ev["extracted_at"] or "")[:19].replace("T", " ")

                            st.markdown(f"""
                            <div class="evidence-row">
                                <div class="evidence-field">{label} &nbsp;&nbsp; {badge_html(status)}</div>
                                <div class="evidence-value">{value}</div>
                                <div class="evidence-source">
                                    Source: <a href="{source_url}" target="_blank" style="color:#6366f1">{source_url[:80]}</a>
                                    &nbsp;·&nbsp; Method: <em>{method}</em>
                                    &nbsp;·&nbsp; Extracted: {extracted_at}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                            if snippet:
                                with st.expander("📄 Supporting text / JSON-LD context", expanded=False):
                                    st.code(snippet[:1000], language="json" if method == "json_ld" else "text")

                            # Status update controls
                            ev_id = ev["id"]
                            new_status = st.selectbox(
                                "Update status",
                                ["Extracted", "Source checked", "Cross-verified", "Not found", "Needs review"],
                                index=["Extracted", "Source checked", "Cross-verified", "Not found", "Needs review"].index(status)
                                      if status in ["Extracted", "Source checked", "Cross-verified", "Not found", "Needs review"]
                                      else 0,
                                key=f"status_{ev_id}",
                            )
                            reviewer_note = st.text_input(
                                "Reviewer note (optional)",
                                key=f"note_{ev_id}",
                                placeholder="Add note for this field...",
                            )
                            if st.button("💾 Save", key=f"save_{ev_id}"):
                                try:
                                    import datetime
                                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                                    with db.get_connection(DB_PATH) as conn:
                                        db.update_evidence_status(conn, ev_id, new_status, reviewer_note or None, now)
                                    st.success("Status updated.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Update failed: {exc}")

                            st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Scrape Control
# ═══════════════════════════════════════════════════════════════════════════════
elif nav_choice == "⚙️ Scrape Control":
    st.markdown("#### Scrape Control Panel")
    st.caption(
        "Launch a scraping run against the approved company URLs in `data/seed_urls.csv`. "
        "The scraper checks robots.txt, respects rate limits, and never fabricates data."
    )

    # Seed CSV preview
    col_seed, col_info = st.columns([2, 1])
    with col_seed:
        st.markdown("**Current Seed URLs** (`data/seed_urls.csv`)")
        if SEED_CSV.exists():
            try:
                df_seed = pd.read_csv(SEED_CSV)
                st.dataframe(df_seed, use_container_width=True, height=260)
                st.caption(f"{len(df_seed)} URL(s) loaded")
            except Exception as exc:
                st.error(f"Cannot read seed CSV: {exc}")
        else:
            st.warning(
                "⚠️ `data/seed_urls.csv` not found.\n\n"
                "Create the file with columns: `url`, `category` (architecture / interior / other), `notes`."
            )

    with col_info:
        st.markdown("**Scraping behaviour**")
        st.markdown("""
        - ✅ Checks `robots.txt` before fetching
        - ✅ Rate-limits requests per domain
        - ✅ Validates URLs (SSRF protection)
        - ✅ Deduplicates on re-run
        - ✅ Logs all errors
        - ❌ Does not bypass auth/CAPTCHAs
        - ❌ Does not invent or infer data
        - ❌ Does not scrape search engines
        """)

    st.markdown("---")

    # CSV upload for adding new URLs
    st.markdown("**Add URLs via CSV upload** (will merge with existing seed file)")
    uploaded = st.file_uploader(
        "Upload CSV (columns: url, category, notes)",
        type=["csv"],
        key="url_uploader",
    )
    if uploaded:
        try:
            new_df = pd.read_csv(uploaded)
            if "url" not in new_df.columns:
                st.error("Uploaded CSV must have a 'url' column.")
            else:
                existing = pd.read_csv(SEED_CSV) if SEED_CSV.exists() else pd.DataFrame(columns=["url", "category", "notes"])
                merged = pd.concat([existing, new_df]).drop_duplicates(subset=["url"])
                merged.to_csv(SEED_CSV, index=False)
                st.success(f"✅ Merged. Seed file now contains {len(merged)} URL(s).")
                st.rerun()
        except Exception as exc:
            st.error(f"Failed to process upload: {exc}")

    st.markdown("---")

    # Scrape action
    if st.session_state.scrape_running:
        st.warning("⏳ A scraping run is in progress…")

        if st.session_state.scrape_log:
            log_text = "\n".join(st.session_state.scrape_log[-30:])
            st.text_area("Scrape log", value=log_text, height=300, key="scrape_log_area", disabled=True)

        if st.button("🔄 Refresh status"):
            st.rerun()

    else:
        if st.button("🚀 Start Scrape Run", type="primary"):
            st.session_state.scrape_running = True
            st.session_state.scrape_log = []
            st.session_state.scrape_result = None

            log_container = st.empty()
            progress_bar = st.progress(0)

            log_lines: list[str] = []

            def append_log(msg: str) -> None:
                log_lines.append(msg)
                log_container.text_area(
                    "Scrape log",
                    value="\n".join(log_lines[-30:]),
                    height=300,
                    key="live_log",
                    disabled=True,
                )

            try:
                append_log("Starting scrape run…")
                result = run_scrape(
                    seed_csv_path=SEED_CSV,
                    db_path=DB_PATH,
                    progress_callback=append_log,
                )
                st.session_state.scrape_result = result
                st.session_state.scrape_log = log_lines
                append_log("✅ Scrape complete!")
            except Exception as exc:
                st.error(f"❌ Scrape failed with exception: {exc}")
                logger.exception("Scrape run failed")
            finally:
                st.session_state.scrape_running = False
                progress_bar.progress(100)

        if st.session_state.scrape_result:
            res = st.session_state.scrape_result
            st.success(
                f"✅ Last run #{res['run_id']}: "
                f"{res['urls_succeeded']}/{res['urls_attempted']} succeeded, "
                f"{res['urls_failed']} failed."
            )
            if res["errors"]:
                with st.expander(f"⚠️ {len(res['errors'])} error(s)"):
                    for err in res["errors"]:
                        st.markdown(
                            f"- **{err['url']}** — `{err['error']}`: {err.get('detail', '')}"
                        )

    st.markdown("---")

    # Scrape run history
    st.markdown("#### Scrape Run History")
    try:
        with db.get_connection(DB_PATH) as conn:
            runs = conn.execute(
                "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 20"
            ).fetchall()
        if runs:
            runs_data = [dict(r) for r in runs]
            df_runs = pd.DataFrame(runs_data)
            st.dataframe(df_runs, use_container_width=True)
        else:
            st.info("No scrape runs yet.")
    except Exception as exc:
        st.error(f"Could not load run history: {exc}")

    st.markdown("---")

    # Error log
    st.markdown("#### Recent Scrape Errors")
    try:
        with db.get_connection(DB_PATH) as conn:
            errs = conn.execute(
                "SELECT * FROM scrape_errors ORDER BY id DESC LIMIT 50"
            ).fetchall()
        if errs:
            errs_data = [dict(e) for e in errs]
            df_errs = pd.DataFrame(errs_data)
            st.dataframe(df_errs, use_container_width=True)
        else:
            st.info("No errors recorded yet.")
    except Exception as exc:
        st.error(f"Could not load error log: {exc}")
