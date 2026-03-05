"""
scrape_businessesforsale.py
---------------------------
Parses BusinessesForSale.com RSS feeds to extract business listings.
RSS is far more reliable than HTML scraping for this site.

RSS URL pattern: https://www.businessesforsale.com/rss/us-{state-code}/businesses-for-sale.xml
If feed returns 0 items, visit https://www.businessesforsale.com/info/rssmenu.aspx
to find updated feed URLs and document them in workflows/scrape_listings.md.

Usage:
    python tools/scrape_businessesforsale.py --states FL TX GA NC SC --out .tmp/raw_listings_businessesforsale.json
"""

import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SOURCE_ID = "businessesforsale"
BASE_RSS = "https://www.businessesforsale.com/rss"

STATE_CODES_LOWER = {
    "AL": "al", "AK": "ak", "AZ": "az", "AR": "ar",
    "CA": "ca", "CO": "co", "CT": "ct", "DE": "de",
    "FL": "fl", "GA": "ga", "HI": "hi", "ID": "id",
    "IL": "il", "IN": "in", "IA": "ia", "KS": "ks",
    "KY": "ky", "LA": "la", "ME": "me", "MD": "md",
    "MA": "ma", "MI": "mi", "MN": "mn", "MS": "ms",
    "MO": "mo", "MT": "mt", "NE": "ne", "NV": "nv",
    "NH": "nh", "NJ": "nj", "NM": "nm", "NY": "ny",
    "NC": "nc", "ND": "nd", "OH": "oh", "OK": "ok",
    "OR": "or", "PA": "pa", "RI": "ri", "SC": "sc",
    "SD": "sd", "TN": "tn", "TX": "tx", "UT": "ut",
    "VT": "vt", "VA": "va", "WA": "wa", "WV": "wv",
    "WI": "wi", "WY": "wy",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.businessesforsale.com/",
}

DELAY = float(os.getenv("SCRAPER_DELAY_DEFAULT", "2"))


def build_rss_url(state_code: str) -> str:
    state_lc = STATE_CODES_LOWER.get(state_code.upper(), state_code.lower())
    return f"{BASE_RSS}/us-{state_lc}/businesses-for-sale.xml"


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


