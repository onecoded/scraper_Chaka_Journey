"""
parse_buyers_pdf.py
--------------------
Extracts buyer criteria from the broker's PDF and writes structured
JSON to .tmp/buyers.json (or --out path).

Strategy 1: pdfplumber text extraction + regex section splitting
Strategy 2 (fallback): Send extracted text to Claude API for structured extraction

Usage:
    python tools/parse_buyers_pdf.py
    python tools/parse_buyers_pdf.py --pdf "BIZ BROKER MATCHES - buyers w agreements.pdf" --out .tmp/buyers.json
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INDUSTRY_KEYWORDS = [
    "HVAC", "plumbing", "electrical", "landscaping", "roofing", "pest control",
    "home services", "cleaning", "janitorial", "auto repair", "automotive",
    "manufacturing", "distribution", "logistics", "e-commerce", "ecommerce",
    "SaaS", "software", "technology", "healthcare", "medical", "dental",
    "restaurant", "food", "retail", "franchise", "construction", "contracting",
    "staffing", "accounting", "financial services", "insurance", "real estate",
    "childcare", "education", "fitness", "gym", "hotel", "hospitality",
    "transportation", "trucking", "laundry", "dry cleaning",
]

STATE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

ALL_STATE_CODES = set(STATE_MAP.values())


def extract_money(text: str) -> int | None:
    """Parse dollar amounts like $1.2M, $850K, $1,200,000 into integer."""
    if not text:
        return None
    text = text.replace(",", "").strip()
    m = re.search(r'\$?(\d[\d.]*)\s*([MmKk]?)', text)
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    suffix = m.group(2).upper()
    if suffix == "M":
        value *= 1_000_000
    elif suffix == "K":
        value *= 1_000
    return int(value)


def extract_states(text: str) -> list[str]:
    """Extract state abbreviations and full names from a block of text."""
    states = set()
    # 2-letter codes
    for code in re.findall(r'\b([A-Z]{2})\b', text):
        if code in ALL_STATE_CODES:
            states.add(code)
    # Full names
    text_lower = text.lower()
    for name, code in STATE_MAP.items():
        if name in text_lower:
            states.add(code)
    return sorted(states)


def extract_industries(text: str) -> list[str]:
    """Find known industry keywords in a text block."""
    found = []
    text_lower = text.lower()
    for kw in INDUSTRY_KEYWORDS:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def parse_price_range(text: str) -> tuple[int | None, int | None]:
    """Extract min/max price from patterns like '$500K - $2M' or 'up to $3M'."""
    # Range: $X to $Y or $X - $Y
    range_match = re.search(
        r'\$([\d.,]+[MmKk]?)\s*(?:to|-|–)\s*\$([\d.,]+[MmKk]?)', text
    )
    if range_match:
        return extract_money(range_match.group(1)), extract_money(range_match.group(2))
    # Up to / under / below / max
    max_match = re.search(
        r'(?:up to|under|below|max(?:imum)?)\s*\$([\d.,]+[MmKk]?)', text, re.I
    )
    if max_match:
        return None, extract_money(max_match.group(1))
    # At least / min
    min_match = re.search(
        r'(?:at least|min(?:imum)?|above|over)\s*\$([\d.,]+[MmKk]?)', text, re.I
    )
    if min_match:
        return extract_money(min_match.group(1)), None
    # Single value
    single = re.search(r'\$([\d.,]+[MmKk]?)', text)
    if single:
        val = extract_money(single.group(1))
        return None, val
    return None, None


def build_buyer_stub(idx: int) -> dict:
    """Return an empty buyer dict with schema-conformant defaults."""
    return {
        "buyer_id": f"buyer_{idx:03d}",
        "buyer_name": "",
        "company_name": "",
        "contact_email": "",
        "contact_phone": "",
        "agreement_type": "buyer_broker_agreement",
        "agreement_signed_date": "",
        "criteria": {
            "industry_preferences": [],
            "industry_exclusions": [],
            "geography_states": [],
            "financials": {
                "asking_price_min": None,
                "asking_price_max": None,
                "revenue_min": None,
                "revenue_max": None,
                "cash_flow_min": None,
                "cash_flow_max": None,
                "cash_flow_multiple_max": None,
                "revenue_multiple_max": None,
            },
            "deal_structure": {
                "seller_financing_ok": False,
                "sba_loan_preferred": False,
                "all_cash_ok": False,
                "real_estate_preferred": False,
            },
            "business_attributes": {
                "employees_min": None,
                "employees_max": None,
                "years_in_business_min": None,
                "absentee_owner_ok": False,
                "recurring_revenue_preferred": False,
            },
            "scoring_weights": {
                "industry_match": 30,
                "geography_match": 20,
                "financials_in_range": 25,
                "cash_flow_multiple": 10,
                "years_established": 8,
                "deal_structure": 7,
            },
        },
        "buyer_profile_summary": "",
        "notes": "",
        "raw_text": "",
    }


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract full text from PDF using pdfplumber."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages_text)


def split_into_buyer_sections(full_text: str) -> list[str]:
    """
    Split PDF text into per-buyer sections.

    Tries common delimiter patterns:
      - Numbered buyers: "Buyer 1", "BUYER 1", "1."
      - Name + agreement date header
      - Page breaks followed by a capitalized name line
    """
    # Pattern 1: explicit "BUYER N:" or "Buyer N" headers
    sections = re.split(r'\n(?=BUYER\s+\d+[\s:—])', full_text, flags=re.I)
    if len(sections) > 1:
        return [s.strip() for s in sections if s.strip()]

    # Pattern 2: numbered sections "1." at start of line with capital content
    sections = re.split(r'\n(?=\d+\.\s+[A-Z])', full_text)
    if len(sections) > 1:
        return [s.strip() for s in sections if s.strip()]

    # Pattern 3: page breaks as separators (one buyer per page)
    sections = full_text.split("--- PAGE BREAK ---")
    if len(sections) > 1:
        return [s.strip() for s in sections if len(s.strip()) > 100]

    # Fallback: treat entire document as one buyer
    return [full_text.strip()]


def regex_parse_section(section: str, idx: int) -> dict:
    """Extract buyer fields from a text section using regex patterns."""
    buyer = build_buyer_stub(idx)
    buyer["raw_text"] = section[:2000]  # Store first 2000 chars for reference

    # --- Name ---
    # Look for "Name:" label or first capitalized full name line
    name_match = re.search(r'(?:Name|Buyer)[\s:]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', section)
    if name_match:
        buyer["buyer_name"] = name_match.group(1).strip()
    else:
        # Try first line that looks like a name (2-4 capitalized words)
        first_name_line = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})$', section, re.M)
        if first_name_line:
            buyer["buyer_name"] = first_name_line.group(1).strip()

    # --- Company ---
    company_match = re.search(
        r'(?:Company|Entity|LLC|Inc|Corp|Group|Capital|Partners|Holdings)[\s:]+(.+?)(?:\n|$)',
        section, re.I
    )
    if company_match:
        buyer["company_name"] = company_match.group(1).strip()
    else:
        # Look for LLC/Inc/Corp/etc inline
        co_match = re.search(
            r'([A-Z][A-Za-z\s&,]+(?:LLC|Inc\.?|Corp\.?|Capital|Partners|Group|Holdings))',
            section
        )
        if co_match:
            buyer["company_name"] = co_match.group(1).strip()

    # --- Email ---
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', section)
    if email_match:
        buyer["contact_email"] = email_match.group(0)

    # --- Phone ---
    phone_match = re.search(r'(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}', section)
    if phone_match:
        buyer["contact_phone"] = phone_match.group(0)

    # --- Agreement date ---
    date_match = re.search(r'(?:signed|agreement|dated?)[\s:]+(\w+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{2,4})', section, re.I)
    if date_match:
        buyer["agreement_signed_date"] = date_match.group(1).strip()

    # --- Industries ---
    buyer["criteria"]["industry_preferences"] = extract_industries(section)

    # --- Geography ---
    buyer["criteria"]["geography_states"] = extract_states(section)

    # --- Financials: asking price ---
    price_section = ""
    price_label = re.search(
        r'(?:asking price|purchase price|deal size|price range)[\s:]+(.{0,100})',
        section, re.I
    )
    if price_label:
        price_section = price_label.group(1)
    p_min, p_max = parse_price_range(price_section or section[:500])
    buyer["criteria"]["financials"]["asking_price_min"] = p_min
    buyer["criteria"]["financials"]["asking_price_max"] = p_max

    # --- Financials: revenue ---
    rev_label = re.search(
        r'(?:annual revenue|revenue|sales)[\s:]+(.{0,100})',
        section, re.I
    )
    if rev_label:
        r_min, r_max = parse_price_range(rev_label.group(1))
        buyer["criteria"]["financials"]["revenue_min"] = r_min
        buyer["criteria"]["financials"]["revenue_max"] = r_max

    # --- Financials: cash flow / SDE / EBITDA ---
    cf_label = re.search(
        r'(?:cash flow|SDE|seller.s discretionary|EBITDA)[\s:]+(.{0,100})',
        section, re.I
    )
    if cf_label:
        cf_min, cf_max = parse_price_range(cf_label.group(1))
        buyer["criteria"]["financials"]["cash_flow_min"] = cf_min
        buyer["criteria"]["financials"]["cash_flow_max"] = cf_max

    # --- Deal structure ---
    if re.search(r'SBA|sba loan', section, re.I):
        buyer["criteria"]["deal_structure"]["sba_loan_preferred"] = True
    if re.search(r'seller financ|owner financ|seller carry', section, re.I):
        buyer["criteria"]["deal_structure"]["seller_financing_ok"] = True
    if re.search(r'all.cash|cash only|no financing', section, re.I):
        buyer["criteria"]["deal_structure"]["all_cash_ok"] = True

    # --- Business attributes ---
    emp_match = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)\s*employee', section, re.I)
    if emp_match:
        buyer["criteria"]["business_attributes"]["employees_min"] = int(emp_match.group(1))
        buyer["criteria"]["business_attributes"]["employees_max"] = int(emp_match.group(2))

    yrs_match = re.search(r'(\d+)\+?\s*years?\s*(?:in business|established|operating)', section, re.I)
    if yrs_match:
        buyer["criteria"]["business_attributes"]["years_in_business_min"] = int(yrs_match.group(1))

    if re.search(r'recurring revenue|subscription|contract', section, re.I):
        buyer["criteria"]["business_attributes"]["recurring_revenue_preferred"] = True

    # --- Profile summary: first substantial paragraph ---
    paragraphs = [p.strip() for p in section.split('\n\n') if len(p.strip()) > 60]
    if paragraphs:
        buyer["buyer_profile_summary"] = paragraphs[0][:500]

    return buyer


# ---------------------------------------------------------------------------
# Claude API fallback
# ---------------------------------------------------------------------------

def claude_parse_section(section: str, idx: int) -> dict:
    """Use Claude API to extract buyer criteria when regex yields sparse results."""
    try:
        import anthropic
    except ImportError:
        print("[WARN] anthropic not installed, skipping Claude fallback")
        return build_buyer_stub(idx)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "sk-ant-REPLACE_ME":
        print("[WARN] ANTHROPIC_API_KEY not set, skipping Claude fallback")
        return build_buyer_stub(idx)

    client = anthropic.Anthropic(api_key=api_key)

    schema_example = json.dumps({
        "buyer_name": "string",
        "company_name": "string",
        "contact_email": "string",
        "contact_phone": "string",
        "agreement_signed_date": "string",
        "industry_preferences": ["list of industry strings"],
        "industry_exclusions": ["list of industry strings"],
        "geography_states": ["list of 2-letter state codes"],
        "asking_price_min": "integer or null",
        "asking_price_max": "integer or null",
        "revenue_min": "integer or null",
        "revenue_max": "integer or null",
        "cash_flow_min": "integer or null",
        "cash_flow_multiple_max": "number or null",
        "sba_loan_preferred": "boolean",
        "seller_financing_ok": "boolean",
        "all_cash_ok": "boolean",
        "years_in_business_min": "integer or null",
        "employees_min": "integer or null",
        "employees_max": "integer or null",
        "recurring_revenue_preferred": "boolean",
        "buyer_profile_summary": "string",
        "notes": "string"
    }, indent=2)

    prompt = f"""Extract buyer criteria from this business broker document section.
