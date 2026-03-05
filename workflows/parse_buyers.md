# Workflow: Parse Buyer Criteria from PDF

## Objective
Extract structured buyer criteria from the broker's PDF (buyer-broker agreements) and save them to `.tmp/buyers.json`. This JSON file is the source of truth for all matching.

## When to Run
- First-time setup (before any pipeline run)
- When a new buyer-broker agreement is added to the PDF
- When buyer criteria change

## Prerequisites
- PDF file present: `BIZ BROKER MATCHES - buyers w agreements.pdf`
- pdfplumber installed: `pip install pdfplumber`
- ANTHROPIC_API_KEY in `.env` (used as Claude fallback if regex parse is sparse)

---

## Steps

### 1. Run the Parser
```bash
python tools/parse_buyers_pdf.py
```

Or with explicit paths:
```bash
python tools/parse_buyers_pdf.py --pdf "BIZ BROKER MATCHES - buyers w agreements.pdf" --out .tmp/buyers.json
```

Force Claude API extraction (better for complex PDFs):
```bash
python tools/parse_buyers_pdf.py --force-claude
```

### 2. Review the Output
**This step is mandatory.** The parser uses regex + Claude fallback, but PDFs vary widely in formatting. You must verify before running the pipeline.

Open `.tmp/buyers.json` and check each buyer:
- [ ] Name and contact info are correct
- [ ] Industry preferences are complete and accurate
- [ ] Geography states are correct (2-letter codes)
- [ ] Financial ranges (asking price, revenue, cash flow) are correct
- [ ] Deal structure (SBA, seller financing) reflects the agreement

### 3. Manual Corrections
Edit `.tmp/buyers.json` directly. The schema for each buyer:

```json
{
  "buyer_id": "buyer_001",
  "buyer_name": "First Last",
  "company_name": "Company LLC",
  "contact_email": "email@example.com",
  "contact_phone": "305-555-0100",
  "agreement_type": "buyer_broker_agreement",
  "agreement_signed_date": "2025-11-01",

  "criteria": {
    "industry_preferences": ["HVAC", "Plumbing", "Home Services"],
    "industry_exclusions": ["Restaurant", "Retail", "Franchise"],
    "geography_states": ["FL", "TX", "GA", "NC", "SC"],

    "financials": {
      "asking_price_min": 500000,
      "asking_price_max": 2000000,
      "revenue_min": 750000,
      "revenue_max": 5000000,
      "cash_flow_min": 150000,
      "cash_flow_max": null,
      "cash_flow_multiple_max": 5.0,
      "revenue_multiple_max": null
    },

    "deal_structure": {
      "seller_financing_ok": true,
      "sba_loan_preferred": true,
      "all_cash_ok": false,
      "real_estate_preferred": false
    },

    "business_attributes": {
      "employees_min": 5,
      "employees_max": 50,
      "years_in_business_min": 3,
      "absentee_owner_ok": false,
      "recurring_revenue_preferred": true
    },

    "scoring_weights": {
      "industry_match": 30,
      "geography_match": 20,
      "financials_in_range": 25,
      "cash_flow_multiple": 10,
      "years_established": 8,
      "deal_structure": 7
    }
  },

  "buyer_profile_summary": "Experienced operator seeking home services businesses in the Southeast. Prefers SBA-eligible deals.",
  "notes": "Has $400K liquid. Pre-qualified for SBA up to $2M. Wants to close in 90 days."
}
```

### 4. Add a New Buyer Manually
1. Copy an existing buyer object in `buyers.json`
2. Change `buyer_id` to the next number (e.g., `buyer_004`)
3. Fill in all fields
4. Set scoring weights to sum to 100

### 5. Validate JSON
```bash
python -c "import json; buyers = json.load(open('.tmp/buyers.json')); print(f'{len(buyers)} buyers OK')"
```

---

## Scoring Weights Guide

Adjust per-buyer weights in `scoring_weights` to reflect each buyer's true priorities.

| Buyer Type | Industry | Geography | Financials | CF Multiple | Years | Structure |
|------------|----------|-----------|------------|-------------|-------|-----------|
| Strategic operator | 35 | 15 | 25 | 10 | 8 | 7 |
| Financial buyer (PE) | 20 | 15 | 30 | 20 | 8 | 7 |
| Geography-locked | 20 | 30 | 25 | 10 | 8 | 7 |

All weights must sum to exactly 100.

---

## Troubleshooting

**Parser found 0 or 1 buyers when there should be more:**
- The PDF may not have clear section separators
- Try `--force-claude` to use the Claude API for extraction
- If Claude also fails, copy the raw text from the PDF (open in browser or Word) and manually structure `buyers.json`

**Financial values are wrong (e.g., $500K parsed as 500 instead of 500000):**
- Edit `.tmp/buyers.json` directly — set the correct integer value
- Note the pattern for future: the `clean_price()` function handles $M and $K suffixes

**Industry preferences are empty:**
- Manually add them from the buyer agreement
- The parser looks for keywords in `INDUSTRY_KEYWORDS` list in the script

---

## Notes
- `.tmp/buyers.json` is NOT disposable. Back it up before re-running the parser.
- The parser writes `_parse_source` and `raw_text` debug fields to each buyer — these can be deleted after verification
- Do not run the parser again after manually editing buyers.json without first backing up your edits
