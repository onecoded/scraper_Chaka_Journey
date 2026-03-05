"""
run_lead_gen.py — Master orchestrator for the off-market business lead gen system.

USAGE:
  python tools/run_lead_gen.py                     # Run all buyers
  python tools/run_lead_gen.py --buyer magus_abraxas  # Run one buyer
  python tools/run_lead_gen.py --linkedin-only     # Generate LinkedIn search sheet only
  python tools/run_lead_gen.py --list-buyers       # List all buyers

WORKFLOW:
  1. For each buyer, search Apollo.io (if key set) + web scrapers
  2. Deduplicate leads
  3. Generate personalized LinkedIn connection request + InMail for each lead
  4. Export to CSV: .tmp/leads/leads_{buyer_id}.csv
  5. Export master CSV: .tmp/MASTER_LEADS.csv
  6. Export LinkedIn search URL sheet: .tmp/LINKEDIN_SEARCH_URLS.csv

WHAT YOU DO AFTER:
  1. Open MASTER_LEADS.csv
  2. For each lead with an owner_linkedin URL: send the connection_request message
  3. For leads without LinkedIn: use the linkedin_search_url to find them manually
  4. Update status column as you get responses
  5. When seller responds with interest: mark seller_interested=YES
  6. Present confirmed-interested sellers to matching buyer
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add tools/ to path
sys.path.insert(0, str(Path(__file__).parent))

from buyers_db import BUYERS, get_buyer_by_id
from apollo_search import search_leads_for_buyer
from web_scraper import scrape_all_sources
from message_generator import add_messages_to_leads
from export_leads import (
    export_to_csv,
    export_all_buyers_csv,
    generate_linkedin_search_sheet,
    save_leads_json,
    load_leads_json,
)


def run_for_buyer(buyer: dict, use_cache: bool = True, min_leads: int = 10) -> list:
    """
    Run full lead gen pipeline for a single buyer.
    Returns list of leads with messages attached.
    """
    print(f"\n{'='*60}")
    print(f"BUYER: {buyer['name']}")
    print(f"Industries: {', '.join(buyer['industries'])}")
    print(f"Geography: {', '.join(buyer.get('states', buyer.get('geographies', ['US'])))}")
    print(f"EBITDA: ${buyer.get('ebitda_min',0):,} - ${min(buyer.get('ebitda_max',10_000_000), 50_000_000):,}")
    print(f"{'='*60}")

    # Check cache first
    if use_cache:
        cached = load_leads_json(buyer["id"])
        if cached and len(cached) >= min_leads:
            print(f"  [CACHE] Using {len(cached)} cached leads for {buyer['name']}")
            # Re-generate messages in case templates changed
            leads = add_messages_to_leads(cached, buyer)
            return leads

    all_leads = []

    # 1. Apollo.io search
    print("\n[STEP 1] Apollo.io search...")
    apollo_leads = search_leads_for_buyer(buyer, max_results=25)
    all_leads.extend(apollo_leads)
    print(f"  Apollo leads: {len(apollo_leads)}")

    # 2. Web scraper fallback
    print("\n[STEP 2] Web scraper search (Yelp, Yellow Pages, Manta)...")
    web_leads = scrape_all_sources(buyer, max_per_source=10)
    # Deduplicate against Apollo results
    existing_names = {l["company_name"].lower() for l in all_leads}
    new_web = [l for l in web_leads if l["company_name"].lower() not in existing_names]
    all_leads.extend(new_web)
    print(f"  Web scraper leads (new): {len(new_web)}")

    total = len(all_leads)
    print(f"\n[STEP 2 DONE] Total unique leads: {total}")

    if total == 0:
        print(f"  WARNING: No leads found for {buyer['name']}. Check API keys and try again.")
        return []

    if total < min_leads:
        print(f"  NOTE: Found {total} leads (target: {min_leads}). Consider adding API keys for more sources.")

    # 3. Generate messages
    print("\n[STEP 3] Generating personalized LinkedIn messages...")
    leads = add_messages_to_leads(all_leads, buyer)

    # 4. Save to cache
    save_leads_json(leads, buyer["id"])

    return leads


def main():
    parser = argparse.ArgumentParser(description="Off-market business lead gen")
    parser.add_argument("--buyer", help="Run only this buyer ID (e.g. magus_abraxas)")
    parser.add_argument("--linkedin-only", action="store_true",
                        help="Only generate LinkedIn search URL sheet")
    parser.add_argument("--list-buyers", action="store_true",
                        help="List all buyers and exit")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force fresh search, ignore cache")
    parser.add_argument("--min-leads", type=int, default=10,
                        help="Minimum leads per buyer (default: 10)")
    args = parser.parse_args()

    # List buyers
    if args.list_buyers:
        print(f"\n{'Buyer ID':<35} {'Name':<35} {'Industries'}")
        print("-" * 100)
        for b in BUYERS:
            print(f"{b['id']:<35} {b['name']:<35} {', '.join(b['industries'][:3])}")
        return

    # LinkedIn search sheet only
    if args.linkedin_only:
        print("\n[MODE] LinkedIn search URL generation only")
        path = generate_linkedin_search_sheet(BUYERS)
        print(f"\n[DONE] Open this file in Excel/Sheets:")
        print(f"  {path}")
        print("\nThis sheet gives you pre-built LinkedIn search URLs for every buyer.")
        print("Your VA can use these to find and message business owners manually.")
        return

    # Determine which buyers to run
    if args.buyer:
        buyer = get_buyer_by_id(args.buyer)
        if not buyer:
            print(f"ERROR: Buyer ID '{args.buyer}' not found. Run --list-buyers to see options.")
            sys.exit(1)
        buyers_to_run = [buyer]
    else:
        buyers_to_run = BUYERS
        print(f"\n[START] Running lead gen for ALL {len(buyers_to_run)} buyers")
        print("This may take a while. Results are saved progressively.\n")

    # Run pipeline
    all_buyer_leads = {}
    summary = []

    for buyer in buyers_to_run:
        try:
            leads = run_for_buyer(
                buyer,
                use_cache=not args.no_cache,
                min_leads=args.min_leads,
            )

            if leads:
                # Export per-buyer CSV
                csv_path = export_to_csv(leads, buyer["id"])
                all_buyer_leads[buyer["id"]] = leads

                summary.append({
                    "buyer": buyer["name"],
                    "leads_found": len(leads),
                    "with_linkedin": sum(1 for l in leads if l.get("owner_linkedin")),
                    "with_email": sum(1 for l in leads if l.get("owner_email")),
                    "csv": str(csv_path),
                })
            else:
                summary.append({
                    "buyer": buyer["name"],
                    "leads_found": 0,
                    "with_linkedin": 0,
                    "with_email": 0,
                    "csv": "none",
                })

        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Saving progress...")
            break
        except Exception as e:
            print(f"\n[ERROR] Failed for {buyer['name']}: {e}")
            summary.append({"buyer": buyer["name"], "leads_found": 0, "error": str(e)})

    # Export master CSV
    if all_buyer_leads:
        master_path = export_all_buyers_csv(all_buyer_leads)

        # Generate LinkedIn search sheet
        linkedin_path = generate_linkedin_search_sheet(BUYERS)

    # Print summary
    print(f"\n{'='*60}")
    print("LEAD GEN SUMMARY")
    print(f"{'='*60}")
    print(f"{'Buyer':<40} {'Leads':>6} {'LinkedIn':>9} {'Email':>6}")
    print("-" * 65)

    total_leads = 0
    total_linkedin = 0
    for s in summary:
        leads = s.get("leads_found", 0)
        linkedin = s.get("with_linkedin", 0)
        email = s.get("with_email", 0)
        total_leads += leads
        total_linkedin += linkedin
        status = "✓" if leads >= 10 else ("~" if leads > 0 else "✗")
        print(f"{status} {s['buyer']:<38} {leads:>6} {linkedin:>9} {email:>6}")

    print("-" * 65)
    print(f"{'TOTAL':<40} {total_leads:>6} {total_linkedin:>9}")

    print(f"\nOUTPUT FILES:")
    if all_buyer_leads:
        print(f"  Master CSV:      {master_path}")
        print(f"  LinkedIn URLs:   {linkedin_path}")
    print(f"  Per-buyer CSVs:  .tmp/leads/")

    print(f"\nNEXT STEPS:")
    print("  1. Open MASTER_LEADS.csv in Excel or Google Sheets")
    print("  2. Add API keys to .env for more leads (Apollo, Yelp, SerpAPI)")
    print("  3. Use 'connection_request' column text for LinkedIn connection notes")
    print("  4. Use 'inmail' column text for LinkedIn InMail / direct messages")
    print("  5. Update 'seller_responded' and 'seller_interested' as you hear back")
    print("  6. Once 10+ sellers confirmed per buyer → present to buyer")


if __name__ == "__main__":
    main()
