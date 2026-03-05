"""
scrape_bizbuysell.py
--------------------
Scrapes business-for-sale listings from BizBuySell.com.

BizBuySell is protected by Akamai bot detection, so this scraper uses
Playwright (real Chromium browser) to bypass fingerprinting.

URL pattern: https://www.bizbuysell.com/{state}-businesses-for-sale/{page}/

IMPORTANT: If selectors stop working, inspect the live HTML with browser DevTools
and update the SELECTORS dict below. Document changes in workflows/scrape_listings.md.

Usage:
    python tools/scrape_bizbuysell.py --states FL TX GA --max-pages 5 --out .tmp/raw_listings_bizbuysell.json
    python tools/scrape_bizbuysell.py  # uses defaults from .env
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Use Playwright for bot-protected sites
sys.path.insert(0, str(Path(__file__).parent))
from _browser import fetch_pages_sync

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.bizbuysell.com"
SOURCE_ID = "bizbuysell"

STATE_SLUGS = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
    "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
    "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia",
    "WI": "wisconsin", "WY": "wyoming",
}

# Update these selectors if the site redesigns. Inspect via browser DevTools.
SELECTORS = {
    "listing_card":  "div.listing-result",
    "title":         "h3.title a, h2.title a",
    "price":         "span.price, .asking-price",
    "location":      "p.location, .location",
    "category":      "p.category, .category",
    "description":   "p.description, .listing-description",
    "revenue":       None,   # Often inside a data list — parsed from text
    "cash_flow":     None,   # Same — parsed from description/data labels
    "pagination_next": "a[rel='next'], .pagination .next a",
}

DELAY = float(os.getenv("SCRAPER_DELAY_BIZBUYSELL", "2"))

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def clean_price(raw: str | None) -> int | None:
    """Convert raw price string to integer. '$1.2M' -> 1200000."""
    if not raw:
        return None
    raw = raw.replace(",", "").strip()
    m = re.search(r'\$?([\d.]+)\s*([MmKkBb]?)', raw)
    if not m:
        return None
    value = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "M":
        value *= 1_000_000
    elif suffix in ("K",):
        value *= 1_000
    elif suffix == "B":
        value *= 1_000_000_000
    return int(value)


def extract_financial_from_text(text: str, label: str) -> str | None:
    """
    Extract a financial value by label from listing text.
    e.g., extract_financial_from_text(text, "Cash Flow") -> "$220,000"
    """
    pattern = rf'(?:{re.escape(label)})\s*:?\s*(\$[\d,.]+ ?[MmKk]?)'
    m = re.search(pattern, text, re.I)
    return m.group(1).strip() if m else None


def extract_listing_id(url: str) -> str:
    """Extract a stable ID from the listing URL path."""
    # e.g. /Business-Opportunity/1234567/ -> 1234567
    m = re.search(r'/(\d{6,})', url)
    return m.group(1) if m else re.sub(r'[^a-z0-9]', '_', url[-30:])


def parse_card(card, state_code: str) -> dict | None:
    """Parse a single listing card into a normalized DealListing dict."""
    # Title + URL
    title_el = card.select_one(SELECTORS["title"])
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    rel_url = title_el.get("href", "")
    url = urljoin(BASE_URL, rel_url) if rel_url else ""
    deal_id = f"{SOURCE_ID}_{extract_listing_id(url)}" if url else ""

    # Price
    price_el = card.select_one(SELECTORS["price"])
    price_raw = price_el.get_text(strip=True) if price_el else ""

    # Location
    loc_el = card.select_one(SELECTORS["location"])
    location_text = loc_el.get_text(strip=True) if loc_el else ""
    loc_parts = [p.strip() for p in location_text.split(",")]
    location_city = loc_parts[0] if loc_parts else ""
    location_state = state_code  # confirmed from the URL we scraped

    # Category / industry
    cat_el = card.select_one(SELECTORS["category"])
    industry = cat_el.get_text(strip=True) if cat_el else ""

    # Description
    desc_el = card.select_one(SELECTORS["description"])
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Try to find revenue + cash flow from the card's full text
    full_text = card.get_text(" ", strip=True)
    revenue_raw = (
        extract_financial_from_text(full_text, "Annual Revenue") or
        extract_financial_from_text(full_text, "Gross Revenue") or
        extract_financial_from_text(full_text, "Revenue")
    )
    cf_raw = (
        extract_financial_from_text(full_text, "Cash Flow") or
        extract_financial_from_text(full_text, "SDE") or
        extract_financial_from_text(full_text, "Net Income")
    )

    # SBA / financing mentions
    sba_eligible = bool(re.search(r'sba', full_text, re.I))
    financing_available = bool(re.search(r'financing|seller financ|owner financ', full_text, re.I))

    return {
        "deal_id": deal_id,
        "source": SOURCE_ID,
        "url": url,
        "title": title,
        "description": description,
        "industry": industry,
        "industry_category": industry,
        "location_city": location_city,
        "location_state": location_state,
        "asking_price": clean_price(price_raw),
        "asking_price_raw": price_raw,
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
        "sba_eligible": sba_eligible,
        "financing_available": financing_available,
        "broker_email": None,
        "broker_phone": None,
        "date_listed": None,
        "date_scraped": str(date.today()),
    }


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def build_url(state_slug: str, page: int) -> str:
    base = f"{BASE_URL}/{state_slug}-businesses-for-sale"
    return base + "/" if page == 1 else f"{base}/{page}/"


def scrape_state(state_code: str, max_pages: int) -> list[dict]:
    state_slug = STATE_SLUGS.get(state_code.upper())
    if not state_slug:
        print(f"[WARN] Unknown state code: {state_code}")
        return []

    # Build list of URLs to fetch
    urls = [build_url(state_slug, page) for page in range(1, max_pages + 1)]

    print(f"  [{SOURCE_ID}] {state_code}: fetching {len(urls)} pages via Playwright...")
    page_results = fetch_pages_sync(
        urls,
        delay=DELAY,
        wait_selector=SELECTORS["listing_card"],
    )

    results = []
    for url, html in page_results:
        if not html:
            print(f"  [WARN] Empty response for {url}")
            continue

        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(SELECTORS["listing_card"])

        if not cards:
            # Try broader selector
            cards = soup.select("div[class*='listing']")

        if not cards:
            debug_path = Path(".tmp") / f"debug_bbs_{state_code}.html"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(html[:50000], encoding="utf-8")
            print(f"  [DEBUG] No cards found. HTML saved to {debug_path}")
            continue

        page_listings = []
        for card in cards:
            listing = parse_card(card, state_code)
            if listing:
                page_listings.append(listing)

        results.extend(page_listings)
        print(f"  [OK] {url} -> {len(page_listings)} listings ({len(results)} total)")

    return results


def main():
    parser = argparse.ArgumentParser(description="Scrape BizBuySell business listings")
    parser.add_argument(
        "--states",
        nargs="+",
        default=["FL", "TX", "GA", "NC", "SC"],
        help="State codes to scrape (e.g. FL TX GA)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=int(os.getenv("SCRAPER_MAX_PAGES_DEFAULT", "5")),
        help="Max pages per state"
    )
    parser.add_argument(
        "--out",
        default=".tmp/raw_listings_bizbuysell.json",
        help="Output JSON path"
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_listings = []
    for state in args.states:
        print(f"\n[BizBuySell] Scraping {state}...")
        listings = scrape_state(state.upper(), args.max_pages)
        all_listings.extend(listings)
        print(f"[BizBuySell] {state}: {len(listings)} listings")

    # Deduplicate by deal_id
    seen = set()
    deduped = []
    for l in all_listings:
        if l["deal_id"] not in seen:
            seen.add(l["deal_id"])
            deduped.append(l)

    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\n[DONE] Wrote {len(deduped)} listings to {out_path}")


if __name__ == "__main__":
    main()
