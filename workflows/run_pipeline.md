# Workflow: Run Deal Flow Pipeline

## Objective
Execute the full deal flow pipeline: scrape new listings, match them to buyer criteria, generate seller outreach emails, and export to Google Sheets.

## When to Run
- Daily or every 2-3 days to catch new listings
- After adding a new buyer to buyers.json
- After updating buyer criteria

## Prerequisites
- `.env` filled out with real API keys (ANTHROPIC_API_KEY, GOOGLE_SHEET_ID)
- `buyers.json` verified and correct (run `parse_buyers.md` workflow first if not done)
- Python dependencies installed: `pip install -r requirements.txt`

---

## Steps

### 1. Quick Check
Before running, verify that buyers.json exists and looks correct:
```bash
python -c "import json; buyers = json.load(open('.tmp/buyers.json')); print(f'{len(buyers)} buyers loaded'); [print(f'  - {b[\"buyer_name\"]} | {b[\"criteria\"][\"geography_states\"]}') for b in buyers]"
```

### 2. Run Full Pipeline (All States)
```bash
python tools/run_pipeline.py --states FL TX GA NC SC
```

This runs all 6 steps automatically. It will pause after parsing buyers and ask you to confirm.

### 3. Common Flags

```bash
# Skip parsing (buyers.json already good):
python tools/run_pipeline.py --states FL TX GA NC SC

# Re-parse buyers PDF first:
python tools/run_pipeline.py --states FL TX GA NC SC --force-parse

# Skip email generation (just get matches):
python tools/run_pipeline.py --states FL TX --skip-email

# Skip Sheets export (for testing):
python tools/run_pipeline.py --states FL --max-pages 1 --skip-sheets

# Higher minimum match score:
python tools/run_pipeline.py --min-score 50 --min-email-score 70

# Use Sonnet for A-grade emails (higher quality, higher cost):
python tools/run_pipeline.py --upgrade-a-grade

# Only Florida, 1 page — fast smoke test:
python tools/run_pipeline.py --states FL --max-pages 1 --skip-sheets
```

### 4. Run Individual Tools (for debugging)

```bash
# Just BizBuySell:
python tools/scrape_bizbuysell.py --states FL --max-pages 2 --out .tmp/raw_listings_bizbuysell.json

# Just matching:
python tools/match_deals.py --listings .tmp/all_listings.json --buyers .tmp/buyers.json --out .tmp/matches.json

# Just emails (for existing matches):
python tools/generate_emails.py --matches .tmp/matches.json --buyers .tmp/buyers.json --listings .tmp/all_listings.json --out .tmp/email_drafts.json

# Just Sheets export:
python tools/export_to_sheets.py
```

---

## Expected Output

| File | Contents |
|------|----------|
| `.tmp/raw_listings_bizbuysell.json` | Scraped BizBuySell listings |
| `.tmp/raw_listings_bizquest.json` | Scraped BizQuest listings |
| `.tmp/raw_listings_businessesforsale.json` | RSS feed listings |
| `.tmp/raw_listings_loopnet.json` | LoopNet listings (may be empty if blocked) |
| `.tmp/all_listings.json` | Merged, deduplicated listings |
| `.tmp/matches.json` | All matches above min score, sorted by score |
| `.tmp/email_drafts.json` | Generated email drafts for B/A-grade matches |
| Google Sheets | Matches, Email Drafts, All Listings tabs |

---

## Expected Runtime

| Step | Time |
|------|------|
| Scraping (5 states, 5 pages each) | ~10-15 min |
| Matching | < 1 min |
| Email generation (50 drafts) | ~2-3 min |
| Sheets export | < 1 min |
| **Total** | **~15-20 min** |

---

## Error Recovery

**One scraper failed:** Other scrapers continue. Rerun just that scraper:
```bash
python tools/scrape_bizbuysell.py --states FL TX GA NC SC --max-pages 5 --out .tmp/raw_listings_bizbuysell.json
```
Then merge manually and continue from matching:
```bash
python tools/run_pipeline.py --skip-scrape
```

**Matching produced 0 results:**
- Lower the min score: `--min-score 30`
- Check buyers.json for overly restrictive criteria
- Run with `--min-score 0` to see all scores and understand what's failing

**Email generation failed:**
- Check ANTHROPIC_API_KEY in .env
- Try running just email generation: `python tools/generate_emails.py`
- If rate limited, wait 1 minute and retry

**Sheets export failed:**
- Make sure credentials.json is in the project root
- First run will open a browser for OAuth authorization
- Make sure GOOGLE_SHEET_ID is correct in .env

---

## Cost Estimate

Per full pipeline run:
- API calls: ~$0.50–$2.00 (depends on number of email drafts generated)
- Haiku model: ~$0.80/MTok input + $4/MTok output
- 100 email drafts at ~800 tokens each ≈ $0.80 total

---

## Notes
- `.tmp/` files are disposable — regenerated on each run
- `buyers.json` is NOT disposable — keep it backed up
- LoopNet may block scraping — if consistent 403s, increase `SCRAPER_DELAY_LOOPNET` in .env
- BizBuySell may block if you scrape too fast — keep delay at 2+ seconds
