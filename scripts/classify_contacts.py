"""
Phase 2: Classify CC contacts into KEEP / ARCHIVE / PURGE buckets.

Loads Phase 1 exports and pulls 12-month engagement data from CC campaign
tracking APIs to determine which contacts have recently engaged.

Classification rules:
  KEEP:
    - explicit opt-in consent, OR
    - email exists in QuickBase (active relationship), OR
    - opened or clicked any email in the last 12 months, OR
    - is a CCSN partner contact (QB table bvx69kb96)

  PURGE:
    - unsubscribed (permission_to_send = "unsubscribed"), OR
    - hard bounce address (no engagement, not in QB), OR
    - clearly invalid/junk email (role accounts, typos), OR
    - duplicate email (keep the one with more metadata)

  ARCHIVE (everything else):
    - implicit opt-in, no engagement in 12+ months, not in QB

Outputs to ../classifications/:
  keep.json, archive.json, purge.json
  classification_summary.md

Read-only against CC (except tracking data pulls). No writes.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "production"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db_secrets import load_local_env
from cc_account_audit import refresh_access_token, require_env, CC_BASE_URL

load_local_env()

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
BASE_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = BASE_DIR / "exports"
CLASS_DIR = BASE_DIR / "classifications"
RATE_DELAY = 0.34

# Role / junk email patterns
ROLE_PREFIXES = {
    "info", "noreply", "no-reply", "admin", "webmaster", "postmaster",
    "sales", "support", "contact", "office", "hello", "team", "help",
    "billing", "marketing", "hr", "jobs", "careers", "abuse",
    "hostmaster", "security", "mailer-daemon", "donotreply", "do-not-reply",
}
JUNK_PATTERNS = [
    re.compile(r"^test[0-9]*@"),
    re.compile(r"^fake[0-9]*@"),
    re.compile(r"^asdf"),
    re.compile(r"@example\.(com|org|net)$"),
    re.compile(r"@test\.(com|org|net)$"),
    re.compile(r"\.invalid$"),
    re.compile(r"@mailinator\.com$"),
    re.compile(r"@guerrillamail"),
    re.compile(r"@tempmail"),
    re.compile(r"@throwaway"),
]

# ── CC Auth ──────────────────────────────────────────────────────────────

_cc_token: str | None = None


def get_cc_token() -> str:
    global _cc_token
    if _cc_token is None:
        tokens = refresh_access_token(
            require_env("CC_REFRESH_TOKEN"),
            require_env("CC_CLIENT_ID"),
        )
        _cc_token = tokens["access_token"]
        nr = tokens.get("refresh_token")
        if nr and nr != require_env("CC_REFRESH_TOKEN"):
            print(f"\n!! New CC refresh token: {nr}", file=sys.stderr)
    return _cc_token


def cc_get(path: str, params: dict | None = None) -> dict | None:
    time.sleep(RATE_DELAY)
    headers = {"Authorization": f"Bearer {get_cc_token()}", "Accept": "application/json"}
    url = path if path.startswith("http") else f"{CC_BASE_URL}{path}"
    r = requests.get(url, headers=headers, params=params or {})
    if not r.ok:
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
        links = data.get("_links") or {}
        nxt = (links.get("next") or {}).get("href")
        if not nxt:
            break
        next_url = "https://api.cc.email" + nxt if nxt.startswith("/v3") else nxt
        next_params = {}
        pages += 1
    return out


# ── Engagement Tracking ──────────────────────────────────────────────────

def pull_recent_campaigns(months: int = 12) -> list[dict]:
    """Pull all campaigns from the last N months."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=months * 30)).isoformat()
    all_campaigns = cc_paginate("/emails", {"limit": 50}, items_key="campaigns")
    recent = [c for c in all_campaigns
              if c.get("current_status") == "Done"
              and (c.get("updated_at") or "") >= cutoff]
    recent.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return recent


def get_campaign_activity_id(campaign_id: str) -> str | None:
    full = cc_get(f"/emails/{campaign_id}")
    if not full:
        return None
    for act in full.get("campaign_activities", []):
        if act.get("role") == "primary_email":
            return act.get("campaign_activity_id")
    return None


def pull_engaged_contacts(campaigns: list[dict]) -> set[str]:
    """Pull contact_ids that opened or clicked any of the given campaigns."""
    engaged: set[str] = set()
    n = len(campaigns)
    for i, c in enumerate(campaigns, 1):
        cid = c.get("campaign_id")
        name = c.get("name", "")[:50]
        date = (c.get("updated_at") or "")[:10]
        print(f"  [{i}/{n}] {date} {name}", file=sys.stderr)
        aid = get_campaign_activity_id(cid)
        if not aid:
            continue
        for kind in ["opens", "clicks"]:
            items = cc_paginate(
                f"/reports/email_reports/{aid}/tracking/{kind}",
                {"limit": 500},
                items_key="tracking_activities",
            )
            for item in items:
                cid_val = item.get("contact_id")
                if cid_val:
                    engaged.add(cid_val)
    return engaged


