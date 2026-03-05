"""
web_scraper.py — Free web scrapers for off-market business discovery.

Sources (no API key required):
1. Yelp (category + location search)
2. Manta.com (US business directory with revenue/employee data)
3. Yellow Pages (phone + address data)
4. Google Maps via SerpAPI (if key available)
5. LinkedIn search URL generator (manual use)

These return businesses that are NOT listed for sale — true off-market targets.
"""

import os
import re
import time
import json
import random
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
YELP_API_KEY = os.getenv("YELP_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]

# Industry → Yelp category codes
INDUSTRY_TO_YELP = {
    "manufacturing": ["manufacturers", "industrial", "metalfab", "plastic_fabrication"],
    "aerospace": ["aerospace_defense"],
    "logistics": ["freight_shipping", "couriers", "shippingcenters"],
    "transportation": ["trucking", "couriers", "freight_shipping"],
    "it": ["itservices", "computers", "datacenter"],
    "software": ["itservices", "softwaredevelopment"],
    "healthcare": ["health", "doctors", "dentists", "medcenters"],
    "home services": ["homeservices", "hvac", "plumbing", "electricians", "landscaping"],
    "construction": ["contractors", "buildingsupplies", "architects"],
    "legal": ["lawyers", "legalservices"],
    "financial services": ["financialservices", "accountants", "insurance"],
    "chemicals": ["industrial"],
    "energy": ["utilities", "petroleum"],
    "skincare": ["skincare", "medspas"],
    "food": ["food", "foodmanufacturers"],
    "cleaning": ["janitor", "homecleaning"],
}

# Industry → Manta category path fragments
INDUSTRY_TO_MANTA = {
    "manufacturing": "manufacturing",
    "aerospace": "aerospace-defense",
    "logistics": "transportation-warehousing",
    "transportation": "transportation-warehousing",
    "it": "computers-electronics-technology",
    "software": "computers-electronics-technology",
    "healthcare": "health-medical",
    "home services": "construction-home-improvement",
    "construction": "construction-home-improvement",
    "legal": "legal-services",
    "financial services": "financial-services",
    "chemicals": "manufacturing",
    "energy": "energy-utilities",
    "skincare": "beauty-spas-personal-care",
    "food": "food-beverage",
}


def _get_headers():
    return random.choice(HEADERS_POOL)


def _sleep():
    time.sleep(random.uniform(1.5, 3.0))


# ── YELP API ──────────────────────────────────────────────────────────────────

def scrape_yelp(industry: str, location: str, limit: int = 20) -> list:
    """
    Search Yelp Fusion API for businesses by industry + location.
    Returns list of business dicts.
    Requires: YELP_API_KEY
    """
    if not YELP_API_KEY or YELP_API_KEY == "REPLACE_ME":
        print(f"  [YELP] No API key — skipping Yelp for {industry}/{location}")
        return []

    categories = INDUSTRY_TO_YELP.get(industry.lower(), [industry.replace(" ", "")])
    cat_str = ",".join(categories[:3])

    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "term": industry,
        "location": location,
        "categories": cat_str,
        "limit": min(limit, 50),
        "sort_by": "rating",
    }

    try:
        resp = requests.get(
            "https://api.yelp.com/v3/businesses/search",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        businesses = resp.json().get("businesses", [])
    except requests.RequestException as e:
        print(f"  [YELP] Error: {e}")
        return []

    results = []
    for biz in businesses:
        results.append({
            "company_name": biz.get("name", ""),
            "company_domain": "",
            "company_linkedin": "",
            "industry": industry,
            "address": " ".join(biz.get("location", {}).get("display_address", [])),
            "city": biz.get("location", {}).get("city", ""),
            "state": biz.get("location", {}).get("state", ""),
            "phone": biz.get("phone", ""),
            "yelp_url": biz.get("url", ""),
            "yelp_rating": biz.get("rating", ""),
            "yelp_review_count": biz.get("review_count", ""),
            "employee_count": "",
            "estimated_revenue": "",
            "founded_year": "",
            "owner_name": "",
            "owner_linkedin": "",
            "owner_email": "",
            "source": "yelp",
            "status": "new",
        })

    print(f"  [YELP] Found {len(results)} businesses for {industry} in {location}")
    return results


# ── MANTA.COM SCRAPER ─────────────────────────────────────────────────────────

def scrape_manta(industry: str, state: str, city: str = "", page: int = 1) -> list:
    """
    Scrape Manta.com for businesses by industry and state.
    Manta has revenue/employee estimates for many SMBs.
    """
    category = INDUSTRY_TO_MANTA.get(industry.lower(), "business-services")
    location_path = state.lower()
    if city:
        location_path = f"{state.lower()}/{city.lower().replace(' ', '-')}"

    url = f"https://www.manta.com/mb/{category}/{location_path}/?pg={page}"
    print(f"  [MANTA] Scraping: {url}")

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=20)
        if resp.status_code == 403:
            print("  [MANTA] Blocked (403)")
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [MANTA] Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    # Manta listing cards
    for card in soup.select("article.search-result, div.search-result-card, li[data-businessid]"):
        try:
            name_el = card.select_one("h2 a, h3 a, .business-name a")
            name = name_el.get_text(strip=True) if name_el else ""
            link = name_el.get("href", "") if name_el else ""
            if link and not link.startswith("http"):
                link = "https://www.manta.com" + link

            city_el = card.select_one(".city, .location, [data-city]")
            city_txt = city_el.get_text(strip=True) if city_el else ""

            phone_el = card.select_one(".phone, [data-phone]")
            phone = phone_el.get_text(strip=True) if phone_el else ""

            if name:
                results.append({
                    "company_name": name,
                    "company_domain": "",
                    "company_linkedin": "",
                    "industry": industry,
                    "address": city_txt,
                    "city": city_txt.split(",")[0].strip() if "," in city_txt else city_txt,
                    "state": state.upper(),
                    "phone": phone,
                    "manta_url": link,
                    "employee_count": "",
                    "estimated_revenue": "",
                    "founded_year": "",
                    "owner_name": "",
                    "owner_linkedin": "",
                    "owner_email": "",
                    "source": "manta",
                    "status": "new",
                })
        except Exception:
            continue

    print(f"  [MANTA] Found {len(results)} businesses")
    _sleep()
    return results


