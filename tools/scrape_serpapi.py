"""
scrape_serpapi.py
-----------------
Uses SerpAPI (Google Search API) to find business-for-sale listings
from BizBuySell, BizQuest, and other sources — bypassing direct site IP blocks.

SerpAPI searches Google for listings matching industry + geography criteria,
then extracts structured data from the Google search snippets and organic results.

Cost: ~$0.01 per 100 searches (SerpAPI pricing). Targeting 5 states x 5 industry
categories = ~25 searches = $0.25 per run.

Requires: SERPAPI_KEY in .env (get at https://serpapi.com — free tier: 100 searches/mo)

Usage:
    python tools/scrape_serpapi.py --states FL TX GA NC SC --out .tmp/raw_listings_serpapi.json
    python tools/scrape_serpapi.py --states FL --industries "HVAC" "plumbing" --out .tmp/raw_listings_serpapi.json
"""

import argparse
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

SOURCE_ID = "serpapi"
SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# BizBuySell state listing URL templates for targeted Google searches
BIZBUYSELL_SITE = "bizbuysell.com"
BIZQUEST_SITE = "bizquest.com"

DEFAULT_INDUSTRIES = [
    "HVAC", "plumbing", "electrical", "home services",
    "landscaping", "roofing", "pest control", "cleaning",
    "auto repair", "manufacturing", "distribution", "construction",
    "service business", "ecommerce", "software", "healthcare",
]

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