# ── Classification Logic ─────────────────────────────────────────────────

def is_role_or_junk(email: str) -> str | None:
    """Return reason string if junk/role, else None."""
    local = email.split("@")[0].lower()
    if local in ROLE_PREFIXES:
        return f"role_account ({local}@)"
    for pat in JUNK_PATTERNS:
        if pat.search(email.lower()):
            return f"junk_pattern ({pat.pattern})"
    return None


def classify(cc_contacts: list[dict], qb_emails: set[str],
             ccsn_emails: set[str], engaged_ids: set[str]) -> dict:
    """Classify every CC contact. Returns {keep: [...], archive: [...], purge: [...]}."""
    keep, archive, purge = [], [], []
    seen_emails: dict[str, dict] = {}  # email -> best contact record

    # First pass: deduplicate by email
    dupes: dict[str, list[dict]] = defaultdict(list)
    for c in cc_contacts:
        ea = c.get("email_address") or {}
        addr = (ea.get("address") or "").strip().lower()
        if not addr:
            purge.append({**_contact_summary(c), "reason": "no_email_address"})
            continue
        dupes[addr].append(c)

    # Process each unique email
    for email, contacts in dupes.items():
        # Pick the best record (most list memberships, most recent update)
        contacts.sort(key=lambda c: (
            len(c.get("list_memberships") or []),
            c.get("updated_at", ""),
        ), reverse=True)
        best = contacts[0]

        # Mark duplicates for purge
        for dup in contacts[1:]:
            purge.append({
                **_contact_summary(dup),
                "reason": f"duplicate_of_{best.get('contact_id')}",
            })

        ea = best.get("email_address") or {}
        perm = ea.get("permission_to_send", "")
        contact_id = best.get("contact_id", "")

        # --- PURGE checks (hard rules) ---

        # Already unsubscribed
        if perm == "unsubscribed":
            purge.append({**_contact_summary(best), "reason": "unsubscribed"})
            continue

        # Role / junk address
        junk_reason = is_role_or_junk(email)
        if junk_reason and email not in qb_emails and contact_id not in engaged_ids:
            purge.append({**_contact_summary(best), "reason": junk_reason})
            continue

        # --- KEEP checks ---

        keep_reasons = []

        # Explicit opt-in
        if perm == "explicit":
            keep_reasons.append("explicit_opt_in")

        # In QuickBase
        if email in qb_emails:
            keep_reasons.append("in_quickbase")

        # CCSN partner contact
        if email in ccsn_emails:
            keep_reasons.append("ccsn_partner_contact")

        # Engaged in last 12 months
        if contact_id in engaged_ids:
            keep_reasons.append("engaged_12mo")

        if keep_reasons:
            keep.append({**_contact_summary(best), "reasons": keep_reasons})
        else:
            # --- ARCHIVE: implicit, no engagement, not in QB ---
            archive.append({
                **_contact_summary(best),
                "reason": "implicit_no_engagement_not_in_qb",
            })

    return {"keep": keep, "archive": archive, "purge": purge}


def _contact_summary(c: dict) -> dict:
    """Extract a summary dict from a raw CC contact for classification output."""
    ea = c.get("email_address") or {}
    return {
        "contact_id": c.get("contact_id", ""),
        "email": (ea.get("address") or "").lower().strip(),
        "first_name": c.get("first_name", ""),
        "last_name": c.get("last_name", ""),
        "permission_to_send": ea.get("permission_to_send", ""),
        "opt_in_source": ea.get("opt_in_source", ""),
        "opt_in_date": ea.get("opt_in_date", ""),
        "opt_out_source": ea.get("opt_out_source", ""),
        "opt_out_date": ea.get("opt_out_date", ""),
        "created_at": c.get("created_at", ""),
        "updated_at": c.get("updated_at", ""),
        "list_memberships": c.get("list_memberships", []),
    }


# ── Summary Report ───────────────────────────────────────────────────────

