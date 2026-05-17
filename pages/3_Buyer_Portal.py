"""
Buyer Portal — logged-in view for buyers to see their matched deals.

Access: http://localhost:8601/Buyer_Portal?token=<buyer_token>
Token is the buyer's id (or a hash if you want stronger auth later).
"""
import os
import sys
import html
from pathlib import Path
from urllib.parse import quote as _urlquote

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from dealflow_db import (
    get_all_deals, get_buyer, get_all_buyers, update_deal,
    log_outreach,
)

st.set_page_config(
    page_title="Mithril — Buyer Portal",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── header ────────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px">'
    '<span style="font-size:2rem">👑</span>'
    '<div>'
    '<div style="font-size:1.6rem;font-weight:800;'
    'background:linear-gradient(90deg,#c9d6e8 0%,#9B59B6 100%);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">'
    'Mithril Buyer Portal'
    '</div>'
    '<div style="color:#666;font-size:0.78rem">'
    'Your private deal flow. Curated to your mandate.'
    '</div>'
    '</div></div>',
    unsafe_allow_html=True
)
st.divider()

# ── token-based auth ──────────────────────────────────────────────────────────

qp = st.query_params
token = qp.get("token", "")

if not token:
    st.warning("🔒 This is a private buyer portal. You need a buyer access token in the URL.")
    st.info(
        "**For your broker:** Each buyer's portal URL is "
        "`http://localhost:8601/Buyer_Portal?token=<buyer_id>`. "
        "Send this link to the buyer after they sign the agreement."
    )
    # Fallback: let user pick a buyer for demo/testing
    st.markdown("---")
    st.caption("Demo / test mode — pick a buyer below:")
    all_buyers = get_all_buyers()
    if all_buyers:
        pick = st.selectbox("Select buyer", [""] + [f"{b['name']} ({b.get('id','')})" for b in all_buyers])
        if pick:
            import re as _re
            m = _re.search(r"\(([^)]+)\)$", pick)
            if m:
                st.query_params["token"] = m.group(1)
                st.rerun()
    st.stop()

buyer = get_buyer(token)
if not buyer:
    st.error(f"🔒 Invalid buyer token: `{token}`")
    st.stop()

# ── buyer header ──────────────────────────────────────────────────────────────

buyer_name      = buyer.get("name") or buyer.get("firm") or "Buyer"
buyer_email     = buyer.get("email","")
buyer_phone     = buyer.get("phone","")
buyer_industries = ", ".join(buyer.get("industries") or [])
buyer_states    = ", ".join(list(buyer.get("states") or {}) if isinstance(buyer.get("states"), dict) else (buyer.get("states") or []))
b_emin          = buyer.get("ebitda_min", 0) or 0
b_emax          = buyer.get("ebitda_max", 0) or 0

st.markdown(
    f'<div style="background:#1a0d24;border-left:4px solid #9B59B6;padding:14px 20px;'
    f'border-radius:0 8px 8px 0;margin-bottom:16px">'
    f'<div style="font-size:1.3rem;font-weight:800;color:#f0f0f0">👑 Welcome, {html.escape(buyer_name)}</div>'
    f'<div style="color:#aab;font-size:0.85rem;margin-top:3px">'
    f'Mandate: <strong style="color:#d4b3e8">{html.escape(buyer_industries or "any industry")}</strong>'
    + (f' · States: {html.escape(buyer_states)}' if buyer_states else "")
    + (f' · EBITDA ${b_emin/1e6:.1f}M – ${b_emax/1e6:.1f}M' if b_emin or b_emax else "")
    + '</div>'
    '</div>',
    unsafe_allow_html=True
)

# ── load buyer's matched deals ────────────────────────────────────────────────

all_deals = get_all_deals(buyer_id=token)
# Filter out dead/closed deals from the portal view
active = [d for d in all_deals if d.get("deal_stage") not in ("dead","closed","passed")]

