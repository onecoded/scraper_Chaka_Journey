"""
scrape_loopnet.py
-----------------
Scrapes business-for-sale listings from LoopNet's /biz/ section.
LoopNet is a CoStar product with aggressive bot detection.

Safety measures:
- 3-5 second delays between requests
- Realistic headers including Referer
- 403 errors handled gracefully (log and skip, don't crash)
- HTML saved to .tmp/debug_loopnet_*.html if selectors fail

IMPORTANT: LoopNet may block this scraper. If you get consistent 403s:
1. Try increasing SCRAPER_DELAY_LOOPNET in .env
2. Check if the site structure has changed
3. Consider manual data entry for LoopNet matches

URL: https://www.loopnet.com/biz/{state}-businesses-for-sale/

Usage:
    python tools/scrape_loopnet.py --states FL TX GA NC SC --max-pages 3 --out .tmp/raw_listings_loopnet.json
"""

import argparse
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import sys
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from _browser import fetch_pages_sync

load_dotenv()

SOURCE_ID = "loopnet"
BASE_URL = "https://www.loopnet.com"

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

# Update if site redesigns — inspect HTML with browser DevTools
SELECTORS = {
    "listing_card":    "div.c-listing-card, article.c-listing-card, div[data-testid='listing-card']",
    "title":           ".c-listing-card__title a, h3 a, h2 a",
    "price":           ".c-listing-card__price, .listing-price",
    "location":        ".c-listing-card__location, .listing-location",
    "category":        ".c-listing-card__category, .listing-category",
    "description":     ".c-listing-card__description, .listing-description",
    "pagination_next": "a[rel='next'], .pagination-next a",
}

DELAY = float(os.getenv("SCRAPER_DELAY_LOOPNET", "4"))


def clean_price(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.replace(",", "").strip()
    m = re.search(r'\$?([\d.]+)\s*([MmKk]?)', raw)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2).upper()
    if suf == "M":
        val *= 1_000_000
    elif suf == "K":
        val *= 1_000
    return int(val)


def extract_financial_from_text(text: str, label: str) -> str | None:
    m = re.search(rf'{re.escape(label)}\s*:?\s*(\$[\d,.]+ ?[MmKk]?)', text, re.I)
    return m.group(1).strip() if m else None


def extract_listing_id(url: str) -> str:
    m = re.search(r'/(\d{5,})', url)
    return m.group(1) if m else re.sub(r'[^a-z0-9]', '_', url[-30:])


def parse_card(card, state_code: str) -> dict | None:
    title_el = card.select_one(SELECTORS["title"])
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    rel_url = title_el.get("href", "")
    url = urljoin(BASE_URL, rel_url) if rel_url else ""
    deal_id = f"{SOURCE_ID}_{extract_listing_id(url)}" if url else ""

    price_el = card.select_one(SELECTORS["price"])
    price_raw = price_el.get_text(strip=True) if price_el else ""

    loc_el = card.select_one(SELECTORS["location"])
    location_text = loc_el.get_text(strip=True) if loc_el else ""
    loc_parts = [p.strip() for p in location_text.split(",")]
    location_city = loc_parts[0] if loc_parts else ""

    cat_el = card.select_one(SELECTORS["category"])
    industry = cat_el.get_text(strip=True) if cat_el else ""

    desc_el = card.select_one(SELECTORS["description"])
    description = desc_el.get_text(strip=True) if desc_el else ""

    full_text = card.get_text(" ", strip=True)
    revenue_raw = (
        extract_financial_from_text(full_text, "Annual Revenue") or
        extract_financial_from_text(full_text, "Revenue")
    )
    cf_raw = (
        extract_financial_from_text(full_text, "Cash Flow") or
        extract_financial_from_text(full_text, "EBITDA") or
        extract_financial_from_text(full_text, "SDE")
    )

    return {
        "deal_id": deal_id,
        "source": SOURCE_ID,
        "url": url,
        "title": title,
        "description": description,
        "industry": industry,
        "industry_category": industry,
        "location_city": location_city,
        "location_state": state_code,
        "asking_price": clean_price(price_raw),
        "asking_price_raw": price_raw,
        "annual_revenue": clean_price(revenue_raw),
        "annual_revenue_raw": revenue_raw or "",
        "cash_flow": clean_price(cf_raw),
        "cash_flow_raw": cf_raw or "",
        "ebitda": clean_price(cf_raw) if cf_raw and "ebitda" in full_text.lower() else None,
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


def scrape_state(state_code: str, max_pages: int) -> list[dict]:
    state_slug = STATE_SLUGS.get(state_code.upper())
    if not state_slug:
        print(f"[WARN] Unknown state: {state_code}")
        return []

    urls = []
    for page in range(1, max_pages + 1):
        if page == 1:
            urls.append(f"{BASE_URL}/biz/{state_slug}-businesses-for-sale/")
        else:
            urls.append(f"{BASE_URL}/biz/{state_slug}-businesses-for-sale/?page={page}")

    print(f"  [{SOURCE_ID}] {state_code}: fetching {len(urls)} pages via Playwright...")
    page_results = fetch_pages_sync(urls, delay=DELAY, wait_selector=SELECTORS["listing_card"])

    results = []
    for url, html in page_results:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(SELECTORS["listing_card"])

        if not cards:
            debug_path = Path(".tmp") / f"debug_loopnet_{state_code}.html"
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
    parser = argparse.ArgumentParser(description="Scrape LoopNet /biz/ listings")
    parser.add_argument("--states", nargs="+", default=["FL", "TX", "GA", "NC", "SC"])
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--out", default=".tmp/raw_listings_loopnet.json")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_listings = []
    for state in args.states:
        print(f"\n[LoopNet] Scraping {state}...")
        listings = scrape_state(state.upper(), args.max_pages)
        all_listings.extend(listings)
        print(f"[LoopNet] {state}: {len(listings)} listings")

    seen = set()
    deduped = [l for l in all_listings if not (l["deal_id"] in seen or seen.add(l["deal_id"]))]

    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\n[DONE] Wrote {len(deduped)} listings to {out_path}")


if __name__ == "__main__":
    main()
