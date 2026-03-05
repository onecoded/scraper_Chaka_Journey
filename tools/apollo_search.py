"""
apollo_search.py — Search Apollo.io for off-market businesses matching buyer criteria.

Apollo.io has a database of 275M+ contacts and 73M+ companies with:
- Revenue estimates
- Employee count
- Industry (SIC/NAICS codes)
- Geographic data
- Owner/executive contact info (name, LinkedIn URL, email)

Free plan: 50 credits/month
Basic plan ($49/mo): 1,000 credits/month
Professional ($99/mo): 2,000 credits/month

API docs: https://apolloio.github.io/apollo-api-docs/
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
APOLLO_BASE_URL = "https://api.apollo.io/v1"

# Industry keyword → Apollo SIC codes mapping
INDUSTRY_TO_SIC = {
    "manufacturing": ["20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
                       "30", "31", "32", "33", "34", "35", "36", "37", "38", "39"],
    "aerospace": ["3720", "3721", "3728", "3812"],
    "defense": ["3812", "3489", "3795"],
    "logistics": ["4210", "4213", "4215", "4220", "4225", "4226", "4730"],
    "transportation": ["4210", "4213", "4215", "4400", "4500", "4700", "4720", "4730"],
    "it": ["7370", "7371", "7372", "7373", "7374", "7376", "7379"],
    "software": ["7372", "7371"],
    "healthcare": ["8000", "8011", "8021", "8049", "8051", "8062", "8069", "8082", "8099"],
    "home services": ["1711", "1731", "1741", "1751", "1761", "1771", "1781", "7389", "4959"],
    "construction": ["1500", "1520", "1531", "1540", "1600", "1620", "1623", "1700"],
    "legal": ["8111"],
    "financial services": ["6020", "6022", "6141", "6153", "6159", "6211", "6282", "6311", "6321"],
    "chemicals": ["2800", "2810", "2820", "2830", "2840", "2850", "2860", "2870"],
    "energy": ["1311", "1321", "1381", "4911", "4922", "4924", "4941"],
    "ecommerce": ["5940", "5945", "5961", "7372"],
    "skincare": ["2844", "5122"],
    "food": ["2000", "2010", "2020", "2030", "2040", "2050", "2060", "2070", "2080", "2090"],
}

# State name → abbreviation
STATE_MAP = {
    "midwest": ["IL", "IN", "OH", "MI", "WI", "MN", "IA", "MO", "ND", "SD", "NE", "KS"],
    "southeast": ["FL", "GA", "SC", "NC", "TN", "AL", "MS", "AR", "VA", "WV", "KY"],
    "west coast": ["CA", "OR", "WA"],
    "west": ["CA", "NV", "AZ", "UT", "CO", "NM", "WY", "MT", "ID"],
    "northeast": ["NY", "NJ", "CT", "MA", "PA", "MD", "DE", "RI", "NH", "ME", "VT"],
    "south": ["TX", "FL", "GA", "TN", "AL", "MS", "AR", "LA", "OK", "KY"],
    "texas": ["TX"],
    "florida": ["FL"],
    "northwest": ["WA", "OR", "ID"],
    "southwest": ["CA", "AZ", "NM", "NV"],
}


def search_companies(
    industry_keywords: list,
    states: list,
    min_revenue: int = 0,
    max_revenue: int = 999_999_999,
    min_employees: int = 5,
    max_employees: int = 500,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """
    Search Apollo.io for companies matching buyer criteria.
    Returns raw Apollo response dict.
    """
    if not APOLLO_API_KEY or APOLLO_API_KEY == "REPLACE_ME":
        print("  [APOLLO] No API key set. Returning empty results.")
        return {"accounts": [], "pagination": {"total_entries": 0}}

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }

    # Build keyword list from industries
    keywords = []
    for ind in industry_keywords:
        keywords.append(ind)

    # Expand geographic regions to state codes
    all_states = []
    for state in states:
        if state in STATE_MAP:
            all_states.extend(STATE_MAP[state])
        elif len(state) == 2:
            all_states.append(state.upper())

    payload = {
        "page": page,
        "per_page": per_page,
        "organization_num_employees_ranges": [f"{min_employees},{max_employees}"],
        "keywords": keywords,
    }

    if all_states:
        payload["organization_locations"] = [f"{s}, US" for s in set(all_states)]

    # Revenue filter (Apollo uses annual_revenue_range)
    if min_revenue > 0 or max_revenue < 999_999_999:
        payload["revenue_range"] = {
            "min": min_revenue // 1_000_000,  # Apollo uses millions
            "max": max_revenue // 1_000_000,
        }

    try:
        resp = requests.post(
            f"{APOLLO_BASE_URL}/mixed_companies/search",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  [APOLLO] Error: {e}")
        return {"accounts": [], "pagination": {"total_entries": 0}}


def get_person_details(linkedin_url: str = None, email: str = None) -> dict:
    """
    Enrich a contact using Apollo.io People Enrichment.
    Returns person dict with name, title, email, LinkedIn URL.
    """
    if not APOLLO_API_KEY or APOLLO_API_KEY == "REPLACE_ME":
        return {}

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }

    payload = {}
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if email:
        payload["email"] = email

    if not payload:
        return {}

    try:
        resp = requests.post(
            f"{APOLLO_BASE_URL}/people/match",
            headers=headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("person", {})
    except requests.RequestException as e:
        print(f"  [APOLLO] Person enrichment error: {e}")
        return {}


def get_owner_contacts(company_domain: str) -> list:
    """
    Find C-level / owner contacts at a company via Apollo People Search.
    Returns list of contact dicts.
    """
    if not APOLLO_API_KEY or APOLLO_API_KEY == "REPLACE_ME":
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }

    payload = {
        "organization_domains": [company_domain],
        "person_titles": ["owner", "founder", "CEO", "president", "principal", "managing partner"],
        "per_page": 5,
    }

    try:
        resp = requests.post(
            f"{APOLLO_BASE_URL}/mixed_people/search",
            headers=headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("people", [])
    except requests.RequestException as e:
        print(f"  [APOLLO] Owner search error: {e}")
        return []


def search_leads_for_buyer(buyer: dict, max_results: int = 25) -> list:
    """
    Run Apollo search for a specific buyer and return structured lead list.
    """
    print(f"\n[APOLLO] Searching for leads for: {buyer['name']}")

    # Determine revenue range from EBITDA (estimate ~3-5x EBITDA = revenue)
    rev_min = buyer.get("ebitda_min", 0) * 3
    rev_max = min(buyer.get("ebitda_max", 10_000_000) * 8, 200_000_000)

    # Get states
    states = buyer.get("states", [])
    geographies = buyer.get("geographies", [])
    all_states = list(states)
    for geo in geographies:
        if geo.lower() in STATE_MAP:
            all_states.extend(STATE_MAP[geo.lower()])

    results = search_companies(
        industry_keywords=buyer.get("industries", []) + buyer.get("sub_industries", []),
        states=all_states,
        min_revenue=rev_min,
        max_revenue=rev_max,
        per_page=min(max_results, 25),
    )

    leads = []
    for account in results.get("accounts", []):
        lead = {
            "buyer_id": buyer["id"],
            "buyer_name": buyer["name"],
            "company_name": account.get("name", ""),
            "company_domain": account.get("primary_domain", ""),
            "company_linkedin": account.get("linkedin_url", ""),
            "industry": account.get("industry", ""),
            "city": account.get("city", ""),
            "state": account.get("state", ""),
            "country": account.get("country", ""),
            "employee_count": account.get("num_employees", ""),
            "estimated_revenue": account.get("estimated_annual_revenue", ""),
            "founded_year": account.get("founded_year", ""),
            "description": account.get("short_description", ""),
            "owner_name": "",
            "owner_title": "",
            "owner_linkedin": "",
            "owner_email": "",
            "linkedin_message": "",
            "source": "apollo",
            "status": "new",
        }

        # Try to get owner contacts
        if lead["company_domain"]:
            time.sleep(0.5)  # Rate limit courtesy
            contacts = get_owner_contacts(lead["company_domain"])
            if contacts:
                owner = contacts[0]
                lead["owner_name"] = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip()
                lead["owner_title"] = owner.get("title", "")
                lead["owner_linkedin"] = owner.get("linkedin_url", "")
                lead["owner_email"] = owner.get("email", "")

        leads.append(lead)
        time.sleep(0.3)

    print(f"  → Found {len(leads)} leads from Apollo")
    return leads


if __name__ == "__main__":
    # Test with one buyer
    from buyers_db import BUYERS
    test_buyer = next(b for b in BUYERS if b["id"] == "magus_abraxas")
    leads = search_leads_for_buyer(test_buyer, max_results=5)
    print(json.dumps(leads[:2], indent=2))
