"""
subscribers.py — Email newsletter subscriber list management.

Subscribers are stored in SQLite (.tmp/social.db → subscribers table).

Bulk import format:
  CSV with header row: email,first_name,last_name
  first_name and last_name are optional columns.
"""

import csv
import sys
from pathlib import Path
from . import db as db_module


def add_subscriber(email: str, first_name: str = None,
                   last_name: str = None, verbose: bool = True) -> bool:
    """
    Add a subscriber to the list.

    Returns True if added, False if already exists.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        if verbose:
            print(f"  [ERROR] Invalid email: {email}")
        return False

    added = db_module.add_subscriber(email, first_name, last_name)
    if verbose:
        if added:
            name_part = f" ({first_name})" if first_name else ""
            print(f"  [SUBSCRIBER] Added: {email}{name_part}")
        else:
            print(f"  [SUBSCRIBER] Already exists: {email}")
    return added


def remove_subscriber(email: str, verbose: bool = True) -> bool:
    """
    Mark a subscriber as unsubscribed.

    Returns True if found, False if not in list.
    """
    email = email.strip().lower()
    found = db_module.remove_subscriber(email)
    if verbose:
        if found:
            print(f"  [SUBSCRIBER] Unsubscribed: {email}")
        else:
            print(f"  [SUBSCRIBER] Not found: {email}")
    return found


def bulk_import_subscribers(csv_path: str, verbose: bool = True) -> tuple:
    """
    Import subscribers from a CSV file.

    Expected CSV format (header required):
        email,first_name,last_name

    Columns first_name and last_name are optional.

    Returns:
        Tuple of (added_count, skipped_count)
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"  [ERROR] File not found: {csv_path}")
        return 0, 0

    added = 0
    skipped = 0
    errors = []

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("  [ERROR] CSV has no headers. Expected: email,first_name,last_name")
            return 0, 0

        # Case-insensitive header matching
        headers_lower = {h.lower(): h for h in reader.fieldnames}

        for row_num, row in enumerate(reader, start=2):
            email_key = headers_lower.get("email", "")
            email = row.get(email_key, "").strip().lower()

            if not email or "@" not in email:
                errors.append(f"Row {row_num}: invalid email '{email}'")
                skipped += 1
                continue

            fn_key = headers_lower.get("first_name") or headers_lower.get("firstname")
            ln_key = headers_lower.get("last_name") or headers_lower.get("lastname")

            first_name = row.get(fn_key, "").strip() if fn_key else None
            last_name = row.get(ln_key, "").strip() if ln_key else None

            was_added = db_module.add_subscriber(
                email,
                first_name or None,
                last_name or None
            )

            if was_added:
                added += 1
            else:
                skipped += 1

    if verbose:
        print(f"  [IMPORT] Imported {added} new subscribers, skipped {skipped} (already exist or invalid)")
        if errors:
            print(f"  [IMPORT] {len(errors)} errors:")
            for err in errors[:5]:
                print(f"    {err}")
            if len(errors) > 5:
                print(f"    ... and {len(errors)-5} more")

    return added, skipped


def list_subscribers(limit: int = 50) -> list:
    """Return list of active subscribers (up to limit)."""
    conn = db_module.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE status='active' ORDER BY added_at LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def print_subscriber_summary() -> None:
    """Print a summary of subscriber counts by status."""
    counts = db_module.count_subscribers()
    total = sum(counts.values())
    active = counts.get("active", 0)
    unsub = counts.get("unsubscribed", 0)
    bounced = counts.get("bounced", 0)

    print(f"\n  Email Subscribers:")
    print(f"    Active:        {active}")
    if unsub:
        print(f"    Unsubscribed:  {unsub}")
    if bounced:
        print(f"    Bounced:       {bounced}")
    print(f"    Total ever:    {total}")


def manage_subscribers(action: str, email: str = None,
                       name: str = None, csv_file: str = None) -> None:
    """
    Dispatcher for subscriber management actions.

    Args:
        action: "add", "remove", "import", "list", "summary"
        email: email address (for add/remove)
        name: "First Last" string (for add)
        csv_file: path to CSV (for import)
    """
    if action == "add":
        if not email:
            print("[ERROR] Email required for --add-subscriber")
            return
        first_name, last_name = None, None
        if name:
            parts = name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else None
        add_subscriber(email, first_name, last_name)

    elif action == "remove":
        if not email:
            print("[ERROR] Email required for --remove-subscriber")
            return
        remove_subscriber(email)

    elif action == "import":
        if not csv_file:
            print("[ERROR] CSV file path required for --import-subscribers")
            return
        bulk_import_subscribers(csv_file)

    elif action == "list":
        subs = list_subscribers(limit=100)
        if not subs:
            print("  No active subscribers yet.")
            print("  Add some: python tools/run_social.py --add-subscriber email@example.com")
            return
        print(f"\n  {'Email':<35} {'First Name':<15} {'Added'}")
        print("  " + "-" * 70)
        for s in subs[:50]:
            print(f"  {s['email']:<35} {s.get('first_name',''):<15} {s.get('added_at','')[:10]}")
        if len(subs) > 50:
            print(f"  ... and {len(subs)-50} more")

    elif action == "summary":
        print_subscriber_summary()

    else:
        print(f"[ERROR] Unknown subscriber action: {action}")