Return ONLY valid JSON matching this schema (no explanation, no markdown):

{schema_example}

DOCUMENT SECTION:
{section[:3000]}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-3-5-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[WARN] Claude parse failed: {e}")
        return build_buyer_stub(idx)

    # Map flat Claude response back to nested buyer schema
    buyer = build_buyer_stub(idx)
    buyer["buyer_name"] = parsed.get("buyer_name", "")
    buyer["company_name"] = parsed.get("company_name", "")
    buyer["contact_email"] = parsed.get("contact_email", "")
    buyer["contact_phone"] = parsed.get("contact_phone", "")
    buyer["agreement_signed_date"] = parsed.get("agreement_signed_date", "")
    buyer["criteria"]["industry_preferences"] = parsed.get("industry_preferences", [])
    buyer["criteria"]["industry_exclusions"] = parsed.get("industry_exclusions", [])
    buyer["criteria"]["geography_states"] = parsed.get("geography_states", [])
    buyer["criteria"]["financials"]["asking_price_min"] = parsed.get("asking_price_min")
    buyer["criteria"]["financials"]["asking_price_max"] = parsed.get("asking_price_max")
    buyer["criteria"]["financials"]["revenue_min"] = parsed.get("revenue_min")
    buyer["criteria"]["financials"]["revenue_max"] = parsed.get("revenue_max")
    buyer["criteria"]["financials"]["cash_flow_min"] = parsed.get("cash_flow_min")
    buyer["criteria"]["financials"]["cash_flow_multiple_max"] = parsed.get("cash_flow_multiple_max")
    buyer["criteria"]["deal_structure"]["sba_loan_preferred"] = parsed.get("sba_loan_preferred", False)
    buyer["criteria"]["deal_structure"]["seller_financing_ok"] = parsed.get("seller_financing_ok", False)
    buyer["criteria"]["deal_structure"]["all_cash_ok"] = parsed.get("all_cash_ok", False)
    buyer["criteria"]["business_attributes"]["years_in_business_min"] = parsed.get("years_in_business_min")
    buyer["criteria"]["business_attributes"]["employees_min"] = parsed.get("employees_min")
    buyer["criteria"]["business_attributes"]["employees_max"] = parsed.get("employees_max")
    buyer["criteria"]["business_attributes"]["recurring_revenue_preferred"] = parsed.get("recurring_revenue_preferred", False)
    buyer["buyer_profile_summary"] = parsed.get("buyer_profile_summary", "")
    buyer["notes"] = parsed.get("notes", "")
    buyer["raw_text"] = section[:2000]
    return buyer


