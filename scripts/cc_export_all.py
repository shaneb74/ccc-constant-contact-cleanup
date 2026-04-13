"""
Phase 1: Full export of Constant Contact account state.

Exports:
  1. All CC contacts (all statuses) with full metadata including list memberships
  2. All CC lists with member counts
  3. All QB email contacts (WA Clients, Contacts, Prospects, CCSN Partner Contacts)
  4. State snapshot summary

Outputs to ../exports/:
  cc_full_export_YYYY-MM-DD.json
  cc_lists_YYYY-MM-DD.json
  qb_contacts_YYYY-MM-DD.json
  state_snapshot_YYYY-MM-DD.md

Read-only. No writes to CC or QB.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Add parent paths so we can import shared modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "production"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db_secrets import load_local_env
from cc_account_audit import refresh_access_token, require_env, CC_BASE_URL

load_local_env()

TODAY = date.today().isoformat()
EXPORTS_DIR = Path(__file__).resolve().parent.parent / "exports"
RATE_DELAY = 0.34  # ~3 req/sec, under CC's 4/sec limit

# QB config
QB_REALM = require_env("QB_REALM")
QB_TOKEN = require_env("QB_TOKEN")
QB_HEADERS = {
    "QB-Realm-Hostname": QB_REALM,
    "Authorization": f"QB-USER-TOKEN {QB_TOKEN}",
    "Content-Type": "application/json",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# QB tables with email fields
QB_EMAIL_TABLES = {
    "bkpvi5e32": {
        "name": "WA Clients",
        "fids": [(67, "Representative Email"), (25, "Alternative Contact Email"),
                 (61, "Referral Source Email")],
    },
    "bkqfsmeuq": {
        "name": "Contacts",
        "fids": [(17, "Email"), (51, "Record-Email")],
    },
    "bksjvvngk": {
        "name": "Prospects",
        "fids": [(8, "Email"), (238, "CCSN Email")],
    },
    "bvx69kb96": {
        "name": "CCSN Partner Contacts",
        "fids": [(9, "Email")],  # Verified FID 9 = Email field
    },
}

# ── CC Auth ──────────────────────────────────────────────────────────────

_cc_token: str | None = None
_cc_new_refresh: str | None = None


def get_cc_token() -> str:
    global _cc_token, _cc_new_refresh
    if _cc_token is None:
        tokens = refresh_access_token(
            require_env("CC_REFRESH_TOKEN"),
            require_env("CC_CLIENT_ID"),
        )
        _cc_token = tokens["access_token"]
        nr = tokens.get("refresh_token")
        if nr and nr != os.getenv("CC_REFRESH_TOKEN"):
            _cc_new_refresh = nr
            print(f"\n⚠ CC issued new refresh token. Update .env.local:\n  CC_REFRESH_TOKEN={nr}\n",
                  file=sys.stderr)
    return _cc_token


def cc_get(path: str, params: dict | None = None) -> dict | None:
    time.sleep(RATE_DELAY)
    headers = {"Authorization": f"Bearer {get_cc_token()}", "Accept": "application/json"}
    url = path if path.startswith("http") else f"{CC_BASE_URL}{path}"
    r = requests.get(url, headers=headers, params=params or {})
    if not r.ok:
        print(f"  [WARN] CC {r.status_code} on {url}", file=sys.stderr)
        return None
    return r.json()


def cc_paginate(path: str, params: dict, items_key: str | None = None,
                max_pages: int = 200) -> list[dict]:
    out: list[dict] = []
    next_url = path if path.startswith("http") else f"{CC_BASE_URL}{path}"
    next_params = dict(params)
    pages = 0
    while pages < max_pages:
        data = cc_get(next_url, next_params)
        if data is None:
            break
        if items_key and items_key in data:
            items = data[items_key]
        else:
            items = []
            for v in data.values():
                if isinstance(v, list):
                    items = v
                    break
        out.extend(items)
        if pages % 10 == 0:
            print(f"  ... {len(out)} records (page {pages + 1})", file=sys.stderr)
        links = data.get("_links") or {}
        nxt = (links.get("next") or {}).get("href")
        if not nxt:
            break
        next_url = "https://api.cc.email" + nxt if nxt.startswith("/v3") else nxt
        next_params = {}
        pages += 1
    return out


# ── CC Exports ───────────────────────────────────────────────────────────

def export_cc_contacts() -> list[dict]:
    """Pull all CC contacts with full metadata including list memberships."""
    print("\n[1/4] Exporting all CC contacts (status=all, with list memberships)...", file=sys.stderr)
    contacts = cc_paginate(
        "/contacts",
        {
            "status": "all",
            "limit": 500,
            "include": "list_memberships,custom_fields,phone_numbers,street_addresses,notes,taggings",
        },
        items_key="contacts",
    )
    print(f"  Total CC contacts exported: {len(contacts)}", file=sys.stderr)
    return contacts


def export_cc_lists() -> list[dict]:
    """Pull all CC lists with member counts."""
    print("\n[2/4] Exporting all CC lists...", file=sys.stderr)
    lists = cc_paginate(
        "/contact_lists",
        {"limit": 500, "include_count": "true"},
        items_key="lists",
    )
    print(f"  Total CC lists: {len(lists)}", file=sys.stderr)
    return lists


# ── QB Exports ───────────────────────────────────────────────────────────

def qb_query_all(table_id: str, select_fids: list[int], label: str) -> list[dict]:
    """Pull all records from a QB table."""
    url = "https://api.quickbase.com/v1/records/query"
    out = []
    skip = 0
    while True:
        body = {
            "from": table_id,
            "select": [3] + select_fids,  # 3 = Record ID
            "options": {"skip": skip, "top": 1000},
        }
        r = requests.post(url, headers=QB_HEADERS, json=body)
        if not r.ok:
            print(f"  [WARN] QB {table_id} ({label}): {r.status_code} {r.text[:200]}", file=sys.stderr)
            break
        data = r.json().get("data", [])
        out.extend(data)
        if len(data) < 1000:
            break
        skip += 1000
    print(f"  {label}: {len(out)} records", file=sys.stderr)
    return out


def export_qb_contacts() -> dict:
    """Pull all QB email contacts and return structured data."""
    print("\n[3/4] Exporting QB contacts...", file=sys.stderr)
    result = {}
    all_emails: dict[str, dict] = {}  # email -> {sources: [...], tables: [...]}

    for table_id, info in QB_EMAIL_TABLES.items():
        name = info["name"]
        fids = [f[0] for f in info["fids"]]
        records = qb_query_all(table_id, fids, name)

        table_emails = {}
        for rec in records:
            rid = (rec.get("3") or {}).get("value")
            for fid, field_name in info["fids"]:
                cell = rec.get(str(fid)) or {}
                v = (cell.get("value") or "").strip().lower()
                if v and EMAIL_RE.match(v):
                    if v not in table_emails:
                        table_emails[v] = {"field": field_name, "record_ids": []}
                    table_emails[v]["record_ids"].append(rid)

                    if v not in all_emails:
                        all_emails[v] = {"tables": [], "first_seen_table": name}
                    if name not in all_emails[v]["tables"]:
                        all_emails[v]["tables"].append(name)

        result[name] = {
            "table_id": table_id,
            "total_records": len(records),
            "unique_emails": len(table_emails),
            "emails": table_emails,
        }

    result["_all_unique_emails"] = list(all_emails.keys())
    result["_email_metadata"] = all_emails
    result["_total_unique"] = len(all_emails)
    print(f"  Total unique QB emails: {len(all_emails)}", file=sys.stderr)
    return result


# ── State Snapshot ───────────────────────────────────────────────────────

def build_snapshot(cc_contacts: list[dict], cc_lists: list[dict],
                   qb_data: dict) -> str:
    """Build a markdown summary of current state."""
    # CC contact status breakdown
    status_counts: Counter = Counter()
    opt_in_counts: Counter = Counter()
    engagement_12mo = 0
    now = datetime.now(timezone.utc)

    for c in cc_contacts:
        ea = c.get("email_address") or {}
        perm = ea.get("permission_to_send", "unknown")
        status_counts[perm] += 1

        opt_source = ea.get("opt_in_source") or "unknown"
        opt_in_counts[opt_source] += 1

    # List membership counts
    list_sizes = [(lst.get("name", ""), lst.get("membership_count", 0), lst.get("list_id", ""))
                  for lst in cc_lists]
    list_sizes.sort(key=lambda x: -x[1])

    # Cross-reference
    cc_emails = set()
    for c in cc_contacts:
        ea = c.get("email_address") or {}
        addr = (ea.get("address") or "").strip().lower()
        if addr:
            cc_emails.add(addr)

    qb_emails = set(qb_data.get("_all_unique_emails", []))
    overlap = cc_emails & qb_emails
    cc_only = cc_emails - qb_emails
    qb_only = qb_emails - cc_emails

    lines = [
        f"# CC Cleanup — State Snapshot ({TODAY})",
        "",
        "## CC Contact Counts by Status",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
    ]
    for status, count in status_counts.most_common():
        lines.append(f"| {status} | {count:,} |")
    lines.append(f"| **TOTAL** | **{len(cc_contacts):,}** |")

    lines += [
        "",
        "## CC Opt-in Source Distribution",
        "",
        "| Source | Count |",
        "|--------|-------|",
    ]
    for source, count in opt_in_counts.most_common():
        lines.append(f"| {source} | {count:,} |")

    lines += [
        "",
        "## CC Lists (top 30 by size)",
        "",
        "| List Name | Members | List ID |",
        "|-----------|---------|---------|",
    ]
    for name, count, lid in list_sizes[:30]:
        lines.append(f"| {name} | {count:,} | {lid} |")
    lines.append(f"| ... ({len(list_sizes)} total lists) | | |")

    lines += [
        "",
        "## QB ↔ CC Cross-Reference",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Unique CC emails | {len(cc_emails):,} |",
        f"| Unique QB emails | {len(qb_emails):,} |",
        f"| In BOTH (overlap) | {len(overlap):,} |",
        f"| CC-only (not in QB) | {len(cc_only):,} |",
        f"| QB-only (not in CC) | {len(qb_only):,} |",
        "",
        "## QB Table Breakdown",
        "",
        "| Table | Records | Unique Emails |",
        "|-------|---------|---------------|",
    ]
    for tname in ["WA Clients", "Contacts", "Prospects", "CCSN Partner Contacts"]:
        tdata = qb_data.get(tname, {})
        lines.append(f"| {tname} | {tdata.get('total_records', 0):,} | {tdata.get('unique_emails', 0):,} |")

    lines += ["", f"*Generated {datetime.now(timezone.utc).isoformat()}*", ""]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 70, file=sys.stderr)
    print("CC CLEANUP — PHASE 1: FULL EXPORT", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. CC contacts
    cc_contacts = export_cc_contacts()
    cc_file = EXPORTS_DIR / f"cc_full_export_{TODAY}.json"
    with open(cc_file, "w") as f:
        json.dump(cc_contacts, f, indent=2, default=str)
    print(f"  Saved: {cc_file}", file=sys.stderr)

    # 2. CC lists
    cc_lists = export_cc_lists()
    lists_file = EXPORTS_DIR / f"cc_lists_{TODAY}.json"
    with open(lists_file, "w") as f:
        json.dump(cc_lists, f, indent=2, default=str)
    print(f"  Saved: {lists_file}", file=sys.stderr)

    # 3. QB contacts
    qb_data = export_qb_contacts()
    qb_file = EXPORTS_DIR / f"qb_contacts_{TODAY}.json"
    with open(qb_file, "w") as f:
        json.dump(qb_data, f, indent=2, default=str)
    print(f"  Saved: {qb_file}", file=sys.stderr)

    # 4. State snapshot
    print("\n[4/4] Building state snapshot...", file=sys.stderr)
    snapshot = build_snapshot(cc_contacts, cc_lists, qb_data)
    snap_file = EXPORTS_DIR / f"state_snapshot_{TODAY}.md"
    with open(snap_file, "w") as f:
        f.write(snapshot)
    print(f"  Saved: {snap_file}", file=sys.stderr)

    # Quick summary
    print("\n" + "=" * 70, file=sys.stderr)
    print("EXPORT COMPLETE", file=sys.stderr)
    print(f"  CC contacts: {len(cc_contacts)}", file=sys.stderr)
    print(f"  CC lists:    {len(cc_lists)}", file=sys.stderr)
    print(f"  QB emails:   {qb_data.get('_total_unique', 0)}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    if _cc_new_refresh:
        print(f"\n!! UPDATE .env.local with new CC_REFRESH_TOKEN: {_cc_new_refresh}", file=sys.stderr)


if __name__ == "__main__":
    main()
