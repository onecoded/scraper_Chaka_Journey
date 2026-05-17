"""
Seller Portal — for business owners selling their company.
Two modes:
  1) New seller intake (no token → form to submit listing)
  2) Existing seller dashboard (token → see status of their listing,
     which buyers have viewed it, NDAs received, etc.)
"""
import os
import sys
import html
from pathlib import Path
from datetime import datetime

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from dealflow_db import (
    get_all_deals, get_deal, update_deal,
    add_seller_intake, get_outreach_log,
)

st.set_page_config(
    page_title="Mithril — Seller Portal",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SELLER_FORM_URL = "https://forms.gle/pVNQwEBsnWJQMymm7"

# ── header ────────────────────────────────────────────────────────────────────

st.markdown(
    '<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px">'
    '<span style="font-size:2rem">📦</span>'
    '<div>'
    '<div style="font-size:1.6rem;font-weight:800;'
    'background:linear-gradient(90deg,#c9d6e8 0%,#F39C12 100%);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">'
    'Mithril Seller Portal'
    '</div>'
    '<div style="color:#666;font-size:0.78rem">'
    'List your business · track buyer interest · move toward close.'
    '</div>'
    '</div></div>',
    unsafe_allow_html=True
)
st.divider()

# ── token-based auth ──────────────────────────────────────────────────────────

qp    = st.query_params
token = qp.get("token", "")

def _e(v): return html.escape(str(v or ""))

# ============================================================================
# NEW SELLER INTAKE — no token, show form
# ============================================================================
if not token:
    st.markdown("### 🏢 List Your Business for Sale")
    st.caption(
        "Tell us about your business. We'll match you with pre-qualified buyers "
        "from our signed-agreement network. Confidential. No fee to list."
    )

    with st.form("seller_intake_form"):
        c1, c2 = st.columns(2)
        with c1:
            owner_name  = st.text_input("Your Full Name *")
            owner_email = st.text_input("Email *", placeholder="you@company.com")
            owner_phone = st.text_input("Phone")
            company     = st.text_input("Business Name *")
            industry    = st.text_input("Industry / Sector *", placeholder="e.g. HVAC, Manufacturing, Healthcare")
            city        = st.text_input("City")
            state       = st.text_input("State (2-letter)", max_chars=2)
        with c2:
            revenue   = st.text_input("Annual Revenue", placeholder="$X.XM")
            ebitda    = st.text_input("EBITDA / Cash Flow", placeholder="$X.XM")
            asking    = st.text_input("Asking Price (if known)", placeholder="$X.XM or 'open'")
            founded   = st.text_input("Year Founded")
            employees = st.text_input("Number of Employees")
            reason    = st.text_area("Reason for Selling", height=80, placeholder="Retirement, new venture, etc.")

        notes = st.text_area("Anything else we should know?", height=80,
                              placeholder="Recurring revenue %, real estate included, key contracts…")

        submitted = st.form_submit_button("📤 Submit Listing", type="primary", use_container_width=True)

        if submitted:
            if not (owner_name.strip() and owner_email.strip() and company.strip() and industry.strip()):
                st.error("Required fields: Name, Email, Business Name, Industry.")
            else:
                intake = {
                    "owner_name":   owner_name.strip(),
                    "owner_email":  owner_email.strip(),
                    "owner_phone":  owner_phone.strip(),
                    "company_name": company.strip(),
                    "industry":     industry.strip(),
                    "city":         city.strip(),
                    "state":        state.strip().upper()[:2],
                    "revenue":      revenue.strip(),
                    "ebitda":       ebitda.strip(),
                    "asking_price": asking.strip(),
                    "founded_year": founded.strip(),
                    "employees":    employees.strip(),
                    "reason":       reason.strip(),
                    "notes":        notes.strip(),
                    "submitted_at": datetime.now().isoformat(),
                }
                try:
                    intake_id = add_seller_intake(intake)
                    st.success(
                        f"✅ Listing submitted! Your broker has been notified. "
                        f"You'll receive a confirmation email at **{owner_email}** within 24 hours. "
                        f"Bookmark this URL to check on your listing later:"
                    )
                    portal_url = f"http://localhost:8601/Seller_Portal?token=intake_{intake_id}"
                    st.code(portal_url, language=None)
                except Exception as ex:
                    st.error(f"Submission failed: {ex}")

    st.divider()
    st.markdown(
        f'<div style="background:#241a0d;border-left:3px solid #F39C12;padding:10px 14px;'
        f'border-radius:0 6px 6px 0;font-size:0.85rem;color:#aab">'
        f'<strong style="color:#F39C12">Prefer Google Forms?</strong> '
        f'You can also fill out our seller intake at <a href="{SELLER_FORM_URL}" '
        f'target="_blank" style="color:#F39C12">{SELLER_FORM_URL}</a>'
        f'</div>',
        unsafe_allow_html=True
    )

# ============================================================================
# EXISTING SELLER DASHBOARD — token, show their listing + buyer activity
# ============================================================================
else:
    # Token format: either a deal_id or "intake_<intake_id>"
    deal = None
    if token.startswith("intake_"):
        # Could look up intake → deal here once linked
        st.info(f"Submission token: `{token}`. Status: under broker review. "
                "Once your listing is matched with buyers, this page will show buyer activity.")
        st.stop()

    deal = get_deal(token)
    if not deal:
        st.error(f"🔒 Listing not found for token `{token}`.")
        st.stop()

    company = (deal.get("company_name") or "Your Listing").strip()
    industry = (deal.get("industry") or "").strip()
    state = (deal.get("state") or "").strip()
    city = (deal.get("city") or "").strip()
    rev = (deal.get("revenue_estimate") or "").strip()
    ebit = (deal.get("ebitda_estimate") or "").strip()
    asking = (deal.get("asking_price") or "").strip()
    stage = deal.get("deal_stage", "identified")
    nda_sent = deal.get("nda_sent", 0)
    cim_sent = deal.get("cim_sent", 0)

    # Header card
    st.markdown(
        f'<div style="background:#241a0d;border-left:4px solid #F39C12;padding:14px 20px;'
        f'border-radius:0 8px 8px 0;margin-bottom:16px">'
        f'<div style="font-size:1.3rem;font-weight:800;color:#f0f0f0">📦 {_e(company)}</div>'
        f'<div style="color:#aab;font-size:0.85rem;margin-top:3px">'
        f'{_e(industry)} · {_e(", ".join(filter(None, [city, state])))}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Stats
    log = get_outreach_log(token) or []
    buyer_count = len({e.get("buyer_id") for e in log if e.get("buyer_id")})
    nda_count   = sum(1 for e in log if (e.get("action") or "").endswith("nda"))
    cim_count   = sum(1 for e in log if (e.get("action") or "").endswith("cim"))

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("👀 Buyers Reviewing", buyer_count)
    sc2.metric("📝 NDAs Signed",      nda_count)
    sc3.metric("📄 CIMs Sent",        cim_count)
    sc4.metric("📊 Current Stage",    stage.replace("_"," ").title())

    st.markdown("---")
    st.markdown("### 📋 Listing Details")
    dc1, dc2, dc3 = st.columns(3)
    dc1.markdown(f"**Revenue**<br>{_e(rev) if rev else '—'}", unsafe_allow_html=True)
    dc2.markdown(f"**EBITDA**<br>{_e(ebit) if ebit else '—'}", unsafe_allow_html=True)
    dc3.markdown(f"**Asking**<br>{_e(asking) if asking else 'Open to offers'}", unsafe_allow_html=True)

    if log:
        st.markdown("---")
        st.markdown("### 🕐 Recent Activity")
        for entry in log[-10:][::-1]:
            ts = (entry.get("timestamp") or "")[:16].replace("T", " ")
            action = entry.get("action", "").replace("_", " ").title()
            who = entry.get("buyer_name", "A buyer")
            st.caption(f"**{ts}** — {who}: {action}")

    # Footer
    st.markdown("---")
    broker_email = os.getenv("BROKER_EMAIL", "Joseph.Schneek@gmail.com")
    broker_phone = os.getenv("BROKER_PHONE", "641-451-7288")
    broker_name  = os.getenv("BROKER_NAME",  "Joseph Schneekloth")
    st.caption(
        f"Questions about your listing? Reach out to {broker_name} — "
        f"{broker_email} · {broker_phone}. Mithril Deal Flow Forge."
    )