DELAY = float(os.getenv("SCRAPER_DELAY_DEFAULT", "2"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_price(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.replace(",", "").strip()
    m = re.search(r'\$?(\d[\d.]*)\s*([MmKk]?)', raw)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    suf = m.group(2).upper()
    if suf == "M":
        val *= 1_000_000
    elif suf == "K":
        val *= 1_000
    return int(val)


def extract_financial(text: str, label: str) -> str | None:
    m = re.search(rf'{re.escape(label)}\s*:?\s*(\$[\d,.]+ ?[MmKk]?)', text, re.I)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# SerpAPI search
# ---------------------------------------------------------------------------

def search_google(query: str, num_results: int = 10) -> list[dict]:
    """Run a Google search via SerpAPI and return organic results."""
    if not SERPAPI_KEY or SERPAPI_KEY == "REPLACE_ME":
        print("[ERROR] SERPAPI_KEY not set in .env")
        return []

    params = {
        "engine": "google",
        "q": query,
        "num": num_results,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "gl": "us",
    }
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [WARN] SerpAPI request failed: {e}")
        return []

    return data.get("organic_results", [])


def parse_bbs_result(result: dict, state_code: str) -> dict | None:
    """Parse a BizBuySell search result snippet into a DealListing."""
    url = result.get("link", "")
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    full_text = f"{title} {snippet}"

    # Filter: must look like a listing page, not a category page
    if "/Business-Opportunity/" not in url and "/businesses-for-sale/" not in url.split("?")[0]:
        if not re.search(r'/\d{6,}', url):
            return None

    # Extract ID from URL
    id_m = re.search(r'/(\d{6,})', url)
    deal_id = f"bbs_{id_m.group(1)}" if id_m else f"bbs_{hash(url) & 0xFFFFFF}"

    # Parse financials from snippet
    price_raw = extract_financial(snippet, "Asking Price") or extract_financial(snippet, "Price")
    revenue_raw = extract_financial(snippet, "Revenue") or extract_financial(snippet, "Annual Revenue")
    cf_raw = extract_financial(snippet, "Cash Flow") or extract_financial(snippet, "SDE")

    # Parse location from title/snippet
    loc_m = re.search(r'([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})\b', full_text)
    location_city = loc_m.group(1).strip() if loc_m else ""
    location_state = state_code  # We know which state we searched for

    # Industry from title
    industry = ""
    industry_patterns = [
        r'(HVAC|Plumbing|Electrical|Landscaping|Roofing|Pest Control|Cleaning|'
        r'Auto Repair|Manufacturing|Distribution|Construction|Software|'
        r'Healthcare|Restaurant|Retail|Service)',
    ]
    for pat in industry_patterns:
        m = re.search(pat, title, re.I)
        if m:
            industry = m.group(1)
            break

    if not title or not url:
        return None

    return {
        "deal_id": deal_id,
        "source": "bizbuysell",
        "url": url,
        "title": title.replace(" - BizBuySell", "").replace(" | BizBuySell", "").strip(),
        "description": snippet,
        "industry": industry,
        "industry_category": industry,
        "location_city": location_city,
        "location_state": location_state,
        "asking_price": clean_price(price_raw),
        "asking_price_raw": price_raw or "",
        "annual_revenue": clean_price(revenue_raw),
        "annual_revenue_raw": revenue_raw or "",
        "cash_flow": clean_price(cf_raw),
        "cash_flow_raw": cf_raw or "",
        "ebitda": None,
        "sde": clean_price(cf_raw),
        "employees": None,
        "years_established": None,
        "reason_for_selling": None,
        "real_estate_included": None,
        "inventory_included": None,
        "sba_eligible": bool(re.search(r'sba', full_text, re.I)),
        "financing_available": bool(re.search(r'financ', full_text, re.I)),
        "broker_email": None,
        "broker_phone": None,
        "date_listed": None,
        "date_scraped": str(date.today()),
    }


def search_state(state_code: str, industries: list[str]) -> list[dict]:
    """Search Google for business listings in a given state across industry categories."""
    state_name = STATE_NAMES.get(state_code, state_code)
    listings = []
    seen_urls = set()

    # Strategy: Search by broad industry groups to get variety
    search_groups = [
        f"site:{BIZBUYSELL_SITE} {state_name} businesses for sale",
        f"site:{BIZBUYSELL_SITE} {state_name} service business for sale",
        f"site:{BIZBUYSELL_SITE} {state_name} construction business for sale",
        f"site:{BIZBUYSELL_SITE} {state_name} manufacturing business for sale",
    ]

    # Add specific industry searches
    for industry in industries[:4]:  # Limit to 4 to control API usage
        search_groups.append(
            f"site:{BIZBUYSELL_SITE} {state_name} {industry} business for sale"
        )

    for query in search_groups:
        print(f"  [serpapi] Search: {query[:70]}...")
        results = search_google(query, num_results=10)

        for r in results:
            url = r.get("link", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)

            listing = parse_bbs_result(r, state_code)
            if listing:
                listings.append(listing)

        time.sleep(DELAY)

    print(f"  [serpapi] {state_code}: found {len(listings)} listings")
    return listings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Search for listings via SerpAPI (Google)")
    parser.add_argument("--states", nargs="+", default=["FL", "TX", "GA", "NC", "SC"])
    parser.add_argument("--industries", nargs="+", default=None,
                        help="Industry keywords to include in searches")
    parser.add_argument("--out", default=".tmp/raw_listings_serpapi.json")
    args = parser.parse_args()

    if not SERPAPI_KEY or SERPAPI_KEY == "REPLACE_ME":
        print("[ERROR] SERPAPI_KEY not configured in .env")
        print("[INFO] Get a free API key at https://serpapi.com (100 free searches/month)")
        print("[INFO] Add: SERPAPI_KEY=your_key_here to .env")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    industries = args.industries or DEFAULT_INDUSTRIES[:6]

    all_listings = []
    for state in args.states:
        print(f"\n[SerpAPI] Searching {state}...")
        listings = search_state(state.upper(), industries)
        all_listings.extend(listings)

    # Deduplicate
    seen = set()
    deduped = [l for l in all_listings if not (l["deal_id"] in seen or seen.add(l["deal_id"]))]

    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\n[DONE] Wrote {len(deduped)} listings to {out_path}")
    print(f"[INFO] SerpAPI searches used: ~{len(args.states) * 8}")


if __name__ == "__main__":
    main()