# ── YELLOW PAGES SCRAPER ──────────────────────────────────────────────────────

def scrape_yellow_pages(search_term: str, location: str) -> list:
    """
    Scrape YellowPages.com for businesses.
    Returns business name, address, phone.
    """
    location_slug = location.replace(" ", "-").replace(",", "").lower()
    search_slug = search_term.replace(" ", "-").lower()
    url = f"https://www.yellowpages.com/search?search_terms={requests.utils.quote(search_term)}&geo_location_terms={requests.utils.quote(location)}"

    print(f"  [YP] Scraping Yellow Pages: {search_term} in {location}")

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=20)
        if resp.status_code in (403, 429):
            print("  [YP] Rate limited or blocked")
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [YP] Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    for listing in soup.select("div.result, div.search-results .v-card"):
        try:
            name_el = listing.select_one("a.business-name, h2.n, .business-name")
            name = name_el.get_text(strip=True) if name_el else ""

            phone_el = listing.select_one(".phones, .phone")
            phone = phone_el.get_text(strip=True) if phone_el else ""

            addr_el = listing.select_one(".street-address, address")
            addr = addr_el.get_text(strip=True) if addr_el else ""

            city_el = listing.select_one(".city")
            city_txt = city_el.get_text(strip=True) if city_el else ""

            website_el = listing.select_one("a.track-visit-website, a[href*='http']:not(.business-name)")
            website = website_el.get("href", "") if website_el else ""
            # YP wraps external URLs
            if "yellowpages.com" in website:
                website = ""

            if name:
                results.append({
                    "company_name": name,
                    "company_domain": _extract_domain(website),
                    "company_linkedin": "",
                    "industry": search_term,
                    "address": addr,
                    "city": city_txt.split(",")[0].strip() if city_txt else "",
                    "state": location.split(",")[-1].strip() if "," in location else "",
                    "phone": phone,
                    "website": website,
                    "employee_count": "",
                    "estimated_revenue": "",
                    "founded_year": "",
                    "owner_name": "",
                    "owner_linkedin": "",
                    "owner_email": "",
                    "source": "yellow_pages",
                    "status": "new",
                })
        except Exception:
            continue

    print(f"  [YP] Found {len(results)} businesses")
    _sleep()
    return results


# ── GOOGLE SEARCH (SerpAPI) ───────────────────────────────────────────────────

