# Phase 6: New Sending Subdomain Setup & Warm-Up

The root domain `conciergecaradvisors.com` has an 81% spam-block rate. Changing the `from` address (e.g., `newsletter@` to `news@`) does NOT help — inbox providers evaluate the **domain**, not the address prefix. A new **subdomain** starts with a neutral reputation and builds its own score independently.

## 6A. Create the Subdomain via GoDaddy API

Use the GoDaddy Domains API to create DNS records for the new marketing subdomain: `news.conciergecaradvisors.com`.

**GoDaddy API details:**
- Production base URL: `https://api.godaddy.com`
- Auth: API Key + Secret (production keys from https://developer.godaddy.com)
- Endpoint for adding records: `PUT /v1/domains/{domain}/records/{type}/{name}`
- All GoDaddy APIs are free to use

**Records to create via API:**

1. **DKIM records** — Constant Contact provides these. Two options:
   - **CNAME method (recommended):** CC manages key rotation for you. They provide two CNAME records.
   - **TXT method:** CC generates a public/private key pair. You publish the public key as TXT records. Better if running multiple CC accounts on the same domain.

2. **DMARC record** for the subdomain:
   - TXT record: `_dmarc.news` -> `v=DMARC1; p=none; rua=mailto:dmarc-reports@conciergecaradvisors.com`
   - Start with `p=none` (monitoring), move to `p=quarantine` then `p=reject` once deliverability is confirmed

3. **SPF — Do NOT add.** Constant Contact does NOT support SPF alignment. Their Envelope-From domain is always their own, so SPF alignment will always fail. Do NOT add `include:spf.constantcontact.com` — it wastes a DNS lookup and achieves nothing. DMARC compliance is achieved through DKIM alignment only.

**GoDaddy API example (Python):**

```python
import requests

API_KEY = "your_key"
API_SECRET = "your_secret"
DOMAIN = "conciergecaradvisors.com"
SUBDOMAIN = "news"

headers = {
    "Authorization": f"sso-key {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json"
}

# DKIM CNAME records (values provided by Constant Contact)
dkim_records = [
    {
        "type": "CNAME",
        "name": f"selector1._domainkey.{SUBDOMAIN}",
        "data": "value-from-constant-contact.com",
        "ttl": 3600
    },
    {
        "type": "CNAME",
        "name": f"selector2._domainkey.{SUBDOMAIN}",
        "data": "value-from-constant-contact.com",
        "ttl": 3600
    }
]

# DMARC record for subdomain
dmarc_record = [{
    "type": "TXT",
    "name": f"_dmarc.{SUBDOMAIN}",
    "data": "v=DMARC1; p=none; rua=mailto:dmarc-reports@conciergecaradvisors.com",
    "ttl": 3600
}]

for record in dkim_records + dmarc_record:
    url = f"https://api.godaddy.com/v1/domains/{DOMAIN}/records"
    resp = requests.patch(url, json=[record], headers=headers)
    print(f"Added {record['name']}: {resp.status_code}")
```

**The DKIM values above are placeholders.** Actual values come from Constant Contact after you:
1. Go to My Account -> Advanced Settings -> Add Self-Authentication
2. Select the subdomain as the sending domain
3. CC generates the CNAME or TXT key pairs
4. Copy those exact values into the GoDaddy API calls
5. Allow 24-48 hours for DNS propagation, then activate in CC

## 6B. Configure Constant Contact Sending Identity

1. Add a new verified sender email on the subdomain (e.g., `news@news.conciergecaradvisors.com`)
2. Set as the default sending address for all campaigns
3. **Stop sending from `newsletter@conciergecaradvisors.com` entirely** — let the root domain recover passively
4. Complete DKIM self-authentication for the new subdomain

## 6C. Warm-Up Schedule

| Week | Daily Volume | Audience |
|------|-------------|----------|
| 1 | 5-10 | Internal team + contacts who opened/clicked in last 90 days |
| 2 | 15-25 | Expand to engaged contacts (opened/clicked in last 6 months) |
| 3 | 30-50 | Full KEEP list, most engaged first |
| 4 | 100+ | Full KEEP list at normal cadence |
| 5-6 | Standard | Normal campaign operations |

**Rules:**
- Send to engaged contacts first — opens and replies build the subdomain's reputation. Gmail weighs this heavily.
- Monitor daily. If bounce rate exceeds 2% or spam complaints exceed 0.1%, pause and investigate.
- No blast sends during warm-up. Every send is a controlled batch to a targeted segment.
- Generate replies if possible — a re-engagement email asking people to reply creates positive engagement signals.
- Do NOT send to the ARCHIVE list during warm-up.

## 6D. Post-Warm-Up: Re-Permission Campaign for Archived Contacts

After 6+ weeks of clean sending with good engagement on the subdomain:

1. Import a small batch from `archive.json` (start with 50-100)
2. Send a single re-permission email: "Click here to keep receiving updates from Concierge Care Advisors"
3. Clicked -> add to KEEP list
4. No engagement after 2 sends -> leave archived permanently
5. Scale up archive batches gradually, monitoring reputation impact

---

## Additional Important Notes

- **Root domain isolation:** Moving marketing to the subdomain protects advisor day-to-day email. Every advisor sending from `@conciergecaradvisors.com` will no longer carry the baggage of the marketing reputation. This is a permanent structural improvement.
- **GoDaddy API keys** are generated at https://developer.godaddy.com — use production keys, not OTE (test environment). The API is free.
