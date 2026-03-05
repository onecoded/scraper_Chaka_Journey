"""
generate_emails.py
------------------
Generates personalized seller outreach email drafts using the Claude API.

The email is FROM the broker (Jordi / Valar Brokers) TO the listing broker or seller.
Goal: excite the seller that a qualified, motivated buyer exists who is a strong fit.

Only generates emails for matches scoring >= MIN_EMAIL_SCORE (default: 60, B grade+).
Uses Claude Haiku for cost efficiency. Switch to Sonnet for A-grade deals.

Usage:
    python tools/generate_emails.py
    python tools/generate_emails.py --matches .tmp/matches.json --buyers .tmp/buyers.json --listings .tmp/all_listings.json --out .tmp/email_drafts.json --min-score 60
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Broker config (from .env)
# ---------------------------------------------------------------------------

BROKER_NAME = os.getenv("BROKER_NAME", "Jordi Quevedo-Valls")
BROKER_COMPANY = os.getenv("BROKER_COMPANY", "Valar Brokers")
BROKER_LINKEDIN = os.getenv("BROKER_LINKEDIN", "")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are {BROKER_NAME}, a business broker at {BROKER_COMPANY}.
You are writing outreach emails to sellers and their listing brokers about a specific,
qualified buyer you represent who is a strong match for their business.

Your emails:
- Sound personal and human, NOT like a template
- Reference specific details about the listing (location, industry, key financials)
- Lead with the buyer's single strongest qualification for THIS deal
- Create genuine excitement without hype or pressure
- Are professional, confident, and to the point
- Are 180-250 words in the body (not counting subject line)
- End with a low-friction CTA: a 15-minute call, not a formal meeting request
- Never open with "I hope this email finds you well" or "I'm excited to..."
- Never use the words "reach out", "circle back", "touch base", or "synergy"
- Protect buyer privacy — share profile summary strategically, not their exact financials

Format your response as:
SUBJECT: [subject line under 60 characters]

BODY:
[email body]"""


def buyer_financing_summary(buyer: dict) -> str:
    ds = buyer["criteria"].get("deal_structure", {})
    parts = []
    if ds.get("sba_loan_preferred"):
        parts.append("SBA loan preferred")
    if ds.get("seller_financing_ok"):
        parts.append("open to seller financing")
    if ds.get("all_cash_ok"):
        parts.append("all-cash capable")
    return ", ".join(parts) if parts else "flexible on structure"


