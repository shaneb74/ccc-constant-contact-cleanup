"""
GoDaddy DNS Migration — recreate all Cloudflare DNS records in GoDaddy.

This script creates the full DNS record set in GoDaddy so that when
nameservers are flipped from Cloudflare to GoDaddy, everything works
identically.

DOES NOT change nameservers. That's a manual step in GoDaddy dashboard
after verifying the records are correct.

Rollback: Change nameservers back to alla.ns.cloudflare.com /
hugh.ns.cloudflare.com in GoDaddy dashboard. Cloudflare zone is untouched.

Usage:
  python3 godaddy_dns_migrate.py              # Dry run — show what would be created
  python3 godaddy_dns_migrate.py --execute    # Create records in GoDaddy
  python3 godaddy_dns_migrate.py --verify     # Check GoDaddy records match expected
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "production"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_secrets import load_local_env
load_local_env()

import os
API_KEY = os.environ["GODADDY_API_KEY"]
API_SECRET = os.environ["GODADDY_API_SECRET"]
DOMAIN = "conciergecareadvisors.com"

HEADERS = {
    "Authorization": f"sso-key {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# ── Complete DNS record set (captured 2026-04-13 via public DNS queries) ──
# These reproduce the exact records currently served by Cloudflare.

RECORDS = [
    # --- Website ---
    {"type": "A",     "name": "@",           "data": "149.56.169.178",  "ttl": 3600},
    {"type": "CNAME", "name": "www",         "data": "conciergecareadvisors.com",  "ttl": 3600},
    {"type": "CNAME", "name": "ftp",         "data": "conciergecareadvisors.com",  "ttl": 3600},

    # --- Dev subdomain (GCP) ---
    {"type": "A",     "name": "dev",         "data": "35.247.85.42",   "ttl": 3600},

    # --- Email: Proofpoint MX ---
    {"type": "MX",    "name": "@",           "data": "mx1-us1.ppe-hosted.com",  "ttl": 3600, "priority": 10},
    {"type": "MX",    "name": "@",           "data": "mx2-us1.ppe-hosted.com",  "ttl": 3600, "priority": 20},

    # --- Email: Legacy GoDaddy mail CNAMEs ---
    {"type": "CNAME", "name": "mail",        "data": "pop.secureserver.net",     "ttl": 3600},
    {"type": "CNAME", "name": "webmail",     "data": "webmail.secureserver.net", "ttl": 3600},
    {"type": "CNAME", "name": "smtp",        "data": "smtp.secureserver.net",    "ttl": 3600},
    {"type": "CNAME", "name": "pop",         "data": "pop.secureserver.net",     "ttl": 3600},
    {"type": "CNAME", "name": "imap",        "data": "imap.secureserver.net",    "ttl": 3600},

    # --- Microsoft 365 ---
    {"type": "CNAME", "name": "autodiscover","data": "autodiscover.outlook.com", "ttl": 3600},
    {"type": "CNAME", "name": "msoid",       "data": "clientconfig.microsoftonline-p.net", "ttl": 3600},
    {"type": "CNAME", "name": "lyncdiscover","data": "webdir.online.lync.com",   "ttl": 3600},
    {"type": "CNAME", "name": "sip",         "data": "sipdir.online.lync.com",   "ttl": 3600},

    # --- Microsoft 365 SRV records ---
    {"type": "SRV",   "name": "_sipfederationtls._tcp", "data": "sipfed.online.lync.com",  "ttl": 3600,
     "priority": 100, "weight": 1, "port": 5061, "service": "_sipfederationtls", "protocol": "_tcp"},
    {"type": "SRV",   "name": "_sip._tls",              "data": "sipdir.online.lync.com",  "ttl": 3600,
     "priority": 100, "weight": 1, "port": 443, "service": "_sip", "protocol": "_tls"},

    # --- TXT records (SPF, verification, DMARC) ---
    {"type": "TXT",   "name": "@",           "data": "v=spf1 a:dispatch-us.ppe-hosted.com include:secureserver.net include:_spf.activedemand.com ~all", "ttl": 3600},
    {"type": "TXT",   "name": "@",           "data": "MS=6799AE8659770CA3BC2A1F08A5C12DE6F0531912", "ttl": 3600},
    {"type": "TXT",   "name": "@",           "data": "NETORG8292524.onmicrosoft.com",              "ttl": 3600},
    {"type": "TXT",   "name": "@",           "data": "google-site-verification=HnajWZCyi0_rmdWul5owM9U3EfRxnWtzOj76aNInNf8", "ttl": 3600},
    {"type": "TXT",   "name": "@",           "data": "google-site-verification=uAfna94bzmquQixOWiEi0HRzxu4psKi5Tc0Ho_uzIys", "ttl": 3600},

    # --- DMARC ---
    {"type": "TXT",   "name": "_dmarc",      "data": "v=DMARC1; p=none; rua=mailto:dmarc@conciergecareadvisors.com", "ttl": 3600},
]


def godaddy_get(path: str) -> dict | list | None:
    r = requests.get(f"https://api.godaddy.com{path}", headers=HEADERS)
    if not r.ok:
        print(f"  [ERR] GET {path}: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return None
    return r.json()


def godaddy_patch(path: str, body: list) -> bool:
    """PATCH adds/updates records without replacing the entire zone."""
    r = requests.patch(f"https://api.godaddy.com{path}", headers=HEADERS, json=body)
    if not r.ok:
        print(f"  [ERR] PATCH {path}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return False
    return True


def godaddy_put(path: str, body: list) -> bool:
    """PUT replaces all records of a given type+name."""
    r = requests.put(f"https://api.godaddy.com{path}", headers=HEADERS, json=body)
    if not r.ok:
        print(f"  [ERR] PUT {path}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return False
    return True


def display_records():
    """Show the planned record set."""
    print(f"\nPlanned DNS records for {DOMAIN}:")
    print(f"{'Type':<6} {'Name':<30} {'Data':<60} {'TTL':>5}")
    print("-" * 105)
    for r in RECORDS:
        extra = ""
        if r["type"] == "MX":
            extra = f" (pri={r.get('priority', '')})"
        elif r["type"] == "SRV":
            extra = f" (pri={r.get('priority', '')} w={r.get('weight', '')} port={r.get('port', '')})"
        print(f"{r['type']:<6} {r['name']:<30} {r['data'][:58]:<60} {r['ttl']:>5}{extra}")
    print(f"\nTotal: {len(RECORDS)} records")


def execute_migration():
    """Create all records in GoDaddy using PATCH (additive)."""
    print(f"\nCreating {len(RECORDS)} DNS records in GoDaddy for {DOMAIN}...\n")

    # Group records by type+name for efficient API calls
    # GoDaddy API: PATCH /v1/domains/{domain}/records adds records
    # For multiple TXT records on @, we need to PUT them all at once
    from collections import defaultdict
    groups: dict[tuple, list] = defaultdict(list)
    for r in RECORDS:
        groups[(r["type"], r["name"])].append(r)

    success = 0
    failed = 0

    for (rtype, name), records in groups.items():
        payloads = []
        for r in records:
            payload = {"data": r["data"], "ttl": r["ttl"]}
            if rtype == "MX":
                payload["priority"] = r["priority"]
            elif rtype == "SRV":
                payload["priority"] = r["priority"]
                payload["weight"] = r["weight"]
                payload["port"] = r["port"]
                payload["service"] = r["service"]
                payload["protocol"] = r["protocol"]
            payloads.append(payload)

        # PUT replaces all records for this type+name (needed for multiple TXT on @)
        path = f"/v1/domains/{DOMAIN}/records/{rtype}/{name}"
        print(f"  PUT {rtype:>5} {name:<30} ({len(payloads)} record(s))", end="")
        time.sleep(0.5)
        ok = godaddy_put(path, payloads)
        if ok:
            print(" OK")
            success += len(payloads)
        else:
            print(" FAILED")
            failed += len(payloads)

    print(f"\nDone: {success} created, {failed} failed")
    return failed == 0


def verify_records():
    """Verify GoDaddy records match expected."""
    print(f"\nVerifying GoDaddy DNS records for {DOMAIN}...\n")
    existing = godaddy_get(f"/v1/domains/{DOMAIN}/records")
    if existing is None:
        print("  Could not fetch GoDaddy records")
        return

    # Build lookup
    gd_lookup: dict[tuple, list] = {}
    for r in existing:
        key = (r["type"], r["name"])
        if key not in gd_lookup:
            gd_lookup[key] = []
        gd_lookup[key].append(r)

    ok_count = 0
    missing_count = 0

    for r in RECORDS:
        key = (r["type"], r["name"])
        gd_records = gd_lookup.get(key, [])
        found = False
        for gd in gd_records:
            if r["type"] == "MX":
                if gd["data"].rstrip(".") == r["data"].rstrip(".") and gd.get("priority") == r.get("priority"):
                    found = True
                    break
            elif r["type"] == "SRV":
                if gd["data"].rstrip(".") == r["data"].rstrip(".") and gd.get("port") == r.get("port"):
                    found = True
                    break
            else:
                if gd["data"].rstrip(".") == r["data"].rstrip("."):
                    found = True
                    break
        status = "OK" if found else "MISSING"
        if found:
            ok_count += 1
        else:
            missing_count += 1
        print(f"  [{status:>7}] {r['type']:>5} {r['name']:<30} {r['data'][:50]}")

    print(f"\n  {ok_count} OK, {missing_count} missing")
    if missing_count == 0:
        print("\n  All records verified. Safe to flip nameservers.")
        print(f"\n  Next step: Go to GoDaddy dashboard → {DOMAIN} → DNS → Nameservers")
        print(f"  Change from Cloudflare to GoDaddy default nameservers.")
    else:
        print(f"\n  {missing_count} records missing — investigate before flipping nameservers.")


def main():
    parser = argparse.ArgumentParser(description="GoDaddy DNS migration")
    parser.add_argument("--execute", action="store_true", help="Create records in GoDaddy")
    parser.add_argument("--verify", action="store_true", help="Verify records match expected")
    args = parser.parse_args()

    print("=" * 70)
    print("GODADDY DNS MIGRATION")
    print(f"Domain: {DOMAIN}")
    print(f"Source: Cloudflare (alla.ns.cloudflare.com)")
    print(f"Target: GoDaddy (API-managed)")
    print("=" * 70)

    if args.verify:
        verify_records()
    elif args.execute:
        display_records()
        print("\n  EXECUTING — creating records in GoDaddy...")
        ok = execute_migration()
        if ok:
            print("\n  Migration complete. Now run --verify to confirm.")
    else:
        display_records()
        print("\n  DRY RUN — no changes made. Use --execute to create records.")
        print("  Use --verify after execution to confirm records match.")

    print(f"\n  Rollback: Change nameservers back to alla.ns.cloudflare.com / hugh.ns.cloudflare.com")


if __name__ == "__main__":
    main()
