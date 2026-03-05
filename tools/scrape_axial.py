"""
scrape_axial.py
---------------
Axial is a private M&A network — it has NO public listings.
Web scraping Axial violates their Terms of Service and would result in account termination.

This tool is a STUB that returns an empty list with integration instructions.

PHASE 2 INTEGRATION (Email-based):
Axial sends deal alert emails to registered buyers/intermediaries when matching deals
are posted. To integrate:

1. Register on Axial as a sell-side or buy-side intermediary at https://www.axial.net
2. Create a Gmail label "axial-deals" and set up a filter to apply it to Axial emails
3. Enable the Gmail API and download credentials.json
4. Run with --gmail-mode to parse forwarded Axial emails from the label

For now, if you receive Axial deal alerts by email, forward relevant ones to the
monitored Gmail label and note the key details in .tmp/axial_manual.json using the
template at the bottom of this file.

Usage:
    python tools/scrape_axial.py --out .tmp/raw_listings_axial.json
    python tools/scrape_axial.py --gmail-mode --label axial-deals --out .tmp/raw_listings_axial.json  [PHASE 2]
"""

import argparse
import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SOURCE_ID = "axial"

MANUAL_TEMPLATE = {
    "deal_id": "axial_REPLACE_WITH_DEAL_ID",
    "source": "axial",
    "url": "",
    "title": "Business name or deal title from Axial email",
    "description": "Copy relevant description from the Axial deal alert email",
    "industry": "e.g. HVAC, Manufacturing, Software",
    "industry_category": "",
    "location_city": "",
    "location_state": "2-letter state code",
    "asking_price": None,
    "asking_price_raw": "$X.XM",
    "annual_revenue": None,
    "annual_revenue_raw": "$X.XM",
    "cash_flow": None,
    "cash_flow_raw": "$XXXk EBITDA",
    "ebitda": None,
    "sde": None,
    "employees": None,
    "years_established": None,
    "reason_for_selling": None,
    "real_estate_included": None,
    "inventory_included": None,
    "sba_eligible": None,
    "financing_available": None,
    "broker_email": "",
    "broker_phone": "",
    "date_listed": "",
    "date_scraped": str(date.today()),
}


def load_manual_entries(manual_path: Path) -> list[dict]:
    """Load manually entered Axial deals from .tmp/axial_manual.json if it exists."""
    if not manual_path.exists():
        return []
    try:
        data = json.loads(manual_path.read_text())
        if isinstance(data, list):
            return [d for d in data if d.get("deal_id") != "axial_REPLACE_WITH_DEAL_ID"]
        return []
    except Exception as e:
        print(f"[WARN] Could not load {manual_path}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Axial deal integration (stub + manual entry)")
    parser.add_argument("--out", default=".tmp/raw_listings_axial.json")
    parser.add_argument(
        "--gmail-mode",
        action="store_true",
        help="[PHASE 2] Parse Axial deal alert emails from Gmail"
    )
    parser.add_argument("--label", default=os.getenv("GMAIL_AXIAL_LABEL", "axial-deals"))
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manual_path = Path(".tmp/axial_manual.json")

    if args.gmail_mode:
        print("[Axial] Gmail mode not yet implemented (Phase 2).")
        print("[Axial] To implement: use Gmail API to read emails with label 'axial-deals'")
        print("[Axial] Parse HTML email bodies using BeautifulSoup to extract deal details.")

    # Load any manually entered deals
    manual_entries = load_manual_entries(manual_path)
    if manual_entries:
        print(f"[Axial] Loaded {len(manual_entries)} manually entered deals from {manual_path}")
    else:
        print(f"[Axial] No manual Axial deals found.")
        print(f"[Axial] To add deals manually:")
        print(f"        1. Create .tmp/axial_manual.json with an array of deal objects")
        print(f"        2. Use this template: .tmp/axial_template.json")

        # Write the template for reference
        template_path = Path(".tmp/axial_template.json")
        template_path.write_text(json.dumps([MANUAL_TEMPLATE], indent=2))
        print(f"[Axial] Template written to {template_path}")

    out_path.write_text(json.dumps(manual_entries, indent=2))
    print(f"[DONE] Wrote {len(manual_entries)} Axial listings to {out_path}")


if __name__ == "__main__":
    main()
