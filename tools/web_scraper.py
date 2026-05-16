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
        yelp_url = biz.get("url", "")
        results.append({
            "company_name": biz.get("name", ""),
            "company_domain": yelp_url,
            "company_linkedin": "",
            "industry": industry,
            "address": " ".join(biz.get("location", {}).get("display_address", [])),
            "city": biz.get("location", {}).get("city", ""),
            "state": biz.get("location", {}).get("state", ""),
            "phone": biz.get("phone", ""),
            "yelp_url": yelp_url,
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
                    "company_domain": link,
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


def _empty_lead(name: str, industry: str, state: str, source: str, listing_type: str = "on-market") -> dict:
    return {
        "company_name": name, "industry": industry, "state": state.upper()[:2],
        "city": "", "asking_price": "", "revenue_estimate": "", "ebitda_estimate": "",
        "owner_name": "", "owner_email": "", "phone": "", "company_domain": "",
        "founded_year": "", "source": source, "listing_type": listing_type, "status": "new",
    }


# ── BIZBUYSELL ─────────────────────────────────────────────────────────────────

def scrape_bizbuysell(industry: str, states: list, min_price: int = 0,
                      max_price: int = 0, max_results: int = 30) -> list:
    """Scrape BizBuySell.com — the largest business-for-sale marketplace."""
    results = []
    seen = set()
    for state in states[:4]:
        url = f"https://www.bizbuysell.com/businesses-for-sale/?q={requests.utils.quote(industry)}&state={state.lower()}"
        if min_price: url += f"&asking_price_min={int(min_price)}"
        if max_price: url += f"&asking_price_max={int(max_price)}"
        print(f"  [BBS] {url}")
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=20)
            if resp.status_code in (403, 429): continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div.listing-card, article.listing, div[data-listing-id], div.result"):
                name_el = card.select_one("h2 a, h3 a, .listing-name a, a.listing-title, .title a")
                if not name_el: continue
                name = name_el.get_text(strip=True)
                if not name or name in seen: continue
                seen.add(name)
                lead = _empty_lead(name, industry, state, "bizbuysell", "on-market")
                p = card.select_one(".price, .asking-price, [class*='price']")
                if p: lead["asking_price"] = p.get_text(strip=True)
                r = card.select_one(".revenue, .gross-revenue, [class*='revenue']")
                if r: lead["revenue_estimate"] = r.get_text(strip=True)
                cf = card.select_one(".cash-flow, .ebitda, [class*='cash']")
                if cf: lead["ebitda_estimate"] = cf.get_text(strip=True)
                loc = card.select_one(".location, .city-state, [class*='location']")
                if loc:
                    parts = loc.get_text(strip=True).split(",")
                    lead["city"] = parts[0].strip()
                results.append(lead)
                if len(results) >= max_results: return results
        except Exception as e:
            print(f"  [BBS] Error: {e}")
        _sleep()
    print(f"  [BBS] Found {len(results)} listings")
    return results


# ── BIZQUEST ───────────────────────────────────────────────────────────────────

def scrape_bizquest(industry: str, states: list, max_results: int = 20) -> list:
    """Scrape BizQuest.com — strong for manufacturing and services."""
    results = []
    seen = set()
    for state in states[:3]:
        url = f"https://www.bizquest.com/buy-a-business/?industry={requests.utils.quote(industry)}&state={state.upper()}"
        print(f"  [BQ] {url}")
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=20)
            if resp.status_code in (403, 429): continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div.listing, article.listing-item, li.listing-result"):
                name_el = card.select_one("h2 a, h3 a, .listing-name, .title")
                if not name_el: continue
                name = name_el.get_text(strip=True)
                if not name or name in seen: continue
                seen.add(name)
                lead = _empty_lead(name, industry, state, "bizquest", "on-market")
                p = card.select_one(".price, .asking")
                if p: lead["asking_price"] = p.get_text(strip=True)
                r = card.select_one(".revenue, .gross")
                if r: lead["revenue_estimate"] = r.get_text(strip=True)
                loc = card.select_one(".location, .city")
                if loc: lead["city"] = loc.get_text(strip=True).split(",")[0].strip()
                results.append(lead)
                if len(results) >= max_results: return results
        except Exception as e:
            print(f"  [BQ] Error: {e}")
        _sleep()
    print(f"  [BQ] Found {len(results)} listings")
    return results


# ── BUSINESSESFORSALE.COM ─────────────────────────────────────────────────────

