# Off-Market Business Lead Gen Workflow

**Objective:** Find 10+ off-market businesses per buyer that match their acquisition criteria, confirm seller interest via LinkedIn outreach, then present confirmed sellers to buyers.

**Last Updated:** 2026-02-17

---

## Inputs Required

- `BIZ BROKER MATCHES - buyers w agreements.pdf` — buyer criteria (already parsed into `tools/buyers_db.py`)
- `.env` — API keys (see setup below)

## Outputs

- `.tmp/MASTER_LEADS_[date].csv` — all leads across all buyers with LinkedIn messages
- `.tmp/leads/leads_[buyer_id].csv` — per-buyer lead lists
- `.tmp/LINKEDIN_SEARCH_URLS_[date].csv` — LinkedIn search URLs for manual prospecting
- Confirmed seller interest recorded in status columns

---

## Step 1: API Key Setup (One Time)

Add these to `.env`:

| Key | Where to get | Cost | Priority |
|-----|-------------|------|----------|
| `APOLLO_API_KEY` | app.apollo.io → Settings → API | Free (50/mo) or $49/mo | HIGH |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Pay-per-use | HIGH (AI messages) |
| `YELP_API_KEY` | yelp.com/developers | Free | MEDIUM |
| `SERPAPI_KEY` | serpapi.com | $50/mo | LOW |

Apollo.io is the most important — it has 275M+ companies with revenue/employee data and owner contact info.

**To get Apollo free API key:**
1. Go to https://app.apollo.io/settings/integrations/api
2. Create free account → Settings → Integrations → API → Create Key
3. Paste into `.env` as `APOLLO_API_KEY=your_key_here`

---

## Step 2: Run Lead Gen

```bash
# Generate LinkedIn search URLs (works immediately, no API keys needed)
python tools/run_lead_gen.py --linkedin-only

# Run for ALL buyers (requires API keys for meaningful results)
python tools/run_lead_gen.py

# Run for ONE specific buyer
python tools/run_lead_gen.py --buyer magus_abraxas

# List all buyer IDs
python tools/run_lead_gen.py --list-buyers

# Force fresh search (ignore cache)
python tools/run_lead_gen.py --no-cache
```

---

## Step 3: LinkedIn Outreach Process

### Option A: VA-Assisted (Recommended)
1. Open `LINKEDIN_SEARCH_URLS_[date].csv`
2. For each buyer, click the LinkedIn People Search URL
3. Filter results by: current company > 10 employees, title = owner/founder/CEO
4. Use the `connection_request` text from MASTER_LEADS.csv when sending connection requests
5. After connecting (24-48 hours), send the `inmail` message text

### Option B: LinkedIn Sales Navigator (Most Efficient)
If you have Sales Navigator ($99/mo):
1. Use the LinkedIn Company Search URLs to find target businesses
2. Use Lead Builder to filter by company size, geography, industry
3. Save leads and send InMails directly

### Outreach Rules
- Send max 20-25 connection requests per day (LinkedIn limits)
- Send max 10 InMails per day (free) / 50 per day (Sales Navigator)
- Do NOT use "buying your business" language in connection requests
- Always be soft and curiosity-driven: "we have buyers in your space"
- Follow up once if no response after 5-7 days

---

## Step 4: Track Seller Responses

In `MASTER_LEADS.csv`, update these columns as you get responses:

| Column | Values |
|--------|--------|
| `status` | `new` → `contacted` → `responded` → `qualified` → `passed` |
| `outreach_sent_date` | Date you sent the message |
| `seller_responded` | Yes / No |
| `seller_interested` | Yes / No / Maybe |
| `response_notes` | What they said |
| `next_action` | Call scheduled / Send NDA / Follow up / Archive |

---

## Step 5: Qualify Interested Sellers

When a seller responds with interest:

1. **Confirm EBITDA range** — ask: "Just to make sure we're aligned, can you share a rough sense of your annual profit/cash flow?"
2. **Confirm geography** — confirm they match the buyer's location preference
3. **Confirm industry** — make sure the business type matches
4. **Check exclusivity** — are they listed anywhere else?
5. **Set expectations** — explain the process: intro call, NDA, financials, then buyer intro

---

## Step 6: Present to Buyers

Once you have 10+ confirmed-interested sellers per buyer:
1. Create a blind 1-pager per seller (no name, generic description, EBITDA range, location)
2. Send to buyer: "We have 10 potential matches — here's a summary. Which would you like to learn more about?"
3. For each match they want to pursue: execute NDA, share full details, facilitate intro call

---

## Lead Source Priority

| Source | Quality | Volume | Cost |
|--------|---------|--------|------|
| Apollo.io API | High (revenue/contact data) | High | $0-99/mo |
| LinkedIn (manual) | Very High (direct owners) | Low-Medium | Time |
| Yelp API | Medium | Medium | Free |
| Yellow Pages | Low-Medium | High | Free |
| Manta.com | Medium | Medium | Free |
| Google (SerpAPI) | Medium | Medium | $50/mo |

---

## Off-Market Lead Generation Strategies (Beyond This Tool)

These require human time but generate the best leads:

1. **LinkedIn Cold Outreach** — use search URLs, message owners directly
2. **Industry Associations** — contact association membership directors
3. **Accountant/CPA Referrals** — CPAs know which clients are thinking about exit
4. **Business Attorney Referrals** — same principle as CPAs
5. **Trade Shows** — attend industry-specific events, talk to exhibitors
6. **Direct Mail** — send letters to businesses in target industries/geographies
7. **Warm Outreach via Existing Network** — ask referral partners

---

## Buyer IDs Reference

Run `python tools/run_lead_gen.py --list-buyers` for full list.

Key buyers and their IDs:
- `magus_abraxas` — Manufacturing, Midwest, $5M-$100M
- `castle_pines` — B2B Services/Software, US, $10M-$50M
- `black_swan` — Manufacturing, Mid-Atlantic, $1M-$7M EBITDA
- `cicada_fund` — General, Southeast, $5M-$18M
- `strategic_succession` — Industrial/Manufacturing, Houston TX
- `cedar_crest` — Manufacturing/Healthcare, US, $500K-$3M EBITDA
- `mode_growth` — Manufacturing/Healthcare, West Coast
- `baruk_capital` — Home Services, Dallas/Miami, $1M-$3M EBITDA
- `back_9_capital` — Services/IT/Healthcare, NV/AZ/UT/CA
- `zeon_investments` — Legal/Immigration, TX/FL/TN

---

## Troubleshooting

**"No leads found"** → Check API keys in `.env`. Apollo key is most important.

**Apollo rate limit** → Wait 1 minute, retry. Upgrade plan if needed.

**Manta/YP blocked (403)** → Normal — these sites block scrapers. Use Apollo + Yelp instead.

**LinkedIn account restricted** → You sent too many requests too fast. Pause 24-48 hours. Stay under 25/day.

**Seller not responding** → Follow up once at day 7. If still no response, mark `status=passed` and move on.

**Low match quality from Apollo** → Tighten industry keywords in `tools/buyers_db.py`. Add more specific sub-industries.
