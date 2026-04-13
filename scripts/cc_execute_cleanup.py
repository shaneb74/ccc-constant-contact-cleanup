"""
Phase 3: Execute CC cleanup — delete PURGE and ARCHIVE contacts.

Uses the CC bulk delete activity endpoint (POST /activities/contact_delete).
Max 500 contact_ids per request. Batches automatically.

Logs every API action to ../logs/cleanup_log_YYYY-MM-DD.md

Safety:
  - Phase 1 exports must exist (verified at startup)
  - Dry-run by default (--execute to actually delete)
  - Deletes PURGE first, then ARCHIVE
  - Polls each activity to completion before proceeding
"""
from __future__ import annotations

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

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
BASE = Path(__file__).resolve().parent.parent
EXPORTS = BASE / "exports"
CLASS = BASE / "classifications"
LOGS = BASE / "logs"
RATE_DELAY = 0.5  # slightly more conservative for write operations

_token: str | None = None
_new_refresh: str | None = None


def get_token() -> str:
    global _token, _new_refresh
    if _token is None:
        tokens = refresh_access_token(
            require_env("CC_REFRESH_TOKEN"),
            require_env("CC_CLIENT_ID"),
        )
        _token = tokens["access_token"]
        nr = tokens.get("refresh_token")
        if nr and nr != os.getenv("CC_REFRESH_TOKEN"):
            _new_refresh = nr
            print(f"\n!! New CC refresh token: {nr}", file=sys.stderr)
    return _token


