"""
buyer_outreach.py — Generate teaser emails to recruit new buyers
into signing a buyer agreement and joining the Fellowship.

Uses Claude (Anthropic API) for personalization. Falls back to a static
template if no API key configured.
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

BUYER_FORM_URL = "https://forms.gle/Ka7VuFtryfkmvpp48"

BROKER_NAME    = os.getenv("BROKER_NAME",    "Joseph Schneekloth")
BROKER_TITLE   = os.getenv("BROKER_TITLE",   "Chief Growth Officer")
BROKER_COMPANY = os.getenv("BROKER_COMPANY", "Valar Advisory")
BROKER_PHONE   = os.getenv("BROKER_PHONE",   "641-451-7288")
BROKER_EMAIL   = os.getenv("BROKER_EMAIL",   "Joseph.Schneek@gmail.com")


def _sample_deals_for_pitch(deals: list, max_n: int = 3) -> list:
    """Return top N anonymized deals to mention in recruitment email."""
    sellers = [d for d in deals
               if (d.get("company_name") or "").strip()
               and (d.get("revenue_estimate") or d.get("ebitda_estimate"))
               and not (d.get("buyer_id") or "").strip()]  # unmatched sellers
    sellers.sort(key=lambda d: d.get("match_score", 0), reverse=True)
    return sellers[:max_n]


def _anonymize_deal(d: dict) -> str:
    """Format a deal as anonymized pitch line."""
    industry = (d.get("industry") or "Business").strip()
    state    = (d.get("state") or "").strip()
    geo      = state or (d.get("city") or "US").strip()
    rev      = (d.get("revenue_estimate") or "").strip()
    ebit     = (d.get("ebitda_estimate") or "").strip()
    parts = [industry, f"in {geo}" if geo else ""]
    if rev:  parts.append(f"~{rev} revenue")
    if ebit: parts.append(f"~{ebit} EBITDA")
    return " · ".join(p for p in parts if p)


def generate_recruitment_email_ai(prospect: dict, sample_deals: list) -> dict:
    """
    Use Claude to generate a personalized recruitment email.
    Returns {subject, body}. Falls back to static template if no API key.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not api_key.startswith("sk-"):
        return generate_recruitment_email_static(prospect, sample_deals)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
    except Exception:
        return generate_recruitment_email_static(prospect, sample_deals)

    prospect_name = prospect.get("name") or prospect.get("contact_name") or "there"
    prospect_firm = prospect.get("firm") or prospect.get("company") or ""
    prospect_focus = ", ".join((prospect.get("industries") or [])[:3]) or "M&A acquisitions"

    deal_summaries = "\n".join(f"- {_anonymize_deal(d)}" for d in sample_deals) or "- Various $1M-$50M EBITDA targets across multiple sectors"

    prompt = f"""Write a short, warm, fun-but-professional recruitment email to a prospective buyer for a business brokerage firm. Style guide:

- Tone: confident, conversational dealmaker. Not stiff. Not corporate-robot.
- Length: 150-180 words MAX. Punchy.
- Open with one line that hooks — a market observation or named win.
- Reference 2-3 of our current active deals (anonymized teaser-level, no company names).
- End with a clear CTA: sign our buyer agreement so they get first-look on new deals.
- Sign-off: clean, just Joseph + phone, no clutter.

RECIPIENT:
- Name: {prospect_name}
- Firm: {prospect_firm}
- Stated acquisition focus: {prospect_focus}

OUR CURRENT ACTIVE DEALS (sample to reference, anonymized):
{deal_summaries}

CALL-TO-ACTION: sign our 1-page buyer agreement at {BUYER_FORM_URL} — once signed, they get the live deal pipeline.

OUTPUT FORMAT:
Subject: <subject line>

<body>

Best,
{BROKER_NAME}
{BROKER_COMPANY} · {BROKER_PHONE}

Generate ONLY the email. No explanation."""

    try:
        msg = client.messages.create(
            model=os.getenv("EMAIL_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
    except Exception:
        return generate_recruitment_email_static(prospect, sample_deals)

    # Parse subject + body
    m = re.match(r"Subject:\s*(.+?)\n+(.+)", raw, re.DOTALL | re.I)
    if m:
        return {"subject": m.group(1).strip(), "body": m.group(2).strip()}
    return {"subject": f"A few deals you should see — {prospect_firm}".strip(" —"), "body": raw}


def generate_recruitment_email_static(prospect: dict, sample_deals: list) -> dict:
    """Fallback static template (no API key required)."""
    name = prospect.get("name") or prospect.get("contact_name") or "there"
    firm = prospect.get("firm") or prospect.get("company") or ""
    focus = ", ".join((prospect.get("industries") or [])[:3]) or "acquisitions"

    deal_lines = "\n".join(f"  • {_anonymize_deal(d)}" for d in sample_deals)
    if not deal_lines:
        deal_lines = "  • Various $1M-$10M EBITDA targets across home services, manufacturing, healthcare"

    firm_ref = f"At {firm}, you've built " if firm else "You've built "

    body = f"""Hi {name.split()[0] if name and name != 'there' else 'there'},

{firm_ref}a track record around {focus} — and right now we're sitting on a few off-market deals that look like they'd land in your wheelhouse.

A quick sample from this month's pipeline:

{deal_lines}

These are running through Madison Street Capital and a few private channels — most never hit BizBuySell or Axial. We share them with buyers who have a signed mandate on file, so we can move fast and respect the seller's confidentiality.

The agreement is a single page — no fee to sign, no obligation to bid. Once it's in, you get the live deal flow:

  → {BUYER_FORM_URL}

Worth a 10-minute call to walk you through what's active?

Best,
{BROKER_NAME}
{BROKER_COMPANY} · {BROKER_PHONE}
"""
    subject = f"Off-market deals in {focus.split(',')[0].strip()} — worth a look?"
    return {"subject": subject, "body": body}


def generate_buyer_recruitment_email(prospect: dict, all_deals: list) -> dict:
    """Main entry point. Picks 3 best sample deals and generates an email."""
    samples = _sample_deals_for_pitch(all_deals, max_n=3)
    return generate_recruitment_email_ai(prospect, samples)
