# CC Contact Classification Summary (2026-04-13)

## Overview

| Bucket | Count | % |
|--------|-------|---|
| **KEEP** | 14,237 | 53.8% |
| **ARCHIVE** | 3,583 | 13.5% |
| **PURGE** | 8,655 | 32.7% |
| **TOTAL** | 26,475 | 100% |

Engagement scan: 9,156 unique contacts opened/clicked across 20 campaigns (last 12 months).

## KEEP Reasons (contacts may have multiple)

| Reason | Count |
|--------|-------|
| in_quickbase | 11,235 |
| engaged_12mo | 8,153 |
| explicit_opt_in | 335 |
| ccsn_partner_contact | 12 |

## PURGE Reasons

| Reason | Count |
|--------|-------|
| unsubscribed | 8,529 |
| no_email_address | 73 |
| role_account (info@) | 21 |
| role_account (admin@) | 16 |
| role_account (marketing@) | 10 |
| role_account (office@) | 3 |
| role_account (team@) | 1 |
| duplicate_of_e5ebad00-1401-11e7-8c98-d4ae52710c75 | 1 |
| role_account (webmaster@) | 1 |

## Classification Criteria

### KEEP (stays in CC)
- Has explicit opt-in consent
- Exists in QuickBase as an active relationship
- Has opened or clicked an email in the last 12 months
- Is a CCSN partner contact

### ARCHIVE (remove from CC, preserve for reimport)
- Implicit opt-in with no engagement in 12+ months
- Not in QuickBase
- Not a CCSN partner

### PURGE (remove permanently)
- Already unsubscribed
- Role accounts (info@, noreply@, etc.) with no engagement or QB presence
- Junk/invalid addresses
- Duplicate emails (kept the record with most metadata)

*Generated 2026-04-13T19:32:57.400871+00:00*