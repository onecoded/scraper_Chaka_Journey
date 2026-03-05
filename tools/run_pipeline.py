"""
run_pipeline.py
---------------
Master orchestrator for the Deal Flow & Matching pipeline.

Execution sequence:
  1. Parse buyers PDF → .tmp/buyers.json  (skipped if file exists, use --force-parse to rerun)
  2. Scrape all deal sources in parallel
  3. Merge and deduplicate all raw listings → .tmp/all_listings.json
  4. Match deals to buyer criteria → .tmp/matches.json
  5. Generate email drafts for B/A-grade matches → .tmp/email_drafts.json
  6. Export to Google Sheets

Usage:
    python tools/run_pipeline.py
    python tools/run_pipeline.py --states FL TX GA --max-pages 3
    python tools/run_pipeline.py --states FL --skip-email --skip-sheets
    python tools/run_pipeline.py --force-parse   # re-parse buyers PDF even if buyers.json exists
    python tools/run_pipeline.py --min-score 50  # override match threshold
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYTHON = sys.executable  # Use the same Python interpreter that's running this script
ROOT = Path(__file__).parent.parent  # Project root


def run_tool(script: str, args: list[str], label: str) -> tuple[bool, str]:
    """Run a tool script as a subprocess. Returns (success, output)."""
    cmd = [PYTHON, str(ROOT / "tools" / script)] + args
    print(f"\n[PIPELINE] Running: {label}")
    print(f"  Command: {' '.join(cmd)}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=300  # 5 minute timeout per tool
        )
        elapsed = time.time() - start

        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                print(f"  [STDERR] {line}")

        success = result.returncode == 0
        status = "OK" if success else f"FAILED (exit {result.returncode})"
        print(f"  [{status}] {label} completed in {elapsed:.1f}s")
        return success, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] {label} exceeded 5 minutes")
        return False, "TIMEOUT"
    except Exception as e:
        print(f"  [ERROR] {label}: {e}")
        return False, str(e)


def merge_listings(tmp_dir: Path, out_path: Path) -> int:
    """Merge all raw_listings_*.json files, deduplicate by URL."""
    all_listings = []
    pattern = str(tmp_dir / "raw_listings_*.json")
    files = glob.glob(pattern)

    if not files:
        print("[WARN] No raw listing files found to merge")
        return 0

    for f in files:
        try:
            data = json.loads(Path(f).read_text())
            all_listings.extend(data)
            print(f"  Loaded {len(data)} listings from {Path(f).name}")
        except Exception as e:
            print(f"  [WARN] Could not load {f}: {e}")

    # Deduplicate: prefer bizbuysell > bizquest > others (keep first seen)
    seen_urls = set()
    seen_ids = set()
    deduped = []

    for listing in all_listings:
        url = listing.get("url", "")
        deal_id = listing.get("deal_id", "")

        if url and url in seen_urls:
            continue
        if deal_id and deal_id in seen_ids:
            continue

        if url:
            seen_urls.add(url)
        if deal_id:
            seen_ids.add(deal_id)

        deduped.append(listing)

    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\n[MERGE] {len(all_listings)} total → {len(deduped)} unique listings saved to {out_path}")
    return len(deduped)


def print_summary(matches_path: Path, emails_path: Path, start_time: float):
    """Print a summary of pipeline results."""
    print("\n" + "="*60)
    print("PIPELINE SUMMARY")
    print("="*60)

    if matches_path.exists():
        matches = json.loads(matches_path.read_text())
        a_count = sum(1 for m in matches if m.get("grade") == "A")
        b_count = sum(1 for m in matches if m.get("grade") == "B")
        c_count = sum(1 for m in matches if m.get("grade") == "C")
        print(f"Matches: {len(matches)} total — A:{a_count}  B:{b_count}  C:{c_count}")

        if matches:
            top = sorted(matches, key=lambda x: x.get("score_pct", 0), reverse=True)[:3]
            print("\nTop 3 Matches:")
            for m in top:
                print(f"  [{m.get('grade')}] {m.get('score_pct')}% | "
                      f"{m.get('deal_title', '')[:45]} → {m.get('buyer_name', '')}")
    else:
        print("Matches: (not generated)")

    if emails_path.exists():
        emails = json.loads(emails_path.read_text())
        print(f"\nEmail Drafts: {len(emails)} generated")
    else:
        print("\nEmail Drafts: (not generated)")

    elapsed = time.time() - start_time
    print(f"\nTotal runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print("="*60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the full Deal Flow & Matching pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--states", nargs="+",
        default=["FL", "TX", "GA", "NC", "SC"],
        help="States to scrape (2-letter codes)"
    )
    parser.add_argument(
        "--max-pages", type=int,
        default=int(os.getenv("SCRAPER_MAX_PAGES_DEFAULT", "5")),
        help="Max pages per state per scraper"
    )
    parser.add_argument(
        "--min-score", type=float,
        default=float(os.getenv("MIN_MATCH_SCORE", "40")),
        help="Minimum match score to include (0-100)"
    )
    parser.add_argument(
        "--min-email-score", type=float,
        default=float(os.getenv("MIN_EMAIL_SCORE", "60")),
        help="Minimum score to generate email drafts"
    )
    parser.add_argument("--force-parse", action="store_true",
                        help="Re-parse buyers PDF even if buyers.json already exists")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip scraping (use existing raw listing files)")
    parser.add_argument("--skip-email", action="store_true",
                        help="Skip email draft generation")
    parser.add_argument("--skip-sheets", action="store_true",
                        help="Skip Google Sheets export")
    parser.add_argument("--upgrade-a-grade", action="store_true",
                        help="Use Sonnet instead of Haiku for A-grade email drafts")
    args = parser.parse_args()

    start_time = time.time()
    tmp_dir = ROOT / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"DEAL FLOW PIPELINE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"States: {', '.join(args.states)} | Max pages: {args.max_pages}")
    print(f"Match threshold: {args.min_score}% | Email threshold: {args.min_email_score}%")
    print(f"{'='*60}")

    buyers_path = ROOT / os.getenv("BUYERS_JSON_PATH", ".tmp/buyers.json")
    results = {}

    # -----------------------------------------------------------------------
    # Step 1a: Import buyers from Excel (if template has data, always merges)
    # -----------------------------------------------------------------------
    buyers_excel = ROOT / "data" / "BUYERS_TEMPLATE.xlsx"
    if buyers_excel.exists():
        run_tool("import_buyers_excel.py", [
            "--excel", str(buyers_excel),
            "--out", str(buyers_path)
        ], "Import Buyers from Excel")

    # -----------------------------------------------------------------------
    # Step 1b: Parse buyers PDF (only if buyers.json still doesn't exist)
    # -----------------------------------------------------------------------
    if not buyers_path.exists() or args.force_parse:
        pdf_path = os.getenv("PDF_PATH", "BIZ BROKER MATCHES - buyers w agreements.pdf")
        ok, _ = run_tool("parse_buyers_pdf.py", [
            "--pdf", pdf_path,
            "--out", str(buyers_path)
        ], "Parse Buyers PDF")
        results["parse_buyers"] = ok
        if not ok:
            print("[ERROR] Buyer parsing failed. Cannot continue without buyer criteria.")
            sys.exit(1)
        print(f"\n[ACTION REQUIRED] Review {buyers_path} and verify buyer data before continuing.")
        print("Press ENTER to continue or Ctrl+C to abort and edit the file...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nAborted. Edit the buyers.json file and re-run with --skip-parse.")
            sys.exit(0)
    else:
        print(f"\n[STEP 1] Using existing buyers file: {buyers_path}")
        buyers = json.loads(buyers_path.read_text())
        print(f"  {len(buyers)} buyer(s) loaded")

    # -----------------------------------------------------------------------
    # Step 2: Scrape all sources in parallel
    # -----------------------------------------------------------------------
    if not args.skip_scrape:
        states_str = " ".join(args.states)
        serpapi_key = os.getenv("SERPAPI_KEY", "")
        serpapi_configured = bool(serpapi_key and serpapi_key != "REPLACE_ME")

        scrapers = [
            ("scrape_bizbuysell.py",
             ["--states"] + args.states + ["--max-pages", str(args.max_pages), "--out", ".tmp/raw_listings_bizbuysell.json"],
             "BizBuySell"),
            ("scrape_bizquest.py",
             ["--states"] + args.states + ["--max-pages", str(args.max_pages), "--out", ".tmp/raw_listings_bizquest.json"],
             "BizQuest"),
            ("scrape_businessesforsale.py",
             ["--states"] + args.states + ["--out", ".tmp/raw_listings_businessesforsale.json"],
             "BusinessesForSale"),
            ("scrape_loopnet.py",
             ["--states"] + args.states + ["--max-pages", "3", "--out", ".tmp/raw_listings_loopnet.json"],
             "LoopNet"),
            ("scrape_axial.py",
             ["--out", ".tmp/raw_listings_axial.json"],
             "Axial"),
        ]

        # Add SerpAPI scraper if configured — bypasses Akamai IP blocks
        if serpapi_configured:
            scrapers.append((
                "scrape_serpapi.py",
                ["--states"] + args.states + ["--out", ".tmp/raw_listings_serpapi.json"],
                "SerpAPI (Google Search)"
            ))
        else:
            print("\n[INFO] SerpAPI not configured. If direct scrapers are IP-blocked,")
            print("       add SERPAPI_KEY to .env for Google Search fallback.")

        print(f"\n[STEP 2] Running {len(scrapers)} scrapers in parallel...")
        scraper_results = {}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(run_tool, script, scraper_args, label): label
                for script, scraper_args, label in scrapers
            }
            for future in as_completed(futures):
                label = futures[future]
                ok, _ = future.result()
                scraper_results[label] = ok

        for label, ok in scraper_results.items():
            status = "OK" if ok else "FAILED"
            print(f"  {label}: {status}")

        results["scrapers"] = scraper_results
    else:
        print("\n[STEP 2] Skipping scrape (--skip-scrape)")

    # -----------------------------------------------------------------------
    # Step 2b: Import manually entered seller deals from Excel
    # -----------------------------------------------------------------------
    sellers_excel = ROOT / "data" / "SELLERS_TEMPLATE.xlsx"
    if sellers_excel.exists():
        run_tool("import_sellers_excel.py", [
            "--excel", str(sellers_excel),
            "--out", str(tmp_dir / "raw_listings_manual.json")
        ], "Import Seller Deals from Excel")
    else:
        print("\n[STEP 2b] No SELLERS_TEMPLATE.xlsx found — skipping manual seller import")

    # -----------------------------------------------------------------------
    # Step 3: Merge listings
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Merging and deduplicating listings...")
    all_listings_path = tmp_dir / "all_listings.json"
    listing_count = merge_listings(tmp_dir, all_listings_path)
    results["listings_merged"] = listing_count

    if listing_count == 0:
        print("[ERROR] No listings to match. Exiting.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 4: Match deals
    # -----------------------------------------------------------------------
    matches_path = tmp_dir / "matches.json"
    ok, _ = run_tool("match_deals.py", [
        "--listings", str(all_listings_path),
        "--buyers", str(buyers_path),
        "--out", str(matches_path),
        "--min-score", str(args.min_score)
    ], "Match Deals")
    results["matching"] = ok

    # -----------------------------------------------------------------------
    # Step 5: Generate emails
    # -----------------------------------------------------------------------
    emails_path = tmp_dir / "email_drafts.json"
    if not args.skip_email:
        email_args = [
            "--matches", str(matches_path),
            "--buyers", str(buyers_path),
            "--listings", str(all_listings_path),
            "--out", str(emails_path),
            "--min-score", str(args.min_email_score)
        ]
        if args.upgrade_a_grade:
            email_args.append("--upgrade-a-grade")

        ok, _ = run_tool("generate_emails.py", email_args, "Generate Email Drafts")
        results["email_generation"] = ok
    else:
        print("\n[STEP 5] Skipping email generation (--skip-email)")

    # -----------------------------------------------------------------------
    # Step 6: Export to Google Sheets
    # -----------------------------------------------------------------------
    if not args.skip_sheets:
        ok, _ = run_tool("export_to_sheets.py", [
            "--matches", str(matches_path),
            "--emails", str(emails_path),
            "--listings", str(all_listings_path)
        ], "Export to Google Sheets")
        results["sheets_export"] = ok
    else:
        print("\n[STEP 6] Skipping Sheets export (--skip-sheets)")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print_summary(matches_path, emails_path, start_time)


if __name__ == "__main__":
    main()
