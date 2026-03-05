"""
export_to_sheets.py
-------------------
Pushes matched deals and generated email drafts to Google Sheets.

Requires:
- GOOGLE_SHEET_ID in .env (the Sheet ID from the URL)
- credentials.json in project root (Google Cloud OAuth2 service account or desktop credentials)
- Run once interactively to authorize: token.json is created automatically

Sheet tabs created/updated:
  1. "Matches"      — one row per match, sorted by score
  2. "Email Drafts" — one row per email draft with subject + body
  3. "All Listings" — raw dump of all scraped listings

Usage:
    python tools/export_to_sheets.py
    python tools/export_to_sheets.py --matches .tmp/matches.json --emails .tmp/email_drafts.json --listings .tmp/all_listings.json
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = "token.json"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_sheets_service():
    creds = None
    if Path(TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDS_PATH).exists():
                print(f"[ERROR] {CREDS_PATH} not found.")
                print("[INFO] Download OAuth2 credentials from Google Cloud Console:")
                print("  1. Go to console.cloud.google.com")
                print("  2. Enable Google Sheets API")
                print("  3. Create OAuth2 credentials (Desktop app)")
                print("  4. Download as credentials.json to project root")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_PATH).write_text(creds.to_json())

    return build("sheets", "v4", credentials=creds)


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------

def ensure_sheet_tab(service, sheet_id: str, tab_name: str) -> int:
    """Create tab if it doesn't exist. Returns sheetId."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"]
                for s in meta.get("sheets", [])}

    if tab_name in existing:
        return existing[tab_name]

    body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
    resp = service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def clear_and_write(service, sheet_id: str, tab_name: str, rows: list[list]):
    """Clear the tab and write all rows (header + data)."""
    range_name = f"'{tab_name}'!A1"
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": rows}
    ).execute()
    print(f"  [Sheets] '{tab_name}': wrote {len(rows) - 1} rows")


def fmt(val) -> str:
    """Format a value for Sheets (None -> '')."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------

def build_matches_rows(matches: list[dict]) -> list[list]:
    headers = [
        "Grade", "Score %", "Buyer Name", "Business Title", "Source",
        "Location", "Industry", "Asking Price", "Revenue", "Cash Flow",
        "Soft Flags", "Deal URL", "Match ID", "Matched At"
    ]
    rows = [headers]
    for m in sorted(matches, key=lambda x: x.get("score_pct", 0), reverse=True):
        rows.append([
            fmt(m.get("grade")),
            fmt(m.get("score_pct")),
            fmt(m.get("buyer_name")),
            fmt(m.get("deal_title")),
            fmt(m.get("deal_source")),
            fmt(m.get("deal_location")),
            fmt(m.get("deal_industry")),
            fmt(m.get("deal_asking_price_raw")),
            fmt(m.get("deal_revenue_raw")),
            fmt(m.get("deal_cash_flow_raw")),
            fmt("; ".join(m.get("soft_flags", []))),
            fmt(m.get("deal_url")),
            fmt(m.get("match_id")),
            fmt(m.get("matched_at")),
        ])
    return rows


def build_email_rows(drafts: list[dict]) -> list[list]:
    headers = [
        "Grade", "Score %", "Buyer Name", "Business Title", "Location",
        "Source", "Subject Line", "Email Body",
        "Model Used", "Tokens", "Generated At", "Deal URL"
    ]
    rows = [headers]
    for d in sorted(drafts, key=lambda x: x.get("score_pct", 0), reverse=True):
        rows.append([
            fmt(d.get("grade")),
            fmt(d.get("score_pct")),
            fmt(d.get("buyer_name")),
            fmt(d.get("deal_title")),
            fmt(d.get("deal_location")),
            fmt(d.get("deal_source")),
            fmt(d.get("subject")),
            fmt(d.get("body")),
            fmt(d.get("model_used")),
            fmt(d.get("tokens_used")),
            fmt(d.get("generated_at")),
            fmt(d.get("deal_url")),
        ])
    return rows


def build_listings_rows(listings: list[dict]) -> list[list]:
    headers = [
        "Source", "Title", "Industry", "Location City", "State",
        "Asking Price", "Revenue", "Cash Flow", "SBA Eligible",
        "Financing", "Date Listed", "Date Scraped", "URL", "Deal ID"
    ]
    rows = [headers]
    for l in listings:
        rows.append([
            fmt(l.get("source")),
            fmt(l.get("title")),
            fmt(l.get("industry")),
            fmt(l.get("location_city")),
            fmt(l.get("location_state")),
            fmt(l.get("asking_price_raw")),
            fmt(l.get("annual_revenue_raw")),
            fmt(l.get("cash_flow_raw")),
            fmt(l.get("sba_eligible")),
            fmt(l.get("financing_available")),
            fmt(l.get("date_listed")),
            fmt(l.get("date_scraped")),
            fmt(l.get("url")),
            fmt(l.get("deal_id")),
        ])
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export matches and email drafts to Google Sheets")
    parser.add_argument("--matches", default=".tmp/matches.json")
    parser.add_argument("--emails", default=".tmp/email_drafts.json")
    parser.add_argument("--listings", default=".tmp/all_listings.json")
    parser.add_argument("--sheet-id", default=SHEET_ID)
    args = parser.parse_args()

    if not args.sheet_id or args.sheet_id == "REPLACE_ME":
        print("[ERROR] GOOGLE_SHEET_ID not set in .env")
        print("[INFO] Create a Google Sheet, copy its ID from the URL, add to .env")
        return

    # Load data
    matches = []
    emails = []
    listings = []

    for path, container, label in [
        (args.matches, matches, "matches"),
        (args.emails, emails, "email drafts"),
        (args.listings, listings, "listings"),
    ]:
        p = Path(path)
        if p.exists():
            container.extend(json.loads(p.read_text()))
            print(f"[INFO] Loaded {len(container)} {label}")
        else:
            print(f"[WARN] {path} not found, skipping {label} tab")

    service = get_sheets_service()
    if not service:
        return

    sheet_id = args.sheet_id

    # Ensure all tabs exist
    for tab in ["Matches", "Email Drafts", "All Listings"]:
        ensure_sheet_tab(service, sheet_id, tab)

    # Write data
    if matches:
        clear_and_write(service, sheet_id, "Matches", build_matches_rows(matches))
    if emails:
        clear_and_write(service, sheet_id, "Email Drafts", build_email_rows(emails))
    if listings:
        clear_and_write(service, sheet_id, "All Listings", build_listings_rows(listings))

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"\n[DONE] Export complete: {sheet_url}")


if __name__ == "__main__":
    main()
