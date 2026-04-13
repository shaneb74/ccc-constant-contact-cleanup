# Session Log — 2026-04-13

## What Happened Today

Shane authorized and supervised a full Constant Contact account cleanup, DNS migration, and email authentication setup. Everything was executed by Claude Code under direct real-time supervision with explicit approval at each destructive step.

---

## 1. CC List Cleanup (Phases 1-5)

### Problem
CCA's Constant Contact account had 26,475 contacts accumulated over ~15 years. An 81.4% spam-block bounce rate on recent campaigns. Only 336 contacts had explicit opt-in consent. The rest were implicit opt-ins from events, partnerships, COVID outreach, vendor lists, and historical imports. 8,530 were already unsubscribed but still in the system. Zero DKIM authentication was configured. CC never flagged any of this.

### Phase 1: Full Export
Exported the complete CC state before touching anything:
- 26,475 CC contacts with full metadata (list memberships, opt-in type, engagement history) → `exports/cc_full_export_2026-04-13.json` (21 MB)
- 146 CC lists with member counts → `exports/cc_lists_2026-04-13.json`
- 16,263 unique QB emails across 4 tables (WA Clients, Contacts, Prospects, CCSN Partner Contacts) → `exports/qb_contacts_2026-04-13.json`
- State snapshot → `exports/state_snapshot_2026-04-13.md`

### Phase 2: Classification (v1 → v2)

**v1 classification** used opens + clicks as engagement and all QB matches as anchors. This produced:
- KEEP: 14,237 / ARCHIVE: 3,583 / PURGE: 8,655

**Shane identified three problems with v1:**
1. 11,235 contacts anchored by QB was too high — the weekend audit found ~5,527 QB contacts. The discrepancy: the classifier pulled from all 4 QB tables (16,263 unique emails), not just Contacts.
2. 14,237 KEEP was too large for a warm-up. Needed sub-segmentation.
3. Open-only engagement is unreliable — Apple Mail Privacy Protection and bot pre-fetches inflate open tracking.

**Audit findings that drove v2:**
- Of 9,163 contacts with an "open," only 1,370 (15%) also clicked. The other 7,793 were open-only — likely inflated by MPP/bots.
- CC's tracking API provides `device_type` (computer/mobile) but no bot or MPP indicator. Opens are untrustworthy.
- 10,055 of 16,263 QB emails hadn't been modified in 2+ years.

**v2 classification applied three tightening changes:**
1. **Engagement = clicks only** (opens discarded as unreliable)
2. **QB recency filter:** QB anchor only counts if record modified after 2024-04-13 (2-year cutoff)
3. **KEEP sub-segmented into warm-up tiers**

**v2 results (final):**

| Bucket | Count | % |
|--------|-------|---|
| KEEP-T1 (clicked in 12mo) | 1,308 | 4.9% |
| KEEP-T2 (recent QB, no click) | 4,223 | 16.0% |
| KEEP-T3 (explicit/CCSN) | 66 | 0.2% |
| **KEEP total** | **5,597** | **21.1%** |
| ARCHIVE | 12,153 | 45.9% |
| PURGE | 8,725 | 33.0% |
| **TOTAL** | **26,475** | **100%** |

**Note on QB recency cutoff:** Shane originally suggested a 3-year cutoff on WA Clients only, keeping Contacts/Prospects/CCSN regardless of age. The implementation applied a 2-year universal cutoff across all tables — slightly more aggressive. This moved some Contacts and Prospects entries (referral partners) into ARCHIVE whose QB records hadn't been touched recently. Not a problem since they're in ARCHIVE (not PURGE) and will surface in the re-permission campaign. Documented in the playbook.

### Phase 3: Execution
- Confirmed with Shane that CC preserves campaign history after contact deletion (soft delete model — engagement data tied to email address, reconnected on reimport)
- Shane gave explicit green light
- 43 bulk delete API calls (500 contacts per batch)
- PURGE: 8,725/8,725 deleted (0 errors, 18 batches)
- ARCHIVE: 12,153/12,153 deleted (0 errors, 25 batches)
- All activity IDs logged in `logs/cleanup_log_2026-04-13.md`

