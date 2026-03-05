# Workflow: Scrape Business Listings

## Objective
Collect fresh business-for-sale listings from major marketplaces and normalize them into a unified format for matching.

## Sources

| Source | Method | Reliability | Notes |
|--------|--------|-------------|-------|
| BizBuySell | HTML scraping | High | Largest volume; 2s delay required |
| BizQuest | HTML scraping | High | Same parent co as BizBuySell |
| BusinessesForSale | RSS feed | Very High | Most stable; XML-based |
| LoopNet | HTML scraping | Medium | Bot detection; 4s delay required |
| Axial | Manual / stub | Low | Private network; no web scraping |

---

## Running Scrapers

### All at once (via pipeline):
```bash
python tools/run_pipeline.py --states FL TX GA NC SC --skip-email --skip-sheets
```

### Individually:
```bash
python tools/scrape_bizbuysell.py --states FL TX GA NC SC --max-pages 5 --out .tmp/raw_listings_bizbuysell.json
python tools/scrape_bizquest.py --states FL TX GA NC SC --max-pages 5 --out .tmp/raw_listings_bizquest.json
python tools/scrape_businessesforsale.py --states FL TX GA NC SC --out .tmp/raw_listings_businessesforsale.json
python tools/scrape_loopnet.py --states FL TX GA NC SC --max-pages 3 --out .tmp/raw_listings_loopnet.json
python tools/scrape_axial.py --out .tmp/raw_listings_axial.json
```

---

## Rate Limits and Delays

| Source | Delay | Setting |
|--------|-------|---------|
| BizBuySell | 2 seconds | `SCRAPER_DELAY_BIZBUYSELL` in .env |
| BizQuest | 2 seconds | `SCRAPER_DELAY_DEFAULT` in .env |
| BusinessesForSale | 2 seconds | `SCRAPER_DELAY_DEFAULT` in .env |
| LoopNet | 4 seconds | `SCRAPER_DELAY_LOOPNET` in .env |

Do NOT reduce delays below these values. Sites will block you.

---

## Diagnosing Broken Scrapers

If a scraper returns 0 results or fails, it usually means the site changed its HTML structure.

### Step 1: Check the debug HTML
Each scraper saves debug HTML when it can't find listings:
```
.tmp/debug_bbs_FL_p1.html   ← BizBuySell debug
.tmp/debug_bq_FL_p1.html    ← BizQuest debug
.tmp/debug_loopnet_FL_p1.html
```

Open the file and inspect the structure.

### Step 2: Find the correct selectors
Use browser DevTools (F12 → Elements) on the live site:
1. Right-click a listing card → "Inspect"
2. Find the repeating container element (div, article, li)
3. Note its class or data attribute

### Step 3: Update the SELECTORS dict
Each scraper has a `SELECTORS` dict at the top of the file. Update it:
```python
SELECTORS = {
    "listing_card": "div.NEW_CARD_CLASS",  # Updated
    "title": "h3.NEW_TITLE_CLASS a",
    ...
}
```

### Step 4: Test with 1 page
```bash
python tools/scrape_bizbuysell.py --states FL --max-pages 1
```

### Step 5: Document the change
Add a note here with the date and what changed:
```
2026-02-17: BizBuySell updated card class from 'listing-result' to 'srp-card'. Updated SELECTORS.
```

---

## BizBuySell Specific Notes
- Pagination: Pages go up to ~50. Default max is 5 pages (adjust with --max-pages).
- Some listings show "Price Not Disclosed" — these have null asking_price.
- Financial data (revenue, CF) is often in a `<ul class="data">` with labeled `<li>` items.
- If blocked (403): increase SCRAPER_DELAY_BIZBUYSELL to 5+.

## BizQuest Specific Notes
- Same parent company as BizBuySell (BizBuySell Inc.).
- Pagination uses `?page=N` parameter.
- May have duplicate listings with BizBuySell — deduplication handles this.

## BusinessesForSale Specific Notes
- RSS feed is the most reliable method. Don't switch to HTML scraping unless the feed breaks.
- Feed URL format: `https://www.businessesforsale.com/rss/us-{state}/businesses-for-sale.xml`
  - Example: `https://www.businessesforsale.com/rss/us-fl/businesses-for-sale.xml`
- If the feed returns 0 items: visit https://www.businessesforsale.com/info/rssmenu.aspx to find updated URLs.
- Financial data is embedded in the `<description>` field as HTML. The scraper parses it.

## LoopNet Specific Notes
- LoopNet is a CoStar product with aggressive bot detection.
- If getting consistent 403s:
  1. Increase `SCRAPER_DELAY_LOOPNET` to 8+ seconds
  2. Run at off-peak hours (early morning)
  3. Rotate User-Agent strings (expand USER_AGENTS list in the script)
- LoopNet's `/biz/` section has business sales (NOT commercial real estate listings).
- URL: `https://www.loopnet.com/biz/{state}-businesses-for-sale/`

## Axial Specific Notes
- **Do NOT attempt web scraping.** Axial is a private network and ToS prohibits it.
- **Current approach:** Manual entry via `.tmp/axial_manual.json`
  - Copy the template from `.tmp/axial_template.json`
  - Fill in deal details from Axial email alerts
  - Save and run `python tools/scrape_axial.py` to include them in the pipeline
- **Phase 2:** Gmail API integration to auto-parse Axial deal alert emails.

---

## Merged Output

After running all scrapers, merge with:
```bash
# Via pipeline:
python tools/run_pipeline.py --skip-scrape   # merges existing .tmp/raw_listings_*.json

# Or merge manually (for debugging):
python -c "
import glob, json
from pathlib import Path
all_listings = []
for f in glob.glob('.tmp/raw_listings_*.json'):
    data = json.loads(Path(f).read_text())
    all_listings.extend(data)
    print(f'{f}: {len(data)} listings')

# Dedup by URL
seen = set()
deduped = []
for l in all_listings:
    if l['url'] not in seen:
        seen.add(l['url'])
        deduped.append(l)

Path('.tmp/all_listings.json').write_text(json.dumps(deduped, indent=2))
print(f'Total unique: {len(deduped)}')
"
```

---

## Dealing with IP Blocks (Akamai)

BizBuySell, BizQuest, and LoopNet use Akamai WAF which can block entire IP ranges.
Symptoms: immediate 403 "Access Denied" even with Playwright browser.

**Solutions in order of ease:**

1. **SerpAPI (recommended):** Add `SERPAPI_KEY` to `.env`. The `scrape_serpapi.py` scraper
   searches Google for listings — Google is never IP-blocked. Free tier: 100 searches/month.
   ```bash
   python tools/scrape_serpapi.py --states FL TX GA NC SC --out .tmp/raw_listings_serpapi.json
   ```

2. **VPN / change IP:** Switch IP and rerun. Akamai blocks specific IPs, not accounts.

3. **Wait 24 hours:** Akamai IP bans often expire automatically.

4. **Manual collection:** Browse the sites normally in your browser (no block), copy listing
   details, and enter them in `.tmp/axial_manual.json` format using the template.

## Changelog
| Date | Change |
|------|--------|
| 2026-02-17 | Initial setup. Playwright + playwright-stealth for bot detection bypass. |
| 2026-02-17 | SerpAPI fallback scraper added for IP-blocked environments. |
