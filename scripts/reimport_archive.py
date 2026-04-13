"""
Reimport archived contacts back into Constant Contact.

Use this ONLY after the subdomain warm-up is complete (minimum 6 weeks
of clean sending with good engagement metrics).

Usage:
  # Dry run — show what would be imported
  python3 reimport_archive.py

  # Import a small test batch (50 contacts)
  python3 reimport_archive.py --execute --batch-size 50

  # Import a larger batch
  python3 reimport_archive.py --execute --batch-size 200

  # Import all archived contacts (use only after successful small batches)
  python3 reimport_archive.py --execute --all

Strategy:
  1. Start with 50-100 contacts
  2. Send re-permission email to the imported batch
  3. Monitor bounce rate (<2%) and spam complaints (<0.1%)
  4. If metrics are clean, scale up batch size
  5. Contacts who don't engage after 2 re-permission emails stay archived permanently

The script adds reimported contacts to a dedicated "Reimport - Re-Permission"
list so they can be targeted with the re-permission campaign.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "production"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db_secrets import load_local_env
from cc_account_audit import refresh_access_token, require_env, CC_BASE_URL

load_local_env()

BASE = Path(__file__).resolve().parent.parent
CLASS = BASE / "classifications"
LOGS = BASE / "logs"
RATE_DELAY = 0.5
REIMPORT_LIST_NAME = "Reimport - Re-Permission"

_token: str | None = None


def get_token() -> str:
    global _token
    if _token is None:
        tokens = refresh_access_token(
            require_env("CC_REFRESH_TOKEN"),
            require_env("CC_CLIENT_ID"),
        )
        _token = tokens["access_token"]
        nr = tokens.get("refresh_token")
        if nr and nr != os.getenv("CC_REFRESH_TOKEN"):
            print(f"\n!! New CC refresh token: {nr}", file=sys.stderr)
    return _token


def cc_request(method: str, path: str, body: dict | None = None,
               params: dict | None = None) -> dict | None:
    time.sleep(RATE_DELAY)
    url = path if path.startswith("http") else f"{CC_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = requests.request(method, url, headers=headers, json=body, params=params)
    if not r.ok:
        print(f"  [ERR] {method} {path}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    if r.status_code == 204:
        return {}
    return r.json()


def get_or_create_list(list_name: str) -> str | None:
    """Find or create the reimport list. Returns list_id."""
    # Search existing lists
    data = cc_request("GET", "/contact_lists", params={"limit": 500})
    if data:
        for lst in data.get("lists", []):
            if lst.get("name") == list_name:
                print(f"  Found existing list: {list_name} ({lst['list_id']})", file=sys.stderr)
                return lst["list_id"]

    # Create new list
    result = cc_request("POST", "/contact_lists", {
        "name": list_name,
        "description": f"Contacts reimported from archive.json for re-permission campaign. Created {datetime.now(timezone.utc).isoformat()}",
        "favorite": False,
    })
    if result:
        lid = result.get("list_id")
        print(f"  Created list: {list_name} ({lid})", file=sys.stderr)
        return lid
    return None


def reimport_contact(contact: dict, list_id: str) -> bool:
    """Add a single archived contact back to CC on the reimport list."""
    email = contact.get("email", "")
    if not email:
        return False

    body = {
        "email_address": {"address": email, "permission_to_send": "implicit"},
        "first_name": contact.get("first_name", ""),
        "last_name": contact.get("last_name", ""),
        "list_memberships": [list_id],
        "update_source": "Account",
    }

    result = cc_request("POST", "/contacts/sign_up_form", body=body)
    return result is not None


def poll_activity(activity_id: str) -> bool:
    for _ in range(60):
        time.sleep(5)
        status = cc_request("GET", f"/activities/{activity_id}")
        if status and status.get("state") == "completed":
            return True
        if status and status.get("state") in ("cancelled", "failed"):
            return False
    return False


def bulk_reimport(contacts: list[dict], list_id: str) -> dict:
    """Bulk import contacts using the add-contacts activity endpoint."""
    # Build the import payload
    import_data = []
    for c in contacts:
        email = c.get("email", "")
        if not email:
            continue
        import_data.append({
            "email": email,
            "first_name": c.get("first_name", ""),
            "last_name": c.get("last_name", ""),
        })

    # CC bulk import: POST /activities/contacts_json_import
    body = {
        "import_data": import_data,
        "list_ids": [list_id],
        "column_names": ["email", "first_name", "last_name"],
    }

    result = cc_request("POST", "/activities/contacts_json_import", body)
    if not result:
        return {"success": 0, "failed": len(import_data)}

    activity_id = result.get("activity_id")
    print(f"  Import activity started: {activity_id}", file=sys.stderr)
    ok = poll_activity(activity_id)

    if ok:
        return {"success": len(import_data), "failed": 0, "activity_id": activity_id}
    else:
        return {"success": 0, "failed": len(import_data), "activity_id": activity_id}


def main():
    parser = argparse.ArgumentParser(description="Reimport archived CC contacts")
    parser.add_argument("--execute", action="store_true", help="Actually import (default is dry-run)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of contacts to import (default 50)")
    parser.add_argument("--all", action="store_true", help="Import all archived contacts (use with caution)")
    parser.add_argument("--offset", type=int, default=0, help="Start from this index in the archive (for resuming)")
    args = parser.parse_args()

    print("=" * 60, file=sys.stderr)
    print("CC CLEANUP — REIMPORT ARCHIVED CONTACTS", file=sys.stderr)
    print(f"  Mode: {'LIVE' if args.execute else 'DRY RUN'}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Load archive
    with open(CLASS / "archive.json") as f:
        archive = json.load(f)
    print(f"  Total archived contacts: {len(archive)}", file=sys.stderr)

    # Select batch
    if args.all:
        batch = archive[args.offset:]
        print(f"  Importing ALL {len(batch)} contacts (offset {args.offset})", file=sys.stderr)
    else:
        batch = archive[args.offset:args.offset + args.batch_size]
        print(f"  Importing batch of {len(batch)} (offset {args.offset}, batch-size {args.batch_size})", file=sys.stderr)

    if not batch:
        print("  No contacts to import.", file=sys.stderr)
        return

    # Show sample
    print(f"\n  Sample (first 5):", file=sys.stderr)
    for c in batch[:5]:
        print(f"    {c.get('email', '?'):<40} {c.get('first_name', '')} {c.get('last_name', '')}", file=sys.stderr)

    if not args.execute:
        print(f"\n  DRY RUN — no contacts imported. Use --execute to import.", file=sys.stderr)
        return

    # Get or create the reimport list
    list_id = get_or_create_list(REIMPORT_LIST_NAME)
    if not list_id:
        print("  ABORT: Could not create reimport list", file=sys.stderr)
        sys.exit(1)

    # Import
    result = bulk_reimport(batch, list_id)
    print(f"\n  Result: {result['success']} imported, {result['failed']} failed", file=sys.stderr)

    # Log
    LOGS.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "batch_size": len(batch),
        "offset": args.offset,
        "result": result,
        "list_id": list_id,
    }
    log_path = LOGS / f"reimport_log_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"  Log appended: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