### Phase 5: Verification
- Post-cleanup CC live count: 5,558
- Expected: 5,597 (KEEP classification count)
- Delta: -39 (organic churn between export and execution, not an error)
- Zero cross-bucket overlap in classification IDs (verified programmatically)

---

## 2. DNS Migration (Cloudflare → GoDaddy)

### Problem
DNS for `conciergecareadvisors.com` was managed in Cloudflare under the web vendor's (Citizen) account. Shane had no access to Cloudflare and couldn't create DNS records for email authentication.

### Discovery
- Domain registered at GoDaddy, nameservers pointed to Cloudflare (`alla.ns.cloudflare.com` / `hugh.ns.cloudflare.com`)
- Cloudflare was DNS-only mode (no proxy) — Let's Encrypt SSL cert, direct IP, no `cf-ray` headers
- The vendor had no technical reason to own DNS other than convenience for managing the WordPress site

### DNS Record Inventory (captured via public queries)
23 records total:
- **Website:** A record → 149.56.169.178 (OVH, vendor WordPress), www/ftp CNAMEs
- **Dev:** A record → 35.247.85.42 (GCP)
- **Email:** 2 MX records → Proofpoint (`mx1/mx2-us1.ppe-hosted.com`)
- **Legacy mail:** 5 CNAMEs (mail, webmail, smtp, pop, imap → secureserver.net)
- **M365:** autodiscover, msoid, lyncdiscover, sip CNAMEs + 2 SRV records (Teams/Lync)
- **TXT:** SPF, 2x Google verification, M365 verification, NETORG identifier
- **DMARC:** `v=DMARC1; p=none`

### Execution
1. Stored GoDaddy API keys in `.env.local` and AWS Secrets Manager (`cca/godaddy-api`)
2. Built `scripts/godaddy_dns_migrate.py` — recreates all records via GoDaddy API
3. Activated GoDaddy DNS zone (required setting nameservers to GoDaddy defaults, which triggered zone creation)
4. GoDaddy assigned `ns49.domaincontrol.com` / `ns50.domaincontrol.com`
5. Created all 23 records via API — all verified
6. Confirmed resolution through GoDaddy NS: website, MX, SPF, DMARC, M365 autodiscover all correct
7. Shane confirmed email delivery working (sent from Proton to company address, received successfully)

### Rollback
Change nameservers back to `alla.ns.cloudflare.com` / `hugh.ns.cloudflare.com` in GoDaddy dashboard. Cloudflare zone is untouched and would resume serving immediately.

---

## 3. DKIM Authentication

### Problem
Zero DKIM authentication was configured for `conciergecareadvisors.com`. Every email CC sent had no DKIM signature, which is a major spam signal for inbox providers. This was a significant contributor to the 81% spam-block rate alongside the dirty list.

### Execution
1. CC's self-authentication page showed two required CNAME records:
   - `ctct1._domainkey` → `100._domainkey.dkim1.ccsend.com`
   - `ctct2._domainkey` → `200._domainkey.dkim2.ccsend.com`
2. Created both CNAMEs in GoDaddy via API
3. CC detected the records (showed "Found" for both CNAMEs and DMARC)
4. Activated self-authentication in CC
5. Sent test email from `news@conciergecareadvisors.com` to `shanetbray@proton.me`
6. **Confirmed: `dkim=pass`, `dmarc=pass`**

### Subdomain Isolation — Not Available in CC
Shane's original plan was to authenticate `news.conciergecareadvisors.com` as a separate sending subdomain to isolate marketing reputation from advisor email. CC does not support this:
- Only one domain can be self-authenticated per account (platform limitation, not plan-tier)
- The self-authentication UI only offers the root domain in the dropdown — no option to enter a subdomain
- The "customize subdomain" feature in CC's knowledge base is cosmetic — it changes the rewritten From address on CC's `ccsend.com` domain, not your own domain
- CC support ticket opened requesting multi-domain DKIM — "a team member will reach out"

**Current state:** Marketing sends from `news@conciergecareadvisors.com` (root domain, new address). DKIM passes via root domain authentication. True subdomain isolation deferred pending CC support response or platform migration.

---

## 4. Shared Mailbox Setup