def scrape_businesses_for_sale(industry: str, states: list, max_results: int = 20) -> list:
    """Scrape BusinessesForSale.com — good international + US inventory."""
    results = []
    seen = set()
    for state in states[:3]:
        slug = industry.lower().replace(" ", "-").replace("/", "-")
        url = f"https://www.businessesforsale.com/us/{state.lower()}/businesses-for-sale?q={requests.utils.quote(industry)}"
        print(f"  [BFS] {url}")
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=20)
            if resp.status_code in (403, 429): continue
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div.listing-item, article, li[class*='listing']"):
                name_el = card.select_one("h2, h3, .listing-title, .title")
                if not name_el: continue
                name = name_el.get_text(strip=True)
                if not name or name in seen: continue
                seen.add(name)
                lead = _empty_lead(name, industry, state, "businesses_for_sale", "on-market")
                p = card.select_one(".price, .asking-price")
                if p: lead["asking_price"] = p.get_text(strip=True)
                r = card.select_one(".revenue, .turnover, .sales")
                if r: lead["revenue_estimate"] = r.get_text(strip=True)
                results.append(lead)
                if len(results) >= max_results: return results
        except Exception as e:
            print(f"  [BFS] Error: {e}")
        _sleep()
    print(f"  [BFS] Found {len(results)} listings")
    return results


# ── CRAIGSLIST ────────────────────────────────────────────────────────────────

_CL_CITIES = {
    "FL": ["miami","orlando","tampa","jacksonville","sarasota"],
    "TX": ["dallas","houston","austin","sanantonio","elpaso"],
    "CA": ["sfbay","losangeles","sandiego","sacramento","fresno"],
    "NY": ["newyork","longisland","buffalo","albany"],
    "GA": ["atlanta","savannah"],
    "NC": ["charlotte","raleigh"],
    "OH": ["cleveland","columbus","cincinnati","akroncanton"],
    "IL": ["chicago","peoria"],
    "AZ": ["phoenix","tucson","flagstaff"],
    "CO": ["denver","cosprings"],
    "WA": ["seattle","spokane"],
    "OR": ["portland","eugene"],
    "NV": ["lasvegas","reno"],
    "MN": ["minneapolis"],
    "MO": ["stlouis","kansascity"],
    "TN": ["nashville","memphis","knoxville"],
    "VA": ["norfolk","richmond"],
    "PA": ["philadelphia","pittsburgh"],
    "MI": ["detroit","grandrapids","lansing"],
    "MA": ["boston","worcester"],
    "NJ": ["newjersey"],
    "SC": ["charleston","columbia","greenville"],
    "AL": ["birmingham","mobile"],
    "LA": ["neworleans","batonrouge"],
    "IN": ["indianapolis","fortwayne"],
    "WI": ["milwaukee","madison"],
    "KY": ["louisville","lexington"],
    "OK": ["oklahoma","tulsa"],
}

def scrape_craigslist(industry: str, states: list, max_results: int = 25) -> list:
    """Scrape Craigslist business-for-sale section (bfs)."""
    results = []
    seen = set()
    for state in states[:3]:
        cities = _CL_CITIES.get(state.upper(), ["atlanta"])
        for city in cities[:2]:
            url = f"https://{city}.craigslist.org/search/bfs?query={requests.utils.quote(industry)}&sort=date"
            print(f"  [CL] {url}")
            try:
                resp = requests.get(url, headers=_get_headers(), timeout=15)
                if resp.status_code in (403, 404, 410, 429): continue
                soup = BeautifulSoup(resp.text, "lxml")
                for item in soup.select("li.cl-static-search-result, div.result-row, li[data-pid]"):
                    title_el = item.select_one("div.title, a.result-title, .titlestring, a[data-id]")
                    if not title_el: continue
                    title = title_el.get_text(strip=True)
                    if not title or title in seen: continue
                    seen.add(title)
                    lead = _empty_lead(title, industry, state, "craigslist", "on-market")
                    lead["city"] = city.title()
                    p = item.select_one(".price, span.result-price")
                    if p: lead["asking_price"] = p.get_text(strip=True)
                    results.append(lead)
                    if len(results) >= max_results: return results
            except Exception as e:
                print(f"  [CL] Error {city}: {e}")
            _sleep()
    print(f"  [CL] Found {len(results)} listings")
    return results


# ── FACEBOOK MARKETPLACE (public search) ─────────────────────────────────────

def scrape_facebook_marketplace(industry: str, states: list, max_results: int = 15) -> list:
    """
    Facebook Marketplace business listings via public search.
    Note: FB aggressively blocks scrapers — returns what it can.
    """
    results = []
    seen = set()
    for state in states[:2]:
        query = f"{industry} business for sale {state}"
        url = f"https://www.facebook.com/marketplace/search/?query={requests.utils.quote(query)}&category=vehicles"
        # FB blocks most automated requests; use a lighter approach via public search
        search_url = f"https://www.facebook.com/marketplace/search?query={requests.utils.quote(query)}"
        try:
            resp = requests.get(search_url, headers={**_get_headers(),
                "Accept": "text/html", "Referer": "https://www.facebook.com/"}, timeout=15)
            if resp.status_code in (400, 403, 429): continue
            soup = BeautifulSoup(resp.text, "lxml")
            for item in soup.select("div[data-testid='marketplace_feed_item'], div.x9f619"):
                name_el = item.select_one("span.x1lliihq, div[class*='title'], span")
                if not name_el: continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5 or name in seen: continue
                seen.add(name)
                lead = _empty_lead(name, industry, state, "facebook_marketplace", "on-market")
                p = item.select_one("[class*='price'], span[class*='x193iq5w']")
                if p: lead["asking_price"] = p.get_text(strip=True)
                results.append(lead)
                if len(results) >= max_results: return results
        except Exception as e:
            print(f"  [FB] Error: {e}")
        _sleep()
    print(f"  [FB] Found {len(results)} listings (FB blocks most scraping)")
    return results