# Stats row
sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric("📦 Active Deals", len(active))
sc2.metric("🔥 Hot Matches", sum(1 for d in active if d.get("interest_level") == "hot"))
sc3.metric("📝 NDAs Sent",   sum(1 for d in active if d.get("nda_sent")))
sc4.metric("📄 Under LOI",   sum(1 for d in active if d.get("deal_stage") == "loi"))

st.markdown("---")

if not active:
    st.info(
        "No active matches yet. Your broker is sourcing — new deals will appear here "
        "as soon as they're matched to your mandate. "
        f"Questions? Reach out to {os.getenv('BROKER_EMAIL','your broker')}."
    )
    st.stop()

# ── filter ────────────────────────────────────────────────────────────────────

fc1, fc2, fc3 = st.columns([3, 2, 2])
search = fc1.text_input("🔎 Search active deals", placeholder="Company, industry, state…",
                         label_visibility="collapsed")
status_filter = fc2.selectbox("Status", ["All", "New", "NDA Sent", "CIM Reviewed", "Under LOI"])
sort_by = fc3.selectbox("Sort", ["Newest", "Highest Match Score", "Largest EBITDA"])

filtered = list(active)
if search.strip():
    q = search.lower().strip()
    filtered = [d for d in filtered
                if q in (d.get("company_name") or "").lower()
                or q in (d.get("industry") or "").lower()
                or q in (d.get("state") or "").lower()]
if status_filter == "New":
    filtered = [d for d in filtered if not d.get("nda_sent")]
elif status_filter == "NDA Sent":
    filtered = [d for d in filtered if d.get("nda_sent") and not d.get("cim_sent")]
elif status_filter == "CIM Reviewed":
    filtered = [d for d in filtered if d.get("cim_sent") and not d.get("loi_received")]
elif status_filter == "Under LOI":
    filtered = [d for d in filtered if d.get("deal_stage") == "loi"]

if sort_by == "Newest":
    filtered.sort(key=lambda d: d.get("date_added",""), reverse=True)
elif sort_by == "Highest Match Score":
    filtered.sort(key=lambda d: d.get("match_score", 0), reverse=True)
elif sort_by == "Largest EBITDA":
    def _pd(v):
        s = str(v or "").upper().replace("$","").replace(",","").replace(" ","")
        try:
            if s.endswith("M"): return float(s[:-1]) * 1_000_000
            if s.endswith("K"): return float(s[:-1]) * 1_000
            return float(s)
        except: return 0
    filtered.sort(key=lambda d: _pd(d.get("ebitda_estimate","")), reverse=True)

st.caption(f"Showing {len(filtered)} of {len(active)} active deals")

# ── deal cards ────────────────────────────────────────────────────────────────

def _e(v): return html.escape(str(v or ""))