def extract_financial_from_html(html: str, label: str) -> str | None:
    """Extract a labeled financial value from HTML description content."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    m = re.search(rf'{re.escape(label)}\s*:?\s*(\$[\d,.]+ ?[MmKk]?)', text, re.I)
    return m.group(1).strip() if m else None


def extract_state_from_text(text: str) -> str:
    all_codes = set(STATE_CODES_LOWER.keys())
    m = re.search(r'\b([A-Z]{2})\b', text)
    if m and m.group(1) in all_codes:
        return m.group(1)
    return ""


def parse_item(item: ET.Element, ns: dict, state_code: str) -> dict | None:
    """Parse a single RSS <item> element into a DealListing dict."""
    def tag(name: str) -> str | None:
        # Try namespace-qualified first, then plain
        for prefix, uri in ns.items():
            el = item.find(f"{{{uri}}}{name}")
            if el is not None and el.text:
                return el.text.strip()
        el = item.find(name)
        return el.text.strip() if el is not None and el.text else None

    title = tag("title") or ""
    url = tag("link") or ""
    description_raw = tag("description") or ""
    pub_date = tag("pubDate") or ""

    # Strip HTML from description for text analysis
    desc_soup = BeautifulSoup(description_raw, "lxml")
    description_text = desc_soup.get_text(" ", strip=True)

    # Extract financials from description HTML
    asking_price_raw = (
        extract_financial_from_html(description_raw, "Asking Price") or
        extract_financial_from_html(description_raw, "Price") or
        tag("askingPrice") or ""
    )
    revenue_raw = (
        extract_financial_from_html(description_raw, "Annual Revenue") or
        extract_financial_from_html(description_raw, "Revenue") or
        tag("annualRevenue") or ""
    )
    cf_raw = (
        extract_financial_from_html(description_raw, "Cash Flow") or
        extract_financial_from_html(description_raw, "Net Income") or
        tag("cashFlow") or ""
    )

    # Industry / category
    industry = tag("category") or tag("businessType") or ""

    # Location: use scraped state; try to parse city from title or description
    location_city = ""
    city_m = re.search(r'(?:in|located in|based in)\s+([A-Z][a-zA-Z\s]+),?\s+[A-Z]{2}', description_text)
    if city_m:
        location_city = city_m.group(1).strip()

    if not title:
        return None

    # Stable ID from URL
    id_m = re.search(r'/(\d{5,})', url)
    deal_id = f"{SOURCE_ID}_{id_m.group(1)}" if id_m else f"{SOURCE_ID}_{hash(url) & 0xFFFFFF}"

    return {
        "deal_id": deal_id,
        "source": SOURCE_ID,
        "url": url,
        "title": title,
        "description": description_text[:500],
        "industry": industry,
        "industry_category": industry,
        "location_city": location_city,
        "location_state": state_code,
        "asking_price": clean_price(asking_price_raw),
        "asking_price_raw": asking_price_raw,
        "annual_revenue": clean_price(revenue_raw),
        "annual_revenue_raw": revenue_raw,
        "cash_flow": clean_price(cf_raw),
        "cash_flow_raw": cf_raw,
        "ebitda": None,
        "sde": clean_price(cf_raw),
        "employees": None,
        "years_established": None,
        "reason_for_selling": None,
        "real_estate_included": None,
        "inventory_included": None,
        "sba_eligible": bool(re.search(r'sba', description_text, re.I)),
        "financing_available": bool(re.search(r'financ', description_text, re.I)),
        "broker_email": None,
        "broker_phone": None,
        "date_listed": pub_date,
        "date_scraped": str(date.today()),
    }


def scrape_state(state_code: str) -> list[dict]:
    url = build_rss_url(state_code)
    print(f"  [{SOURCE_ID}] {state_code}: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"  [WARN] Request failed: {e}")
        return []

    if resp.status_code != 200:
        print(f"  [WARN] HTTP {resp.status_code} for {url}")
        # Try alternative URL pattern
        alt_url = f"https://www.businessesforsale.com/us-{state_code.lower()}/businesses-for-sale"
        print(f"  [INFO] Trying HTML fallback: {alt_url}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  [WARN] XML parse error: {e}")
        return []

    # Detect XML namespaces
    ns = {}
    for elem in root.iter():
        tag = elem.tag
        if tag.startswith("{"):
            uri = tag[1:tag.index("}")]
            # Guess prefix from common BFS namespace URIs
            if "businessesforsale" in uri or "bfs" in uri:
                ns["bfs"] = uri

    channel = root.find("channel")
    if channel is None:
        channel = root  # Sometimes the root IS the channel

    items = channel.findall("item")
    if not items:
        print(f"  [INFO] No items found in RSS feed. Check rssmenu.aspx for current URL.")
        return []

    results = []
    for item in items:
        listing = parse_item(item, ns, state_code)
        if listing:
            results.append(listing)

    print(f"  [OK] {len(results)} listings from RSS")
    return results


def main():
    parser = argparse.ArgumentParser(description="Scrape BusinessesForSale.com via RSS")
    parser.add_argument("--states", nargs="+", default=["FL", "TX", "GA", "NC", "SC"])
    parser.add_argument("--out", default=".tmp/raw_listings_businessesforsale.json")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_listings = []
    for state in args.states:
        print(f"\n[BusinessesForSale] Scraping {state}...")
        listings = scrape_state(state.upper())
        all_listings.extend(listings)
        print(f"[BusinessesForSale] {state}: {len(listings)} listings")
        time.sleep(DELAY)

    seen = set()
    deduped = [l for l in all_listings if not (l["deal_id"] in seen or seen.add(l["deal_id"]))]

    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\n[DONE] Wrote {len(deduped)} listings to {out_path}")


if __name__ == "__main__":
    main()