def is_sparse(buyer: dict) -> bool:
    """Return True if regex parse yielded very little useful data."""
    has_name = bool(buyer.get("buyer_name"))
    has_industries = bool(buyer["criteria"]["industry_preferences"])
    has_states = bool(buyer["criteria"]["geography_states"])
    has_price = buyer["criteria"]["financials"]["asking_price_max"] is not None
    fields_found = sum([has_name, has_industries, has_states, has_price])
    return fields_found < 2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Parse buyer criteria from broker PDF")
    parser.add_argument(
        "--pdf",
        default=os.getenv("PDF_PATH", "BIZ BROKER MATCHES - buyers w agreements.pdf"),
        help="Path to the PDF file"
    )
    parser.add_argument(
        "--out",
        default=os.getenv("BUYERS_JSON_PATH", ".tmp/buyers.json"),
        help="Output JSON path"
    )
    parser.add_argument(
        "--force-claude",
        action="store_true",
        help="Always use Claude API (skip regex parse)"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        # Try relative to project root (one dir up from tools/)
        alt = Path(__file__).parent.parent / args.pdf
        if alt.exists():
            pdf_path = alt
        else:
            print(f"[ERROR] PDF not found: {args.pdf}")
            sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Extracting text from: {pdf_path}")
    full_text = extract_text_from_pdf(str(pdf_path))
    print(f"[INFO] Extracted {len(full_text)} characters")

    sections = split_into_buyer_sections(full_text)
    print(f"[INFO] Found {len(sections)} buyer section(s)")

    buyers = []
    for i, section in enumerate(sections, start=1):
        print(f"\n[INFO] Parsing buyer {i}/{len(sections)}...")

        if args.force_claude:
            buyer = claude_parse_section(section, i)
            source = "claude"
        else:
            buyer = regex_parse_section(section, i)
            if is_sparse(buyer):
                print(f"[INFO] Sparse regex result for buyer {i}, trying Claude fallback...")
                buyer = claude_parse_section(section, i)
                source = "claude-fallback"
            else:
                source = "regex"

        buyer["_parse_source"] = source
        buyers.append(buyer)
        print(f"  Name: {buyer['buyer_name'] or '(unknown)'}")
        print(f"  Industries: {buyer['criteria']['industry_preferences']}")
        print(f"  States: {buyer['criteria']['geography_states']}")
        print(f"  Price max: {buyer['criteria']['financials']['asking_price_max']}")
        print(f"  Parse source: {source}")

    out_path.write_text(json.dumps(buyers, indent=2))
    print(f"\n[DONE] Wrote {len(buyers)} buyer(s) to {out_path}")
    print(f"[INFO] IMPORTANT: Review {out_path} and manually correct any errors before running the pipeline.")


if __name__ == "__main__":
    main()