for deal in filtered[:50]:
    did       = deal.get("id")
    company   = (deal.get("company_name") or "").strip()
    industry  = (deal.get("industry") or "").strip()
    state     = (deal.get("state") or "").strip()
    city      = (deal.get("city") or "").strip()
    rev       = (deal.get("revenue_estimate") or "").strip()
    ebit      = (deal.get("ebitda_estimate") or "").strip()
    asking    = (deal.get("asking_price") or "").strip()
    score     = deal.get("match_score", 0)
    nda_sent  = deal.get("nda_sent", 0)
    cim_sent  = deal.get("cim_sent", 0)
    interest  = deal.get("interest_level", "warm")
    notes     = (deal.get("response_notes") or "").strip()[:200]
    location  = ", ".join(filter(None, [city, state])) or "—"

    # Status pill
    if cim_sent:
        status_pill = '<span style="background:#27AE60;color:#0d0d0d;font-size:0.7rem;padding:2px 8px;border-radius:8px;font-weight:700">CIM REVIEWED</span>'
    elif nda_sent:
        status_pill = '<span style="background:#9B59B6;color:#fff;font-size:0.7rem;padding:2px 8px;border-radius:8px;font-weight:700">NDA SENT</span>'
    else:
        status_pill = '<span style="background:#F39C12;color:#0d0d0d;font-size:0.7rem;padding:2px 8px;border-radius:8px;font-weight:700">NEW</span>'

    score_color = "#27AE60" if score >= 80 else "#F39C12" if score >= 60 else "#888"

    st.markdown(
        f'<div style="border-left:4px solid #9B59B6;border-radius:0 8px 8px 0;'
        f'padding:14px 18px;margin-bottom:8px;background:#0d0a14;border:1px solid #9B59B622">'
        # Header
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<span style="font-size:1.1rem;font-weight:800;color:#f0f0f0">{_e(company)}</span>'
        f'<span style="display:flex;gap:6px;align-items:center">'
        f'{status_pill}'
        f'<span style="background:{score_color}22;color:{score_color};font-size:0.72rem;padding:2px 9px;border-radius:10px;font-weight:700">{score}/100 match</span>'
        f'</span>'
        f'</div>'
        # Sub-row
        f'<div style="color:#888;font-size:0.85rem;margin-bottom:8px">'
        f'{_e(industry)} · {_e(location)}'
        f'</div>'
        # Financials grid
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;font-size:0.85rem">'
        f'<div><span style="color:#666;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px">Revenue</span><br>'
        f'<strong style="color:#e8eaf0">{_e(rev) if rev else "—"}</strong></div>'
        f'<div><span style="color:#666;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px">EBITDA</span><br>'
        f'<strong style="color:#e8eaf0">{_e(ebit) if ebit else "—"}</strong></div>'
        f'<div><span style="color:#666;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px">Asking</span><br>'
        f'<strong style="color:#e8eaf0">{_e(asking) if asking else "—"}</strong></div>'
        f'</div>'
        + (f'<div style="margin-top:10px;color:#666;font-size:0.78rem;font-style:italic">{_e(notes)}</div>' if notes else "")
        + '</div>',
        unsafe_allow_html=True
    )

    # Action buttons row
    bc1, bc2, bc3, bc4 = st.columns(4)

    if not nda_sent:
        if bc1.button("📝 Request NDA", key=f"bp_nda_{did}", use_container_width=True, type="primary"):
            update_deal(did, {"nda_sent": 1, "deal_stage": "nda_sent",
                              "status": "nda_requested",
                              "last_contacted": __import__("datetime").datetime.now().isoformat()})
            log_outreach(did, token, buyer_name, "buyer_requested_nda")
            st.success("NDA requested — your broker has been notified.")
            st.rerun()
    else:
        bc1.success("✓ NDA Sent")

    if nda_sent and not cim_sent:
        if bc2.button("📄 Request CIM", key=f"bp_cim_{did}", use_container_width=True, type="primary"):
            update_deal(did, {"cim_sent": 1, "deal_stage": "cim_sent"})
            log_outreach(did, token, buyer_name, "buyer_requested_cim")
            st.success("CIM requested — your broker has been notified.")
            st.rerun()
    elif cim_sent:
        bc2.success("✓ CIM Reviewed")

    if bc3.button("👍 Interested", key=f"bp_int_{did}", use_container_width=True):
        update_deal(did, {"interest_level": "hot", "seller_interested": 1})
        log_outreach(did, token, buyer_name, "buyer_expressed_interest")
        st.success("Marked as interested.")
        st.rerun()

    if bc4.button("👎 Pass", key=f"bp_pass_{did}", use_container_width=True):
        update_deal(did, {"deal_stage": "passed", "status": "passed",
                          "interest_level": "cold"})
        log_outreach(did, token, buyer_name, "buyer_passed")
        st.info("Marked as passed.")
        st.rerun()

# ── footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
broker_email = os.getenv("BROKER_EMAIL", "Joseph.Schneek@gmail.com")
broker_phone = os.getenv("BROKER_PHONE", "641-451-7288")
broker_name  = os.getenv("BROKER_NAME",  "Joseph Schneekloth")
st.caption(
    f"Questions or want to discuss any of these? Reach out to {broker_name} — "
    f"{broker_email} · {broker_phone}. Mithril Deal Flow Forge."
)