# ── ACQUIRE.COM (tech/software businesses) ────────────────────────────────────

def scrape_acquire(industry: str, max_results: int = 15) -> list:
    """Scrape Acquire.com for SaaS/tech business listings."""
    if not any(k in industry.lower() for k in ["tech","software","saas","app","digital","it","platform"]):
        return []
    results = []
    url = f"https://acquire.com/search?q={requests.utils.quote(industry)}"
    print(f"  [ACQ] {url}")
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=15)
        if resp.status_code in (403, 429): return []
        soup = BeautifulSoup(resp.text, "lxml")
        for card in soup.select("div.listing-card, article, div[class*='business']"):
            name_el = card.select_one("h2, h3, .name, .title")
            if not name_el: continue
            name = name_el.get_text(strip=True)
            if not name: continue
            lead = _empty_lead(name, industry, "US", "acquire_com", "on-market")
            p = card.select_one(".price, .asking, .arr, [class*='revenue']")
            if p: lead["asking_price"] = p.get_text(strip=True)
            results.append(lead)
            if len(results) >= max_results: break
    except Exception as e:
        print(f"  [ACQ] Error: {e}")
    print(f"  [ACQ] Found {len(results)} listings")
    return results


# ── COMBINED SCRAPE ────────────────────────────────────────────────────────────

def scrape_all_sources(buyer: dict, max_per_source: int = 15) -> list:
    """
    Run all scrapers for a buyer and combine results.
    Applies industry + state expansion from buyer mandate.
    Deduplicates by company name.
    """
    all_leads = []
    seen_names = set()

    industries = buyer.get("industries", [])[:3]
    states = list(buyer.get("states") or [])
    geographies = buyer.get("geographies") or []

    # Expand geographies to states
    try:
        from apollo_search import STATE_MAP
        for geo in geographies:
            if geo.lower() in STATE_MAP:
                states.extend(STATE_MAP[geo.lower()])
    except Exception:
        pass
    states = list(dict.fromkeys(s.upper()[:2] for s in states if s))[:6]
    if not states:
        states = ["TX", "FL", "CA", "OH", "GA"]  # broad default

    b_min = float(buyer.get("deal_size_min") or 0)
    b_max = float(buyer.get("deal_size_max") or 0)

    def _add(leads, tag):
        added = 0
        for lead in leads:
            key = (lead.get("company_name") or "").lower().strip()
            if key and key not in seen_names:
                seen_names.add(key)
                lead.setdefault("buyer_id",   buyer["id"])
                lead.setdefault("buyer_name", buyer["name"])
                all_leads.append(lead)
                added += 1
        print(f"    [{tag}] +{added} unique")

    for industry in industries:
        print(f"\n  [SCRAPER] Industry: {industry} | States: {states}")

        # ── LISTED (for-sale) sources ─────────────────────────────────────────
        _add(scrape_bizbuysell(industry, states, int(b_min), int(b_max), max_per_source), "BizBuySell")
        _add(scrape_bizquest(industry, states, max_per_source), "BizQuest")
        _add(scrape_businesses_for_sale(industry, states, max_per_source), "BizForSale")
        _add(scrape_craigslist(industry, states, max_per_source), "Craigslist")
        _add(scrape_facebook_marketplace(industry, states, 10), "Facebook")
        if any(k in industry.lower() for k in ["tech","software","saas","app","digital"]):
            _add(scrape_acquire(industry, 10), "Acquire")

        # ── OFF-MARKET sources (business directories) ─────────────────────────
        for loc in states[:3]:
            _add(scrape_yelp(industry, loc, limit=max_per_source), "Yelp")
            _add(scrape_yellow_pages(f"{industry} company", loc), "YellowPages")
            _add(scrape_manta(industry, loc), "Manta")

    print(f"\n  [SCRAPER] Total unique leads: {len(all_leads)}")
    return all_leads


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from buyers_db import BUYERS
    buyer = next(b for b in BUYERS if b["id"] == "baruk_capital")
    leads = scrape_all_sources(buyer, max_per_source=5)
    print(json.dumps(leads[:3], indent=2))
