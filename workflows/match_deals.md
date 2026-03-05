# Workflow: Match Deals to Buyer Criteria

## Objective
Score every scraped deal against every buyer's criteria using a weighted algorithm. Output high-quality matches for email outreach.

---

## Running the Matcher

```bash
python tools/match_deals.py
```

With custom options:
```bash
python tools/match_deals.py \
  --listings .tmp/all_listings.json \
  --buyers .tmp/buyers.json \
  --out .tmp/matches.json \
  --min-score 40
```

---

## Scoring System

### Phase 1: Hard Stops (automatic disqualification)

A deal is immediately dropped — score = 0, not included in output — if ANY of these trigger:

| Hard Stop | Condition |
|-----------|-----------|
| Price too high | `asking_price > asking_price_max` (if buyer has max) |
| Price too low | `asking_price < asking_price_min` (if buyer has min) |
| Wrong state | `location_state not in geography_states` (if states specified) |
| Cash flow too low | `cash_flow < cash_flow_min` (if buyer has min AND deal has CF) |
| Industry excluded | `deal industry matches buyer's exclusion list` |

### Phase 2: Weighted Scoring (100 points total)

| Dimension | Default Points | Logic |
|-----------|----------------|-------|
| Industry match | 30 | Full: primary preference. 60%: same broad category. 0: no match. |
| Geography match | 20 | Full: state in buyer's list. 0: state not in list. |
| Financials in range | 25 | Split: Price 40% + Revenue 32% + CF 28%. Unknown = 30% credit. |
| CF multiple | 10 | Inverse proportional (lower multiple = higher score). |
| Years established | 8 | Prorated up to 10 years. Full points at 10+ years. |
| Deal structure | 7 | SBA eligible + seller financing. |

### Grades

| Grade | Score Range | Meaning |
|-------|-------------|---------|
| A | 80-100% | Strong match — prioritize immediately |
| B | 60-79% | Good match — send outreach |
| C | 40-59% | Possible match — review manually |
| F | < 40% | Poor match — dropped from output |

---

## Adjusting Thresholds

**Too few matches? Lower the threshold:**
```bash
python tools/match_deals.py --min-score 30
```

**Too many low-quality matches? Raise it:**
```bash
python tools/match_deals.py --min-score 50
```

**See why deals are failing (diagnose):**
```bash
python tools/match_deals.py --min-score 0
```
Then open `.tmp/matches.json` and look at low-scoring deals. Examine `score_breakdown` and `hard_stops` to understand what's being disqualified.

---

## Adjusting Buyer Scoring Weights

Weights are per-buyer in `buyers.json` under `criteria.scoring_weights`.
**Must sum to exactly 100.**

Example: Buyer who prioritizes financial returns over industry/geography:
```json
"scoring_weights": {
  "industry_match": 20,
  "geography_match": 10,
  "financials_in_range": 35,
  "cash_flow_multiple": 20,
  "years_established": 8,
  "deal_structure": 7
}
```

---

## Interpreting Match Output

Each match in `matches.json` contains:

```json
{
  "match_id": "match_buyer_001_bizbuysell_12345",
  "buyer_name": "Michael Johnson",
  "deal_title": "Established HVAC Company - Tampa, FL",
  "score_pct": 84.0,
  "grade": "A",
  "score_breakdown": {
    "industry_match": {"score": 30, "max": 30, "reason": "HVAC matches primary preference"},
    "geography_match": {"score": 20, "max": 20, "reason": "FL is in target states"},
    ...
  },
  "hard_stops": [],
  "soft_flags": ["SBA eligibility not confirmed", "Cash flow not listed"],
  "match_summary": "HVAC matches primary preference | FL is in target states | Price $850K in range"
}
```

**`soft_flags`** are warnings (not disqualifiers) — information missing from the listing that would help confirm the match. When you review a match, check these flags and look up the missing info on the listing page.

---

## Common Issues

**All matches have score < 40:**
- Check that buyer geography states match the scraped states
- Check that buyer industry preferences match the scraped industry categories (run: `python tools/match_deals.py --min-score 0` and look at `score_breakdown.industry_match`)
- The industry matching uses keyword matching — make sure the preference strings are standard (e.g., "HVAC" not "Air Conditioning")

**Same business appears as multiple matches (different buyers):**
- This is expected. Each buyer-deal combination is a separate match.
- The email draft for each is personalized to that specific buyer.

**Matches exist but no email drafts were generated:**
- Check that match scores are >= `MIN_EMAIL_SCORE` (default 60)
- Run: `python tools/generate_emails.py --min-score 40` to lower the email threshold

---

## Changelog
| Date | Change |
|------|--------|
| 2026-02-17 | Initial implementation. 6-dimension weighted scoring. |