def build_user_prompt(match: dict, buyer: dict, deal: dict) -> str:
    """Build the per-match prompt with all deal and buyer details."""

    score_highlights = []
    for dim, data in match.get("score_breakdown", {}).items():
        if data["score"] >= data["max"] * 0.7:
            score_highlights.append(data["reason"])

    buyer_notes = buyer.get("notes", "")
    buyer_summary = buyer.get("buyer_profile_summary", "")

    return f"""Write an outreach email from broker to the listing broker or seller.

LISTING DETAILS:
- Business name/title: {deal.get('title', 'Not listed')}
- Location: {deal.get('location_city', '')}, {deal.get('location_state', '')}
- Industry: {deal.get('industry', 'Not specified')}
- Asking Price: {deal.get('asking_price_raw') or 'Not listed'}
- Annual Revenue: {deal.get('annual_revenue_raw') or 'Not listed'}
- Cash Flow / SDE: {deal.get('cash_flow_raw') or 'Not listed'}
- Reason for Selling: {deal.get('reason_for_selling') or 'Not stated'}
- SBA Eligible: {'Yes' if deal.get('sba_eligible') else 'Not confirmed'}
- Seller Financing: {'Available' if deal.get('financing_available') else 'Not stated'}
- Description: {str(deal.get('description', ''))[:400]}
- Source: {deal.get('source', '')} | URL: {deal.get('url', '')}

BUYER PROFILE (use strategically — do not share exact net worth or loan amount):
- Profile: {buyer_summary}
- Additional context: {buyer_notes}
- Financing approach: {buyer_financing_summary(buyer)}
- Has signed buyer-broker agreement: Yes
- Match score: {match.get('score_pct', 0)}% ({match.get('grade', '')}-grade match)

WHY THIS IS A STRONG MATCH:
{chr(10).join(f'- {h}' for h in score_highlights[:3])}

Write the email now. Be specific. Be human."""


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def generate_email(match: dict, buyer: dict, deal: dict, client: anthropic.Anthropic, model: str) -> dict:
    """Call Claude to generate a single email draft. Returns the draft dict."""
    prompt = build_user_prompt(match, buyer, deal)

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.RateLimitError:
        print("  [WARN] Rate limited by Anthropic API, waiting 30s...")
        time.sleep(30)
        msg = client.messages.create(
            model=model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

    raw = msg.content[0].text.strip()
    tokens_used = msg.usage.input_tokens + msg.usage.output_tokens

    # Parse subject and body from Claude's response
    subject = ""
    body = ""
    if "SUBJECT:" in raw:
        lines = raw.split("\n")
        subject_line = next((l for l in lines if l.startswith("SUBJECT:")), "")
        subject = subject_line.replace("SUBJECT:", "").strip()
        body_start = raw.find("BODY:")
        if body_start >= 0:
            body = raw[body_start + 5:].strip()
        else:
            # Body is everything after the subject line
            body = "\n".join(l for l in lines if not l.startswith("SUBJECT:")).strip()
    else:
        # Fallback: treat first line as subject, rest as body
        lines = raw.split("\n", 1)
        subject = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else raw

    return {
        "match_id": match["match_id"],
        "buyer_id": match["buyer_id"],
        "buyer_name": match.get("buyer_name", ""),
        "deal_id": match["deal_id"],
        "deal_title": match.get("deal_title", ""),
        "deal_url": match.get("deal_url", ""),
        "deal_source": match.get("deal_source", ""),
        "deal_location": match.get("deal_location", ""),
        "score_pct": match.get("score_pct", 0),
        "grade": match.get("grade", ""),
        "subject": subject,
        "body": body,
        "broker_name": BROKER_NAME,
        "broker_company": BROKER_COMPANY,
        "model_used": model,
        "tokens_used": tokens_used,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate seller outreach email drafts")
    parser.add_argument("--matches", default=".tmp/matches.json")
    parser.add_argument("--buyers", default=os.getenv("BUYERS_JSON_PATH", ".tmp/buyers.json"))
    parser.add_argument("--listings", default=".tmp/all_listings.json")
    parser.add_argument("--out", default=".tmp/email_drafts.json")
    parser.add_argument(
        "--min-score",
        type=float,
        default=float(os.getenv("MIN_EMAIL_SCORE", "60")),
        help="Only generate emails for matches above this score threshold"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("EMAIL_MODEL", "claude-haiku-3-5-20241022"),
        help="Claude model to use"
    )
    parser.add_argument(
        "--upgrade-a-grade",
        action="store_true",
        help="Use claude-sonnet-4-5-20250929 for A-grade matches (80+ score)"
    )
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "sk-ant-REPLACE_ME":
        print("[ERROR] ANTHROPIC_API_KEY not set in .env")
        return

    matches_path = Path(args.matches)
    buyers_path = Path(args.buyers)
    listings_path = Path(args.listings)
    out_path = Path(args.out)

    if not matches_path.exists():
        print(f"[ERROR] Matches file not found: {matches_path}")
        return
    if not buyers_path.exists():
        print(f"[ERROR] Buyers file not found: {buyers_path}")
        return
    if not listings_path.exists():
        print(f"[ERROR] Listings file not found: {listings_path}")
        return

    matches = json.loads(matches_path.read_text())
    buyers = json.loads(buyers_path.read_text())
    listings = json.loads(listings_path.read_text())

    # Build lookup dicts
    buyer_lookup = {b["buyer_id"]: b for b in buyers}
    listing_lookup = {l["deal_id"]: l for l in listings}

    # Filter matches by score threshold
    eligible = [m for m in matches if m.get("score_pct", 0) >= args.min_score]
    print(f"[INFO] {len(eligible)} matches eligible for email generation (score >= {args.min_score}%)")

    if not eligible:
        print("[INFO] No eligible matches. Lower --min-score or run matching first.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=api_key)

    email_drafts = []
    total_tokens = 0

    for i, match in enumerate(eligible, 1):
        buyer = buyer_lookup.get(match["buyer_id"])
        deal = listing_lookup.get(match["deal_id"])

        if not buyer or not deal:
            print(f"  [WARN] Missing buyer or deal data for match {match['match_id']}, skipping")
            continue

        # Choose model: upgrade A-grade matches to Sonnet if flag set
        model = args.model
        if args.upgrade_a_grade and match.get("grade") == "A":
            model = "claude-sonnet-4-5-20250929"

        print(f"  [{i}/{len(eligible)}] {match.get('grade')}-grade | "
              f"{match.get('score_pct')}% | {deal.get('title', '')[:50]} → {buyer.get('buyer_name', '')}")

        draft = generate_email(match, buyer, deal, client, model)
        email_drafts.append(draft)
        total_tokens += draft["tokens_used"]

        # Small delay to avoid rate limits
        if i % 10 == 0:
            time.sleep(2)

    out_path.write_text(json.dumps(email_drafts, indent=2))

    # Rough cost estimate (Haiku: ~$0.80 per MTok input, $4 output)
    approx_cost = (total_tokens / 1_000_000) * 2.0
    print(f"\n[DONE] Generated {len(email_drafts)} email drafts")
    print(f"[INFO] Total tokens used: {total_tokens:,} (~${approx_cost:.2f})")
    print(f"[INFO] Drafts written to {out_path}")
    print(f"[INFO] Review drafts before sending. Edit subject/body as needed.")


if __name__ == "__main__":
    main()