Created `news@conciergecareadvisors.com` as an M365 shared mailbox:
- No license required
- Persists independent of any user account
- Shane has FullAccess with AutoMapping
- Used to receive CC sender verification email
- Forwarding rule set up to route to `shaneb@` for verification

**GoDaddy had hijacked the M365 admin center** — navigating to admin.microsoft.com landed on GoDaddy's delegated admin portal instead. All M365 admin work was done via Exchange Online PowerShell (`pwsh` + `ExchangeOnlineManagement` module).

---

## 5. CC Platform Frustrations — Documented for Context

Shane's assessment of Constant Contact:
- **No proactive monitoring:** 81% spam-block rate for years with no alert or notification from CC
- **No list hygiene guidance:** 8,529 unsubscribed contacts sitting in the system, never flagged
- **No authentication prompting:** Zero DKIM configured, never suggested during the years CC was being paid
- **Single-domain DKIM limitation:** Cannot authenticate subdomains, preventing marketing/advisor email isolation
- **Likely replacement candidate:** Shane has Amazon SES already configured for Senior Navigator emails. SES supports subdomain DKIM natively. CC will likely be replaced once the immediate marketing needs are met and the team can be transitioned.

---

## 6. Files in This Repo

| Path | Description |
|------|-------------|
| `exports/cc_full_export_2026-04-13.json` | All 26,475 CC contacts with full metadata |
| `exports/cc_lists_2026-04-13.json` | All 146 CC lists |
| `exports/qb_contacts_2026-04-13.json` | QB email contacts (4 tables) |
| `exports/state_snapshot_2026-04-13.md` | Pre-cleanup summary |
| `classifications/keep.json` | 5,597 KEEP contacts (all tiers) |
| `classifications/keep_t1_clicked.json` | 1,308 T1 (clicked) |
| `classifications/keep_t2_qb_recent.json` | 4,223 T2 (recent QB) |
| `classifications/keep_t3_explicit_ccsn.json` | 66 T3 (explicit/CCSN) |
| `classifications/archive.json` | 12,153 archived (reimport source) |
| `classifications/purge.json` | 8,725 purged (audit trail) |
| `classifications/clicked_contact_ids.json` | 1,370 click-engaged IDs |
| `classifications/engaged_contact_ids.json` | 9,156 any-engaged IDs (v1) |
| `classifications/engagement_quality.json` | Click vs open analysis |
| `classifications/qb_email_recency.json` | QB email date-modified map |
| `logs/cleanup_log_2026-04-13.md` | Full execution log with activity IDs |
| `scripts/cc_export_all.py` | Phase 1 export script |
| `scripts/classify_contacts.py` | Phase 2 classification (v1 logic) |
| `scripts/cc_execute_cleanup.py` | Phase 3 deletion script |
| `scripts/reimport_archive.py` | Phase 4 reimport script |
| `scripts/godaddy_dns_migrate.py` | DNS migration script |
| `MEMORY_AND_RECONSTRUCTION_PLAYBOOK.md` | Full decision log and reconstruction guide |
| `PHASE_6_SUBDOMAIN_WARMUP.md` | Subdomain strategy and warm-up protocol |
| `SESSION_LOG_2026-04-13.md` | This file |

---

## 7. What's Next

| Item | Status | Notes |
|------|--------|-------|
| Start T1 warm-up sends | Ready | 1,308 confirmed clickers, send from `news@conciergecareadvisors.com` |
| CC support callback re: subdomain DKIM | Waiting | If they enable it, 30-second DNS update via GoDaddy API |
| Evaluate CC replacement (SES) | Future | Shane already has SES for SN; supports subdomain DKIM natively |
| Website flip (WordPress → Astro on AWS) | Future | DNS now under Shane's control — one A record change via GoDaddy API when ready |
| Remove Cloudflare vendor dependency | Done | NS now on GoDaddy; Cloudflare zone still exists as passive fallback |
| Re-permission campaign for ARCHIVE | After warm-up | 12,153 contacts, gradual batches, use `scripts/reimport_archive.py` |

---

*Session duration: ~4 hours. All destructive actions were explicitly authorized by Shane before execution.*
