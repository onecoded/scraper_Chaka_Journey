"""
export_leads.py — Export leads to CSV and optionally Google Sheets.

Output columns:
- Buyer info (buyer_name, buyer_id)
- Business info (company_name, industry, city, state, phone, website)
- Owner info (owner_name, owner_title, owner_linkedin, owner_email)
- Outreach (connection_request, inmail, linkedin_search_url)
- Status tracking (status, seller_responded, seller_interested, notes)
- Source (apollo, yelp, yellow_pages, manta, google)
"""

import os
import csv
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
TMP_DIR = BASE_DIR / ".tmp" / "leads"
TMP_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_COLUMNS = [
    # Buyer
    "buyer_name",
    "buyer_id",
    # Business
    "company_name",
    "industry",
    "city",
    "state",
    "phone",
    "company_domain",
    "website",
    "company_linkedin",
    "employee_count",
    "estimated_revenue",
    "founded_year",
    "description",
    # Owner
    "owner_name",
    "owner_title",
    "owner_linkedin",
    "owner_email",
    # Outreach
    "connection_request",
    "inmail",
    "linkedin_search_url",
    # Tracking
    "status",
    "outreach_sent_date",
    "seller_responded",
    "seller_interested",
    "response_notes",
    "next_action",
    # Meta
    "source",
    "date_added",
]


def export_to_csv(leads: list, buyer_id: str = "all") -> Path:
    """
    Export leads list to a CSV file.
    Returns path to the created file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = TMP_DIR / f"leads_{buyer_id}_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            # Fill in defaults for missing fields
            row = {col: lead.get(col, "") for col in EXPORT_COLUMNS}
            row["date_added"] = row.get("date_added") or datetime.now().strftime("%Y-%m-%d")
            row["status"] = row.get("status") or "new"
            row["seller_responded"] = row.get("seller_responded") or "No"
            row["seller_interested"] = row.get("seller_interested") or "Unknown"
            writer.writerow(row)

    print(f"  [EXPORT] Saved {len(leads)} leads → {filename}")
    return filename


def export_all_buyers_csv(all_leads: dict) -> Path:
    """
    Export all buyer leads to a single master CSV.
    all_leads: dict of {buyer_id: [leads]}
    """
    combined = []
    for buyer_id, leads in all_leads.items():
        combined.extend(leads)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = BASE_DIR / ".tmp" / f"MASTER_LEADS_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for lead in combined:
            row = {col: lead.get(col, "") for col in EXPORT_COLUMNS}
            row["date_added"] = row.get("date_added") or datetime.now().strftime("%Y-%m-%d")
            row["status"] = row.get("status") or "new"
            row["seller_responded"] = row.get("seller_responded") or "No"
            row["seller_interested"] = row.get("seller_interested") or "Unknown"
            writer.writerow(row)

    print(f"\n[EXPORT] MASTER CSV: {len(combined)} total leads → {filename}")
    return filename


def generate_linkedin_search_sheet(buyers: list) -> Path:
    """
    Generate a CSV of LinkedIn search URLs for each buyer.
    This is the manual prospecting guide for VAs.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from web_scraper import generate_linkedin_search_url, generate_linkedin_company_search_url

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = BASE_DIR / ".tmp" / f"LINKEDIN_SEARCH_URLS_{timestamp}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Buyer Name",
            "Industries",
            "States/Geography",
            "EBITDA Range",
            "Deal Size",
            "LinkedIn People Search URL",
            "LinkedIn Company Search URL",
            "Search Notes",
        ])

        for buyer in buyers:
            industries = buyer.get("industries", [])
            states = buyer.get("states", [])
            geographies = buyer.get("geographies", [])
            all_states = list(states)

            # Expand geographic regions
            from apollo_search import STATE_MAP
            for geo in geographies:
                if geo.lower() in STATE_MAP:
                    all_states.extend(STATE_MAP[geo.lower()])

            people_url = generate_linkedin_search_url(
                industry=industries[0] if industries else "business",
                states=list(set(all_states))[:5],
            )
            company_url = generate_linkedin_company_search_url(
                keywords=industries[:3] + buyer.get("sub_industries", [])[:2],
                states=list(set(all_states))[:5],
            )

            ebitda_min = buyer.get("ebitda_min", 0)
            ebitda_max = buyer.get("ebitda_max", 0)
            deal_min = buyer.get("deal_size_min", 0)
            deal_max = buyer.get("deal_size_max", 0)

            writer.writerow([
                buyer["name"],
                ", ".join(industries),
                ", ".join(list(set(all_states))[:8]) or ", ".join(geographies),
                f"${ebitda_min:,} - ${min(ebitda_max, 50_000_000):,}",
                f"${deal_min:,} - ${min(deal_max, 100_000_000):,}",
                people_url,
                company_url,
                buyer.get("notes", ""),
            ])

    print(f"\n[EXPORT] LinkedIn search URLs -> {filename}")
    return filename


def save_leads_json(leads: list, buyer_id: str) -> Path:
    """Save leads as JSON for reprocessing."""
    filename = TMP_DIR / f"leads_{buyer_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)
    return filename


def load_leads_json(buyer_id: str) -> list:
    """Load previously scraped leads from JSON."""
    filename = TMP_DIR / f"leads_{buyer_id}.json"
    if filename.exists():
        with open(filename, encoding="utf-8") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from buyers_db import BUYERS

    # Generate LinkedIn search URLs for all buyers
    path = generate_linkedin_search_sheet(BUYERS)
    print(f"LinkedIn search sheet: {path}")