def build_summary(result: dict, engaged_count: int, campaign_count: int) -> str:
    keep = result["keep"]
    archive = result["archive"]
    purge = result["purge"]
    total = len(keep) + len(archive) + len(purge)

    # Keep reason breakdown
    keep_reasons: Counter = Counter()
    for c in keep:
        for r in c.get("reasons", []):
            keep_reasons[r] += 1

    # Purge reason breakdown
    purge_reasons: Counter = Counter()
    for c in purge:
        purge_reasons[c.get("reason", "unknown")] += 1

    lines = [
        f"# CC Contact Classification Summary ({TODAY})",
        "",
        "## Overview",
        "",
        f"| Bucket | Count | % |",
        f"|--------|-------|---|",
        f"| **KEEP** | {len(keep):,} | {100*len(keep)/max(1,total):.1f}% |",
        f"| **ARCHIVE** | {len(archive):,} | {100*len(archive)/max(1,total):.1f}% |",
        f"| **PURGE** | {len(purge):,} | {100*len(purge)/max(1,total):.1f}% |",
        f"| **TOTAL** | {total:,} | 100% |",
        "",
        f"Engagement scan: {engaged_count:,} unique contacts opened/clicked across {campaign_count} campaigns (last 12 months).",
        "",
        "## KEEP Reasons (contacts may have multiple)",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    for reason, count in keep_reasons.most_common():
        lines.append(f"| {reason} | {count:,} |")

    lines += [
        "",
        "## PURGE Reasons",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    for reason, count in purge_reasons.most_common():
        lines.append(f"| {reason} | {count:,} |")

    lines += [
        "",
        "## Classification Criteria",
        "",
        "### KEEP (stays in CC)",
        "- Has explicit opt-in consent",
        "- Exists in QuickBase as an active relationship",
        "- Has opened or clicked an email in the last 12 months",
        "- Is a CCSN partner contact",
        "",
        "### ARCHIVE (remove from CC, preserve for reimport)",
        "- Implicit opt-in with no engagement in 12+ months",
        "- Not in QuickBase",
        "- Not a CCSN partner",
        "",
        "### PURGE (remove permanently)",
        "- Already unsubscribed",
        "- Role accounts (info@, noreply@, etc.) with no engagement or QB presence",
        "- Junk/invalid addresses",
        "- Duplicate emails (kept the record with most metadata)",
        "",
        f"*Generated {datetime.now(timezone.utc).isoformat()}*",
    ]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 70, file=sys.stderr)
    print("CC CLEANUP — PHASE 2: CLASSIFY CONTACTS", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    CLASS_DIR.mkdir(parents=True, exist_ok=True)

    # Load Phase 1 exports
    print("\nLoading Phase 1 exports...", file=sys.stderr)
    with open(EXPORTS_DIR / f"cc_full_export_{TODAY}.json") as f:
        cc_contacts = json.load(f)
    print(f"  CC contacts: {len(cc_contacts)}", file=sys.stderr)

    with open(EXPORTS_DIR / f"qb_contacts_{TODAY}.json") as f:
        qb_data = json.load(f)
    qb_emails = set(qb_data.get("_all_unique_emails", []))
    print(f"  QB emails: {len(qb_emails)}", file=sys.stderr)

    # CCSN partner contact emails
    ccsn_data = qb_data.get("CCSN Partner Contacts", {})
    ccsn_emails = set(ccsn_data.get("emails", {}).keys())
    print(f"  CCSN partner emails: {len(ccsn_emails)}", file=sys.stderr)

    # Pull engagement data
    print("\nPulling 12-month engagement data from campaign tracking...", file=sys.stderr)
    recent_campaigns = pull_recent_campaigns(12)
    print(f"  Found {len(recent_campaigns)} campaigns in last 12 months", file=sys.stderr)
    engaged_ids = pull_engaged_contacts(recent_campaigns)
    print(f"  Engaged contacts (opened or clicked): {len(engaged_ids)}", file=sys.stderr)

    # Save engaged IDs for audit trail
    with open(CLASS_DIR / "engaged_contact_ids.json", "w") as f:
        json.dump({"count": len(engaged_ids), "contact_ids": sorted(engaged_ids)}, f, indent=2)

    # Classify
    print("\nClassifying contacts...", file=sys.stderr)
    result = classify(cc_contacts, qb_emails, ccsn_emails, engaged_ids)

    # Save classifications
    for bucket in ["keep", "archive", "purge"]:
        path = CLASS_DIR / f"{bucket}.json"
        with open(path, "w") as f:
            json.dump(result[bucket], f, indent=2, default=str)
        print(f"  {bucket}: {len(result[bucket]):,} contacts -> {path.name}", file=sys.stderr)

    # Summary
    summary = build_summary(result, len(engaged_ids), len(recent_campaigns))
    summary_path = CLASS_DIR / f"classification_summary_{TODAY}.md"
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"\n  Summary: {summary_path.name}", file=sys.stderr)

    # Print summary to stdout
    print("\n" + summary)


if __name__ == "__main__":
    main()
