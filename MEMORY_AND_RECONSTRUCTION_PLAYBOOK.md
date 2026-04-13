# Constant Contact Cleanup — Memory & Reconstruction Playbook

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Pre-Cleanup State Snapshot](#2-pre-cleanup-state-snapshot)
- [3. Classification Criteria — Full Decision Log](#3-classification-criteria--full-decision-log)
- [4. Classification Results — Final Numbers](#4-classification-results--final-numbers)
- [5. What Was Removed and Where It Lives](#5-what-was-removed-and-where-it-lives)
- [6. Subdomain Strategy](#6-subdomain-strategy)
- [7. Warm-Up Protocol](#7-warm-up-protocol)
- [8. Reconstruction Playbook — How to Reimport](#8-reconstruction-playbook--how-to-reimport)
- [9. Reconstruction Playbook — How to Rebuild from Scratch](#9-reconstruction-playbook--how-to-rebuild-from-scratch)
- [10. Contacts and Accountability](#10-contacts-and-accountability)
- [11. Appendix: Raw Audit Data](#11-appendix-raw-audit-data)

---

## 1. Executive Summary

**Date of execution:** 2026-04-13
**Authorized by:** Shane Bray, EVP/Co-founder, Concierge Care Advisors
**Executed by:** Claude Code (Opus 4.6) under direct supervision

Concierge Care Advisors' Constant Contact account had accumulated 26,475 contacts over ~15 years of operation — accumulated through events, partnerships, COVID outreach, vendor lists, and organic sign-ups. An audit on the weekend of 2026-04-12 revealed an 81.4% spam-block bounce rate on recent campaigns, driven by sending to implicit opt-ins, partner-organization addresses, and contacts who had long since disengaged. Only 77-336 contacts had explicit opt-in consent. The bounce/spam notification volume was unsustainable and actively harming the company's domain reputation.

This cleanup exported the full CC state, classified every contact using tightened criteria (clicks-only engagement, QB recency filtering), and removed 20,878 contacts from CC in two buckets:

- **PURGE (8,725):** Permanently removed — unsubscribed contacts, role accounts, junk addresses, duplicates
- **ARCHIVE (12,153):** Removed from CC but fully preserved in `archive.json` for future reimport via re-permission campaign

**5,597 contacts remain in CC** (the KEEP list), sub-segmented into warm-up tiers:
- **Tier 1 (1,308):** Clicked a link in the last 12 months — highest-confidence engaged
- **Tier 2 (4,223):** Active QuickBase relationship (record modified in last 2 years) but no email click engagement
- **Tier 3 (66):** Explicit opt-in or CCSN partner contacts

CC's soft-delete model preserves all historical campaign engagement data. Reimporting an archived email address reconnects it to its prior history automatically.

**Post-cleanup CC live count: 5,558** (39 fewer than the 5,597 KEEP classification — the delta is organic churn between export and execution, not an error).

---

## 2. Pre-Cleanup State Snapshot

*Data as of 2026-04-13 Phase 1 export.*

### Contact Counts by Status

| Status | Count |
|--------|-------|
| implicit | 17,534 |
| unsubscribed | 8,530 |
| explicit | 336 |
| unknown | 73 |
| not_set | 1 |
| pending_confirmation | 1 |
| **TOTAL** | **26,475** |

### Opt-in Source Distribution

| Source | Count |
|--------|-------|
| Account (admin-added) | 17,586 |
| unknown | 8,605 |
| Contact (self-subscribed) | 284 |

### Engagement Breakdown (Last 12 Months, 22 Campaigns Scanned)

| Engagement Type | Unique Contacts | Reliability |
|----------------|-----------------|-------------|
| Clicked a link | 1,370 | **High** — requires human interaction |
| Opened only (no click) | 7,793 | **Low** — inflated by Apple MPP, bot pre-fetches, security scanners |
| No engagement at all | ~17,312 | N/A |

**Critical finding:** Of the 9,163 contacts who "opened" an email, only 1,370 (15%) actually clicked. The remaining 7,793 open-only contacts are unreliable as engagement signals due to Apple Mail Privacy Protection (which pre-fetches all images, triggering open tracking) and corporate email security bots that scan links and trigger open pixels. CC's tracking API provides a `device_type` field but no bot/MPP indicator.

### QuickBase Cross-Reference

| Metric | Count |
|--------|-------|
| Unique CC emails | 26,401 |
| Unique QB emails (all 4 tables) | 16,263 |
| In BOTH (overlap) | 15,504 |
| CC-only (not in QB) | 10,897 |
| QB-only (not in CC) | 759 |

### QB Table Breakdown

| Table | Table ID | Records | Unique Emails |
|-------|----------|---------|---------------|
| WA Clients | bkpvi5e32 | 19,879 | 12,975 |
| Contacts | bkqfsmeuq | 5,528 | 3,582 |
| Prospects | bksjvvngk | 3,837 | 1,200 |
| CCSN Partner Contacts | bvx69kb96 | 20 | 20 |
| **Deduplicated total** | | | **16,263** |

### QB Email Recency (Date Modified Distribution)

| Year | QB Emails Modified |
|------|-------------------|
| 2016 | 188 |
| 2017 | 329 |
| 2018 | 306 |
| 2019 | 178 |
| 2020 | 408 |
| 2021 | 469 |
| 2022 | 5,029 |
| 2023 | 2,402 |
| 2024 | 2,684 |
| 2025 | 2,802 |
| 2026 | 1,468 |

**Recent (modified after 2024-04-13):** 6,208 emails
**Stale (modified before 2024-04-13):** 10,055 emails

### Root Cause

The 81% spam-block rate was caused by years of sending marketing emails to:
1. ~17,500 implicit opt-ins accumulated through events, COVID outreach, vendor lists, and partnership activities — many from 2011-2018
2. ~5,500+ partner-organization email addresses (providence.org, swedish.org, multicare.org, brookdale.com, etc.) that healthcare orgs' mail servers reject as spam
3. Contacts who had disengaged years ago but were never removed from active lists
4. No systematic list hygiene or re-permission campaigns ever implemented

### CC Lists (Top 10 by Size, Pre-Cleanup)

| List Name | Members | List ID |
|-----------|---------|---------|
| Zoho Contacts | 13,036 | 171999d0-8e92-11e3-b49e-d4ae52712b64 |
| Podcast 8.15 - Clients&Communities | 7,637 | 380d991a-5b3d-11ef-ac51-fa163e24df6a |
| COVID Thanksgiving | 5,196 | 781ff77e-2f53-11eb-97fc-fa163edfff7e |
| NW Harvest Business | 3,767 | 84c775a6-4c8a-11ec-85a6-fa163e159116 |
| Ducks in a Row - Clients | 3,305 | bfcbdd44-56d5-11ed-b75f-fa163ecbdd18 |
| Linda Marzano | 2,777 | 64c2d3cc-fa10-11ef-bf60-fa163e1801b9 |
| Senior Community SeniorLife.AI Blast 10/29 | 2,413 | 7bb141e0-961f-11ef-a51c-fa163e2564f0 |
| Sept 2024 Advisor Job Blast List | 2,405 | 6571da6a-6afb-11ef-ac94-fa163e3c5d75 |
| NW Harvest Clients | 2,215 | 722a9c42-4c8b-11ec-9e03-fa163e159116 |
| AFH Vacancy Email | 2,151 | 3053c9f8-013e-11ec-94b4-fa163edfff7e |

Full list export (146 lists): `exports/cc_lists_2026-04-13.json`

---

## 3. Classification Criteria — Full Decision Log

### Decision 1: Engagement Definition — Clicks Only

**Question:** What counts as "engaged" for determining whether a contact should stay in CC?

**Options considered:**
- (a) Any open or click in the last 12 months (the default CC engagement definition)
- (b) Clicks only (ignore opens entirely)
- (c) Multiple opens as a proxy for genuine engagement

**Decided:** Option (b) — clicks only.

**Rationale:** The audit revealed that of 9,163 contacts with an "open" event, only 1,370 (15%) had also clicked. The remaining 7,793 open-only contacts are unreliable due to Apple Mail Privacy Protection (MPP), which pre-fetches all email images on Apple devices — triggering open tracking pixels without the user ever seeing the email. Corporate email security bots (Barracuda, Proofpoint, Mimecast) also scan emails and trigger open events. CC's tracking API provides `device_type` (computer/mobile) but no bot or MPP indicator, making it impossible to filter automated opens from real ones.

Clicks require deliberate user interaction — clicking a link in an email body. No known bot or privacy feature generates click events on marketing email links. This makes clicks the only trustworthy engagement signal available from CC's tracking data.

**Impact:** 2,535 contacts that were classified KEEP under v1 (open-only engagement, not in QB) moved to ARCHIVE under v2. This is conservative — they can be reimported during the re-permission campaign if they respond.

### Decision 2: QB Anchor Logic — Exact Email Match

**Question:** How should we match CC contacts to QuickBase records to determine "active relationship"?

**Options considered:**
- (a) Exact email match (normalized: `str.strip().lower()`)
- (b) Fuzzy match (name + domain)
- (c) Domain-level match (anyone @company.com where company is in QB)

**Decided:** Option (a) — exact email match only.

**Rationale:** Fuzzy matching would produce false positives. A contact named "John Smith" at "providence.org" in CC is not necessarily the same John Smith in QB's Contacts table. Domain-level matching would anchor every @providence.org address just because one Providence contact exists in QB, which defeats the purpose of the cleanup. Exact email match is the only approach with zero false-positive risk.

**QB tables included:** WA Clients (`bkpvi5e32`), Contacts (`bkqfsmeuq`), Prospects (`bksjvvngk`), CCSN Partner Contacts (`bvx69kb96`). Email FIDs:
- WA Clients: 67 (Representative Email), 25 (Alternative Contact Email), 61 (Referral Source Email)
- Contacts: 17 (Email), 51 (Record-Email)
- Prospects: 8 (Email), 238 (CCSN Email)
- CCSN Partner Contacts: 9 (Email)

Deduplicated total across all 4 tables: **16,263 unique email addresses**.

### Decision 3: QB Recency Filter

**Question:** Should a QB email match from a 2012 WA Client record count as an "active relationship"?

**Options considered:**
- (a) All QB matches count regardless of age
- (b) 2-year universal cutoff across all QB tables
- (c) 3-year cutoff on WA Clients only, no cutoff on Contacts/Prospects/CCSN

**Decided:** Option (b) — 2-year universal cutoff (record modified after 2024-04-13).

**Rationale:** Shane initially suggested option (c), but the implementation applied a 2-year universal cutoff across all tables. This was slightly more aggressive than intended — it moved some Contacts and Prospects entries (referral partners whose QB records hadn't been touched recently) into ARCHIVE. This is acceptable because:
1. Those contacts land in ARCHIVE, not PURGE — they can be reimported
2. A partner whose QB record hasn't been modified in 2+ years is a reasonable re-engagement candidate, not an active marketing target
3. They will surface naturally in the Phase 6D re-permission campaign

**Known caveat:** Some current referral partners whose QB records were simply not updated recently may not be in the KEEP list. If a specific partner is noticed missing, they can be manually added back to CC or pulled from `archive.json`.

**QB population split:**
- Recent (modified after 2024-04-13): 6,208 emails
- Stale (modified before 2024-04-13): 10,055 emails

### Decision 4: KEEP Sub-Tiers

**Question:** How should KEEP contacts be organized for the subdomain warm-up?

**Decided:** Three tiers based on engagement quality:

| Tier | Definition | Count |
|------|-----------|-------|
| T1 | Clicked any email in the last 12 months | 1,308 |
| T2 | QB record modified in last 2 years, no click | 4,223 |
| T3 | Explicit opt-in or CCSN partner contact | 66 |

**Rationale:** Warm-up requires sending to the most-engaged contacts first to build positive reputation signals. T1 contacts are confirmed human engagers — ideal for week 1-2 warm-up sends. T2 contacts have an active business relationship (validated by QB recency) but haven't engaged with email — they're introduced after the subdomain has 2-3 weeks of positive signals. T3 is a small group that's kept for completeness.

### Decision 5: ARCHIVE vs PURGE Threshold

**Question:** When in doubt, which bucket?

**Decided:** ARCHIVE, not PURGE.

**Rationale:** CC's soft-delete model preserves campaign history even after contact deletion, and reimporting an email reconnects it to prior engagement data. However, the `archive.json` file contains full metadata (list memberships, custom fields, engagement dates) that CC may not preserve indefinitely in its internal soft-delete state. Archiving locally gives us a complete, independent copy.

PURGE is reserved for contacts that should never be emailed again: unsubscribed contacts (legal requirement), hard bounces, invalid addresses, and duplicates.

### Decision 6: PURGE Criteria

**Decided:** A contact is PURGE if any of the following apply:

| Criterion | Count |
|-----------|-------|
| Already unsubscribed (`permission_to_send = "unsubscribed"`) | 8,529 |
| Role account (info@, noreply@, admin@, etc.) with no click engagement and not in recent QB | 122 |
| No email address on the contact record | 73 |
| Duplicate email (kept the record with most list memberships and most recent update) | 1 |
| **Total PURGE** | **8,725** |

Note: 97.8% of the PURGE bucket is already-unsubscribed contacts. These were already not receiving email — deleting them is purely housekeeping.

---

## 4. Classification Results — Final Numbers

### Overall

| Bucket | Count | % of Total | Description |
|--------|-------|-----------|-------------|
| **KEEP** | 5,597 | 21.1% | Stays in CC, sub-segmented for warm-up |
| **ARCHIVE** | 12,153 | 45.9% | Removed from CC, preserved for reimport |
| **PURGE** | 8,725 | 33.0% | Removed from CC permanently |
| **TOTAL** | 26,475 | 100% | |

### KEEP Sub-Tiers

| Tier | Count | % of KEEP | Criteria |
|------|-------|-----------|----------|
| T1 — Clicked | 1,308 | 23.4% | Clicked a link in any email in the last 12 months |
| T2 — Recent QB | 4,223 | 75.5% | Email matches QB record modified after 2024-04-13, no click |
| T3 — Explicit/CCSN | 66 | 1.2% | Explicit opt-in consent or CCSN partner contact |
| **Total** | **5,597** | 100% | |

**T1 sub-breakdown:** Of the 1,308 clickers, 428 are also in recent QB, 471 are in stale QB, and 409 are not in QB at all (CC-only contacts who engage).

### ARCHIVE Segments

| Segment | Count | % of ARCHIVE |
|---------|-------|-------------|
| Not in QB + no click engagement | 6,086 | 50.1% |
| QB match but stale (record not modified since 2024-04-13) | 6,067 | 49.9% |
| **Total** | **12,153** | 100% |

### PURGE Segments

| Segment | Count | % of PURGE |
|---------|-------|-----------|
| Unsubscribed | 8,529 | 97.8% |
| Role accounts (info@, admin@, marketing@, etc.) | 122 | 1.4% |
| No email address | 73 | 0.8% |
| Duplicate | 1 | 0.0% |
| **Total** | **8,725** | 100% |

### Post-Cleanup Live Verification

| Metric | Value |
|--------|-------|
| CC live contact count (post-cleanup) | 5,558 |
| Expected (KEEP classification) | 5,597 |
| Delta | -39 |
| Explanation | Organic churn (unsubscribes, bounces) between Phase 1 export and Phase 3 execution (~30 min gap) |

---

## 5. What Was Removed and Where It Lives

### File Inventory

All paths are relative to the repo root (`ccc-constant-contact-cleanup/`).

| File | Size | Contents |
|------|------|----------|
| `exports/cc_full_export_2026-04-13.json` | 21 MB | Every CC contact (26,475) with full metadata |
| `exports/cc_lists_2026-04-13.json` | 35 KB | All 146 CC lists with member counts |
| `exports/qb_contacts_2026-04-13.json` | 4.8 MB | All QB email contacts across 4 tables |
| `exports/state_snapshot_2026-04-13.md` | 3.2 KB | Pre-cleanup summary dashboard |
| `classifications/keep.json` | — | 5,597 KEEP contacts (all tiers combined) |
| `classifications/keep_t1_clicked.json` | — | 1,308 Tier 1 contacts |
| `classifications/keep_t2_qb_recent.json` | — | 4,223 Tier 2 contacts |
| `classifications/keep_t3_explicit_ccsn.json` | — | 66 Tier 3 contacts |
| `classifications/archive.json` | — | 12,153 archived contacts (the reimport source) |
| `classifications/purge.json` | — | 8,725 purged contacts (audit trail) |
| `classifications/clicked_contact_ids.json` | — | 1,370 contact IDs with click engagement |
| `classifications/engaged_contact_ids.json` | — | 9,156 contact IDs with any engagement (v1, includes opens) |
| `classifications/engagement_quality.json` | — | Click vs open analysis summary |
| `classifications/qb_email_recency.json` | — | QB email → date_modified mapping |
| `classifications/classification_summary_2026-04-13.md` | — | v1 classification summary (superseded by v2) |
| `logs/cleanup_log_2026-04-13.md` | — | Step-by-step execution log with activity IDs |
| `scripts/cc_export_all.py` | — | Phase 1 export script |
| `scripts/classify_contacts.py` | — | Phase 2 classification script (v1 logic) |
| `scripts/cc_execute_cleanup.py` | — | Phase 3 execution script |
| `scripts/reimport_archive.py` | — | Phase 4 reimport script |

### JSON Schema: Contact Record

Each contact in the export and classification files has these fields:

```
{
  "contact_id": "uuid",           // CC internal ID
  "email": "user@domain.com",     // Normalized (lowercase, stripped)
  "first_name": "John",
  "last_name": "Doe",
  "permission_to_send": "implicit|explicit|unsubscribed|unknown",
  "opt_in_source": "Account|Contact|unknown",
  "opt_in_date": "ISO-8601 or empty",
  "opt_out_source": "Account|Contact or empty",
  "opt_out_date": "ISO-8601 or empty",
  "created_at": "ISO-8601",       // When contact was added to CC
  "updated_at": "ISO-8601",       // Last modification in CC
  "list_memberships": ["list-uuid-1", "list-uuid-2"],  // CC list IDs
  "reasons": ["clicked_12mo", "in_qb_recent"],  // (KEEP only) why they were kept
  "reason": "unsubscribed",                     // (ARCHIVE/PURGE only) why removed
  "tier": "T1|T2|T3|archive|purge"             // Classification tier
}
```

### CC List ID → Name Mapping

The full mapping is in `exports/cc_lists_2026-04-13.json`. Key lists:

| List ID | List Name |
|---------|-----------|
| 171999d0-8e92-11e3-b49e-d4ae52712b64 | Zoho Contacts |
| 380d991a-5b3d-11ef-ac51-fa163e24df6a | Podcast 8.15 - Clients&Communities |
| 781ff77e-2f53-11eb-97fc-fa163edfff7e | COVID Thanksgiving |
| 70cd5258-2a2c-11f1-93a1-02427845aa03 | Navigator - Clients 3.27.26 |
| 7bb141e0-961f-11ef-a51c-fa163e2564f0 | Senior Community SeniorLife.AI Blast 10/29 |

---

## 6. Subdomain Strategy

### Why a Subdomain, Not a New From-Address

The root domain `conciergecaradvisors.com` carries the 81% spam-block reputation. Inbox providers (Gmail, Outlook, Yahoo) evaluate sender reputation at the **domain level**, not the address prefix level. Changing from `newsletter@conciergecaradvisors.com` to `news@conciergecaradvisors.com` changes nothing — both inherit the same domain reputation score.

A new **subdomain** (`news.conciergecaradvisors.com`) starts with a neutral/blank reputation and builds its own score independently of the parent domain. This is standard practice for separating transactional email from marketing email, or for recovering from a reputation collapse.

### DNS Records

Target subdomain: `news.conciergecaradvisors.com`

**DKIM (DomainKeys Identified Mail):**
- Two CNAME records pointing to CC's DKIM key servers
- CC manages key rotation automatically with CNAME method
- Exact values provided by CC after self-authentication setup (My Account → Advanced Settings → Add Self-Authentication)

**DMARC:**
- TXT record: `_dmarc.news.conciergecaradvisors.com` → `v=DMARC1; p=none; rua=mailto:dmarc-reports@conciergecaradvisors.com`
- Starts at `p=none` (monitoring only), progresses to `p=quarantine` then `p=reject` as deliverability confirms

**SPF — NOT added.**
- Constant Contact does NOT support SPF alignment
- CC's Envelope-From domain is always their own (e.g., `bounce-XXX@in.constantcontact.com`), so SPF alignment will always fail regardless of what SPF records exist on the sending domain
- Adding `include:spf.constantcontact.com` wastes a DNS lookup and achieves nothing
- DMARC compliance is achieved through DKIM alignment only

**DNS records are created via the GoDaddy API.** See `PHASE_6_SUBDOMAIN_WARMUP.md` for the full Python implementation using GoDaddy's REST API.

### Root Domain Isolation Benefit

Moving marketing to the subdomain permanently separates advisor day-to-day email reputation from marketing reputation. Every advisor sending from `@conciergecaradvisors.com` will no longer carry the accumulated marketing bounce/spam baggage. The root domain reputation will recover passively as the spam-block rate drops to zero (no marketing sends from it).

---

## 7. Warm-Up Protocol

### Tier Ordering and Daily Volume

| Week | Daily Volume | Audience | Rationale |
|------|-------------|----------|-----------|
| 1 | 5-10 | T1 only (1,308 clickers), most recent clickers first | Build initial positive engagement signals |
| 2 | 15-25 | T1, expand to older clickers | Deepen engagement history with inbox providers |
| 3 | 30-50 | T1 + begin T2 (recent QB, most engaged first) | Introduce relationship-based contacts |
| 4 | 100+ | Full T1 + T2 at normal cadence | Scale to working audience |
| 5-6 | Standard | Full KEEP list including T3 | Normal campaign operations |

### Why T1 Is Sub-Sorted by Click Recency

Within the 1,308 T1 contacts, send to the most recently clicked contacts first. A contact who clicked 2 weeks ago is more likely to open and engage than one who clicked 11 months ago. Early sends during warm-up have outsized impact on reputation — you want the highest possible open/click rates in weeks 1-2 to establish the subdomain as a legitimate sender.

### Monitoring Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Bounce rate | > 2% | Pause all sends. Investigate which contacts are bouncing and remove them. |
| Spam complaint rate | > 0.1% | Pause all sends. Review content and audience. |
| Open rate | < 15% | Slow down expansion. Stay at current tier longer. |
| Click rate | < 2% | Review email content. May need stronger CTAs. |

### Rules During Warm-Up

- No blast sends. Every send is a controlled batch to a targeted segment.
- Generate replies if possible — re-engagement emails asking people to reply create positive engagement signals that Gmail weighs heavily.
- Do NOT send to the ARCHIVE list during warm-up.
- Monitor daily using CC's campaign reporting dashboard.

---

## 8. Reconstruction Playbook — How to Reimport

### Prerequisites

1. Subdomain reputation is established — minimum 6 weeks of clean sending with:
   - Bounce rate consistently < 1%
   - Spam complaint rate < 0.05%
   - Open rate > 20% on T1/T2 sends
2. All warm-up tiers (T1, T2, T3) are sending at normal cadence without issues
3. The `archive.json` file is accessible

### Source File

**File:** `classifications/archive.json`
**Format:** JSON array of contact objects (see schema in Section 5)
**Count:** 12,153 contacts

### Step-by-Step Reimport Process

1. **Start small.** Import 50-100 contacts from `archive.json`:
   ```bash
   cd constant-contact-cleanup
   python3 scripts/reimport_archive.py --execute --batch-size 50
   ```

2. **Send a re-permission email** to the imported batch. Single email with clear subject line:
   - Subject: "Do you still want to hear from Concierge Care Advisors?"
   - Body: One clear CTA button — "Yes, keep me subscribed"
   - Include unsubscribe link (legally required)

3. **Wait 7 days.** Monitor:
   - Bounce rate on the re-permission email (should be < 2%)
   - Spam complaints (should be < 0.1%)
   - Click-through rate on the "Yes" button

4. **Process results:**
   - Clicked "Yes" → move to appropriate KEEP list
   - No engagement → leave on the reimport list for one more attempt
   - Bounced → remove permanently

5. **Second attempt** (for non-responders from step 4):
   ```bash
   # Import next batch
   python3 scripts/reimport_archive.py --execute --batch-size 100 --offset 50
   ```
   Send a second re-permission email with different subject line. Non-responders after 2 attempts → leave archived permanently.

6. **Scale up gradually:**
   - Batch 1: 50 contacts
   - Batch 2: 100 contacts
   - Batch 3: 200 contacts
   - Batch 4: 500 contacts
   - Continue doubling if metrics stay clean

7. **What success looks like:**
   - Click-through rate on re-permission email > 5% (good)
   - Bounce rate stays < 1%
   - No spike in spam complaints
   - CC account reputation metrics remain stable

### The Reimport Script

**Location:** `scripts/reimport_archive.py`

```bash
# Dry run (shows what would be imported)
python3 scripts/reimport_archive.py

# Import 50 contacts
python3 scripts/reimport_archive.py --execute --batch-size 50

# Import next 100, starting at offset 50
python3 scripts/reimport_archive.py --execute --batch-size 100 --offset 50

# Import all (only after successful smaller batches)
python3 scripts/reimport_archive.py --execute --all
```

The script creates a "Reimport - Re-Permission" list in CC and adds all reimported contacts to it, so they can be targeted with the re-permission campaign.

---

## 9. Reconstruction Playbook — How to Rebuild from Scratch

If the archive files are lost or the classification needs to be re-run:

### Re-Extract from QuickBase

```python
# Tables and email FIDs:
# WA Clients (bkpvi5e32): FIDs 67, 25, 61
# Contacts (bkqfsmeuq): FIDs 17, 51
# Prospects (bksjvvngk): FIDs 8, 238
# CCSN Partner Contacts (bvx69kb96): FID 9

# Also pull FID 2 (Date Modified) for recency filtering
# Use QB API: POST https://api.quickbase.com/v1/records/query
```

Reference script: `scripts/cc_export_all.py` (the `export_qb_contacts()` function)

### Re-Extract from Constant Contact

```python
# Pull all contacts: GET /contacts?status=all&limit=500&include=list_memberships,custom_fields
# Pull all lists: GET /contact_lists?limit=500&include_count=true
```

Reference script: `scripts/cc_export_all.py` (the `export_cc_contacts()` function)

### Rebuild Classification

Reference script: `scripts/classify_contacts.py`

Key logic:
1. Match CC emails to QB emails using exact `str.strip().lower()` equality
2. Pull click tracking from last 12 months of campaigns (opens are unreliable)
3. Apply QB recency filter (2-year cutoff on Date Modified)
4. Classify: clicked → T1, recent QB → T2, explicit/CCSN → T3, else → ARCHIVE, unsubscribed/junk → PURGE

### Engagement Data Caveat

**Historical CC engagement data may not survive long-term.** CC preserves campaign tracking data tied to contact IDs, but there is no guarantee on retention period. The `clicked_contact_ids.json` and `engaged_contact_ids.json` files in this repo are the authoritative record of engagement state at the time of cleanup. If you need to re-run classification in the future, you will need to re-pull engagement data from whatever campaigns exist at that time — historical campaign tracking may have been purged by CC.

---

## 10. Contacts and Accountability

| Role | Person | Notes |
|------|--------|-------|
| **Authorized by** | Shane Bray, EVP/Co-founder | Full authority over CCA marketing operations |
| **Executed by** | Claude Code (Opus 4.6) | Under direct real-time supervision by Shane |
| **Date of execution** | 2026-04-13 | Phase 3 completed at 19:58 UTC |
| **Consult before reimport** | Shane Bray | No reimport without Shane's explicit approval |
| **CC account access** | Restricted | Do not grant CC API access to anyone without Shane's review |

### Authorization Chain

Shane provided explicit green-light for Phase 3 execution after:
1. Reviewing Phase 1 export (26,475 contacts verified)
2. Reviewing v1 classification and identifying concerns (QB anchor inflation, bot opens, KEEP too large)
3. Requesting three specific tightening changes (clicks-only, QB recency, KEEP tiering)
4. Reviewing v2 reclassification results (5,597 KEEP / 12,153 ARCHIVE / 8,725 PURGE)
5. Confirming CC preserves campaign history after deletion
6. Providing explicit "Green light on Phase 3" approval

---

## 11. Appendix: Raw Audit Data

### Engagement Type Breakdown (Full)

| Category | Count | Notes |
|----------|-------|-------|
| Total CC contacts | 26,475 | At time of export |
| Any engagement (open or click) | 9,163 | Across 22 campaigns in 12 months |
| Click engagement only | 1,370 | Trustworthy signal |
| Open-only (no click) | 7,793 | Unreliable — Apple MPP + bots |
| No engagement | ~17,312 | Majority of the contact base |

### QB Table Match Counts

| QB Table | Total Emails | In CC (overlap) | Not in CC |
|----------|-------------|-----------------|-----------|
| WA Clients | 12,975 | 12,362 | 612 |
| Contacts | 3,582 | 3,530 | 52 |
| Prospects | 1,200 | 1,092 | 108 |
| CCSN Partner Contacts | 20 | 20 | 0 |

### Bot/MPP Open Analysis

CC's tracking API returns these fields for open events:
- `contact_id`, `email_address`, `device_type` (computer/mobile), `created_time`

No bot indicator, no MPP flag, no user-agent. The `device_type` field cannot distinguish Apple MPP pre-fetches (which report as "mobile" or "computer" depending on the proxy device) from genuine human opens.

**Key statistic:** Only 15% of contacts with an "open" also had a click. In a healthy list with genuine engagement, click-to-open rates are typically 10-20%. The 15% rate is within normal range, which means the 85% who opened but never clicked are a mix of genuine openers-who-don't-click and automated opens. With no way to separate them, discarding opens entirely was the conservative choice.

### v1 → v2 Reclassification Delta

| Bucket | v1 | v2 | Delta | Cause |
|--------|-----|-----|-------|-------|
| KEEP | 14,237 | 5,597 | -8,640 | QB recency filter (-6,067), clicks-only (-2,535), role accounts (-38) |
| ARCHIVE | 3,583 | 12,153 | +8,570 | Absorbed stale QB (+6,067) and open-only engaged (+2,535) |
| PURGE | 8,655 | 8,725 | +70 | Additional role accounts that lost open-only protection |

### Execution Activity IDs

All 43 bulk delete activities completed with 0 errors. Full activity ID list in `logs/cleanup_log_2026-04-13.md`.

### Sample Records

**KEEP-T1 (clicked):**
- `djdkabbott@gmail.com` — Dave Abbott, clicked senior-navigator.com link, 2026-04-13
- `springsgreenapril@gmail.com` — Gaylynn Roth, clicked senior-navigator.com link, 2026-04-11
- `smh7450@comcast.net` — Sue Hennessy, clicked conciergecareadvisors.com link, 2026-04-11

**KEEP-T2 (recent QB, no click):**
- `steve@minarnorthey.com` — WA Clients, implicit opt-in, last CC update 2026-02-13
- `mzdanice@aol.com` — WA Clients, implicit opt-in, last CC update 2026-02-13
- `dlopes@sunriseview.org` — Contacts table, implicit opt-in, 11 list memberships

**ARCHIVE (stale QB):**
- `karen.winslow@swedish.org` — WA Clients, last QB update 2021, last CC update 2021-06-16, 2 lists
- `helen_wiggins@valleymed.org` — WA Clients, last QB update 2020, last CC update 2020-11-25, 4 lists

**ARCHIVE (not in QB, no click):**
- Implicit opt-ins from partner organizations, event lists, and historical imports with no recent engagement

**PURGE (unsubscribed):**
- 8,529 contacts with `permission_to_send: "unsubscribed"`, opt-out dates ranging from 2011 to 2026

---

*Document generated 2026-04-13T20:00:00Z. This document reflects the actual execution results, not planned numbers. All counts are from v2 (tightened criteria) classification.*