def search_google(query: str, num_results: int = 10) -> list:
    """
    Use SerpAPI to run a Google search and return business results.
    Requires: SERPAPI_KEY
    """
    if not SERPAPI_KEY or SERPAPI_KEY == "REPLACE_ME":
        print(f"  [GOOGLE] No SerpAPI key — skipping")
        return []

    params = {
        "api_key": SERPAPI_KEY,
        "q": query,
        "num": num_results,
        "engine": "google",
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  [GOOGLE] Error: {e}")
        return []

    results = []
    for item in data.get("organic_results", []):
        results.append({
            "company_name": item.get("title", "").split(" - ")[0].split(" | ")[0],
            "company_domain": _extract_domain(item.get("link", "")),
            "company_linkedin": "",
            "industry": "",
            "snippet": item.get("snippet", ""),
            "website": item.get("link", ""),
            "city": "",
            "state": "",
            "phone": "",
            "owner_name": "",
            "owner_linkedin": "",
            "owner_email": "",
            "source": "google",
            "status": "new",
        })

    print(f"  [GOOGLE] Found {len(results)} results")
    return results


# ── LINKEDIN SEARCH URL GENERATOR ─────────────────────────────────────────────

def generate_linkedin_search_url(
    industry: str,
    states: list,
    title_keywords: list = None,
    company_size: str = "B,C,D",  # B=1-10, C=11-50, D=51-200, E=201-500
) -> str:
    """
    Generate a LinkedIn People Search URL to find business owners.
    User opens this URL in browser and manually reviews/messages.

    Company size codes: B=1-10, C=11-50, D=51-200, E=201-500, F=501-1000
    """
    if title_keywords is None:
        title_keywords = ["owner", "founder", "president", "CEO", "principal"]

    # LinkedIn Sales Navigator URL (if they have it)
    # Otherwise regular LinkedIn search
    base = "https://www.linkedin.com/search/results/people/?"

    params = []

    # Keywords
    kw_str = " OR ".join([f'"{k}"' for k in title_keywords[:3]])
    industry_str = " OR ".join([f'"{industry}"'])
    params.append(f'keywords={requests.utils.quote(f"{industry} {kw_str}")}')

    # Geography filter (LinkedIn uses geoUrn codes — approximating with text)
    if states:
        geo_str = " OR ".join(states[:5])
        params.append(f"geoUrn={requests.utils.quote(geo_str)}")

    url = base + "&".join(params)
    return url


def generate_linkedin_company_search_url(
    keywords: list,
    states: list,
    company_size_codes: list = None,
) -> str:
    """
    Generate LinkedIn Company Search URL for finding target businesses.
    """
    if company_size_codes is None:
        company_size_codes = ["B", "C", "D"]  # 1-200 employees

    kw = " ".join(keywords[:3])
    base = "https://www.linkedin.com/search/results/companies/?"
    params = [f"keywords={requests.utils.quote(kw)}"]

    if states:
        params.append(f"geoUrn={requests.utils.quote(', '.join(states))}")

    return base + "&".join(params)


# ── UTILITY ───────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""


def scrape_all_sources(buyer: dict, max_per_source: int = 15) -> list:
    """
    Run all available scrapers for a buyer and combine results.
    Deduplicates by company name.
    """
    all_leads = []
    seen_names = set()

    industries = buyer.get("industries", [])[:2]
    states = buyer.get("states", [])
    geographies = buyer.get("geographies", [])

    # Determine locations to search
    from apollo_search import STATE_MAP
    search_states = list(states)
    for geo in geographies:
        if geo.lower() in STATE_MAP:
            search_states.extend(STATE_MAP[geo.lower()])
    search_states = list(set(search_states))[:5]  # Cap at 5 states

    locations = search_states if search_states else ["United States"]

    for industry in industries:
        for loc in locations[:3]:
            # Yelp
            yelp_results = scrape_yelp(industry, loc, limit=max_per_source)
            for lead in yelp_results:
                key = lead["company_name"].lower().strip()
                if key and key not in seen_names:
                    seen_names.add(key)
                    lead["buyer_id"] = buyer["id"]
                    lead["buyer_name"] = buyer["name"]
                    all_leads.append(lead)

            # Yellow Pages
            yp_results = scrape_yellow_pages(f"{industry} company", loc)
            for lead in yp_results:
                key = lead["company_name"].lower().strip()
                if key and key not in seen_names:
                    seen_names.add(key)
                    lead["buyer_id"] = buyer["id"]
                    lead["buyer_name"] = buyer["name"]
                    all_leads.append(lead)

            # Manta
            manta_results = scrape_manta(industry, loc if len(loc) == 2 else "TX")
            for lead in manta_results:
                key = lead["company_name"].lower().strip()
                if key and key not in seen_names:
                    seen_names.add(key)
                    lead["buyer_id"] = buyer["id"]
                    lead["buyer_name"] = buyer["name"]
                    all_leads.append(lead)

    print(f"\n  [SCRAPER] Total unique leads found: {len(all_leads)}")
    return all_leads


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from buyers_db import BUYERS

    # Test with Baruk Capital (Home Services, TX/FL)
    buyer = next(b for b in BUYERS if b["id"] == "baruk_capital")
    leads = scrape_all_sources(buyer, max_per_source=5)
    print(json.dumps(leads[:3], indent=2))