def cc_post(path: str, body: dict) -> dict | None:
    time.sleep(RATE_DELAY)
    url = f"{CC_BASE_URL}{path}"
    r = requests.post(url, headers={
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, json=body)
    if not r.ok:
        print(f"  [ERR] POST {path}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def cc_get(path: str) -> dict | None:
    time.sleep(RATE_DELAY)
    url = path if path.startswith("http") else f"{CC_BASE_URL}{path}"
    r = requests.get(url, headers={
        "Authorization": f"Bearer {get_token()}",
        "Accept": "application/json",
    })
    if not r.ok:
        return None
    return r.json()


def poll_activity(activity_id: str, label: str, log_lines: list[str]) -> bool:
    """Poll an activity until complete. Returns True if successful."""
    max_polls = 120  # 10 minutes at 5s intervals
    for i in range(max_polls):
        time.sleep(5)
        status = cc_get(f"/activities/{activity_id}")
        if status is None:
            continue
        state = status.get("state", "")
        pct = status.get("percent_done", 0)
        errors = len(status.get("activity_errors", []))
        if i % 6 == 0:  # log every 30s
            print(f"    {label}: {state} ({pct}% done, {errors} errors)", file=sys.stderr)
        if state == "completed":
            msg = f"  Activity {activity_id}: completed ({pct}% done, {errors} errors)"
            log_lines.append(msg)
            print(msg, file=sys.stderr)
            if errors > 0:
                for err in status.get("activity_errors", [])[:10]:
                    log_lines.append(f"    Error: {err}")
            return True
        if state in ("cancelled", "failed"):
            msg = f"  Activity {activity_id}: {state} — errors: {status.get('activity_errors', [])[:5]}"
            log_lines.append(msg)
            print(msg, file=sys.stderr)
            return False
    log_lines.append(f"  Activity {activity_id}: timed out after polling")
    return False


def delete_batch(contact_ids: list[str], label: str, batch_num: int,
                 total_batches: int, log_lines: list[str], dry_run: bool) -> bool:
    """Delete a batch of up to 500 contacts. Returns True if successful."""
    tag = f"[{label} batch {batch_num}/{total_batches}]"
    msg = f"{tag} Deleting {len(contact_ids)} contacts..."
    log_lines.append(msg)
    print(f"  {msg}", file=sys.stderr)

    if dry_run:
        log_lines.append(f"  {tag} DRY RUN — skipped")
        return True

    result = cc_post("/activities/contact_delete", {"contact_ids": contact_ids})
    if result is None:
        log_lines.append(f"  {tag} FAILED — API returned error")
        return False

    activity_id = result.get("activity_id")
    log_lines.append(f"  {tag} Activity started: {activity_id}")
    return poll_activity(activity_id, tag, log_lines)


def process_bucket(contacts: list[dict], label: str, log_lines: list[str],
                   dry_run: bool) -> dict:
    """Delete all contacts in a bucket. Returns stats."""
    ids = [c["contact_id"] for c in contacts if c.get("contact_id")]
    # Deduplicate (safety)
    ids = list(dict.fromkeys(ids))

    total = len(ids)
    batches = [ids[i:i+500] for i in range(0, total, 500)]
    total_batches = len(batches)

    log_lines.append(f"\n{'='*60}")
    log_lines.append(f"Processing {label}: {total} contacts in {total_batches} batches")
    log_lines.append(f"{'='*60}")
    print(f"\n  Processing {label}: {total} contacts in {total_batches} batches", file=sys.stderr)

    succeeded = 0
    failed = 0
    for i, batch in enumerate(batches, 1):
        ok = delete_batch(batch, label, i, total_batches, log_lines, dry_run)
        if ok:
            succeeded += len(batch)
        else:
            failed += len(batch)

    stats = {"total": total, "succeeded": succeeded, "failed": failed, "batches": total_batches}
    log_lines.append(f"\n  {label} DONE: {succeeded} succeeded, {failed} failed")
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 3: Execute CC cleanup")
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete contacts (default is dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 70, file=sys.stderr)
    print("CC CLEANUP — PHASE 3: EXECUTE", file=sys.stderr)
    if dry_run:
        print("  *** DRY RUN — no contacts will be deleted ***", file=sys.stderr)
    else:
        print("  *** LIVE RUN — contacts WILL be deleted from CC ***", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Verify exports exist
    export_file = EXPORTS / f"cc_full_export_{TODAY}.json"
    if not export_file.exists():
        print(f"  ABORT: Phase 1 export not found: {export_file}", file=sys.stderr)
        sys.exit(1)
    print(f"  Phase 1 export verified: {export_file}", file=sys.stderr)

    # Load classifications
    with open(CLASS / "purge.json") as f:
        purge = json.load(f)
    with open(CLASS / "archive.json") as f:
        archive = json.load(f)
    with open(CLASS / "keep.json") as f:
        keep = json.load(f)

    print(f"  PURGE:   {len(purge):>6} contacts", file=sys.stderr)
    print(f"  ARCHIVE: {len(archive):>6} contacts", file=sys.stderr)
    print(f"  KEEP:    {len(keep):>6} contacts (untouched)", file=sys.stderr)

    # Build log
    LOGS.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = [
        f"# CC Cleanup Execution Log — {TODAY}",
        f"",
        f"Mode: {'DRY RUN' if dry_run else 'LIVE'}",
        f"Started: {datetime.now(timezone.utc).isoformat()}",
        f"",
        f"Pre-execution counts:",
        f"  PURGE:   {len(purge)}",
        f"  ARCHIVE: {len(archive)}",
        f"  KEEP:    {len(keep)}",
    ]

    # Execute PURGE first (unsubscribed, junk — lowest risk)
    purge_stats = process_bucket(purge, "PURGE", log_lines, dry_run)

    # Then ARCHIVE
    archive_stats = process_bucket(archive, "ARCHIVE", log_lines, dry_run)

    # Summary
    log_lines += [
        "",
        "=" * 60,
        "EXECUTION SUMMARY",
        "=" * 60,
        f"  PURGE:   {purge_stats['succeeded']}/{purge_stats['total']} deleted ({purge_stats['failed']} failed)",
        f"  ARCHIVE: {archive_stats['succeeded']}/{archive_stats['total']} deleted ({archive_stats['failed']} failed)",
        f"  KEEP:    {len(keep)} untouched",
        f"",
        f"Completed: {datetime.now(timezone.utc).isoformat()}",
    ]

    if _new_refresh:
        log_lines.append(f"\n!! New CC refresh token issued: {_new_refresh}")

    # Write log
    log_path = LOGS / f"cleanup_log_{TODAY}.md"
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\n  Log saved: {log_path}", file=sys.stderr)

    # Print summary
    print("\n" + "\n".join(log_lines[-10:]))


if __name__ == "__main__":
    main()
