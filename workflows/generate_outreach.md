# Workflow: Generate Seller Outreach Emails

## Objective
Generate personalized outreach emails from Jordi (Valar Brokers) to listing brokers or sellers. The goal is to excite the seller that a specific, qualified buyer is ready for their business.

---

## Running Email Generation

```bash
python tools/generate_emails.py
```

With custom options:
```bash
python tools/generate_emails.py \
  --matches .tmp/matches.json \
  --buyers .tmp/buyers.json \
  --listings .tmp/all_listings.json \
  --out .tmp/email_drafts.json \
  --min-score 60
```

**Use Sonnet for A-grade matches (higher quality, ~5x cost):**
```bash
python tools/generate_emails.py --upgrade-a-grade
```

---

## Email Generation Thresholds

| Score | Grade | Action |
|-------|-------|--------|
| 80-100% | A | Generate with Haiku (or Sonnet if --upgrade-a-grade) |
| 60-79% | B | Generate with Haiku |
| 40-59% | C | Skip (default) — review matches manually |
| < 40% | F | Never generate |

To generate emails for C-grade matches too:
```bash
python tools/generate_emails.py --min-score 40
```

---

## Model Selection and Cost

| Model | Quality | Cost per 1K emails (est.) |
|-------|---------|--------------------------|
| claude-haiku-3-5-20241022 | Good | ~$0.80 |
| claude-sonnet-4-5-20250929 | Excellent | ~$4.00 |

Configure in `.env`:
```
EMAIL_MODEL=claude-haiku-3-5-20241022
```

---

## What Makes a Good Outreach Email

The Claude prompt is calibrated to produce emails that:

✅ **Do:**
- Open with the buyer's single strongest credential for THIS specific deal
- Reference specific listing details: business type, city, asking price, years established
- Mention that the buyer has a signed buyer-broker agreement (signals seriousness)
- Frame the buyer's financing capability without revealing exact amounts
- End with a low-friction CTA: "Would a 15-minute call this week work?"

❌ **Don't:**
- Open with "I hope this email finds you well"
- Use words like "reach out," "circle back," "synergy"
- Share the buyer's exact liquid net worth or loan approval amount
- Sound like a template (the prompt explicitly prohibits this)
- Be longer than 250 words

---

## Reviewing Generated Emails

1. Open `.tmp/email_drafts.json` or review in Google Sheets → "Email Drafts" tab
2. For each email draft, check:
   - [ ] Subject line is specific (mentions business type + location or key detail)
   - [ ] First paragraph establishes buyer credibility immediately
   - [ ] Specific listing details are referenced (not generic)
   - [ ] Body is 180-250 words
   - [ ] CTA is clear and low-friction
3. Edit as needed before sending

---

## Sending Emails

This tool generates drafts only — it does NOT send emails. To send:

**Option 1 — Gmail manual:**
1. Open Google Sheets → Email Drafts tab
2. Copy subject and body for each email
3. Send from your Gmail account

**Option 2 — Gmail API (Phase 2):**
A future `send_emails.py` tool will use the Gmail API to:
- Read drafts from `email_drafts.json`
- Create Gmail drafts (not send automatically — still requires human review)
- Or send to a queue for batch review

---

## Tone Guidelines

The email represents Jordi Quevedo-Valls / Valar Brokers. Maintain this voice:
- **Confident, not pushy.** The buyer is qualified; we're not begging for a meeting.
- **Specific, not generic.** Every email should feel like it was written for this exact listing.
- **Professional, not stiff.** Brokers talk to each other like peers, not like a cold sales call.
- **Brief, not verbose.** Listing brokers are busy. Get to the point.

---

## Troubleshooting

**Generated emails are too generic:**
- Check that the listing has sufficient detail (title, industry, location, financials)
- Listings with many `null` fields produce weaker emails — find the listing URL and add missing data manually
- Try `--upgrade-a-grade` (Sonnet produces more specific output)

**Rate limit errors:**
- The script waits 30 seconds and retries once on rate limits
- If persistent, wait 60 seconds and rerun: `python tools/generate_emails.py`
- Rate limits reset per minute

**API key errors:**
- Check `ANTHROPIC_API_KEY` in `.env` is correct and starts with `sk-ant-`
- Verify at https://console.anthropic.com

**Emails are too long:**
- The prompt caps at 250 words. If Claude ignores this, add to the prompt: "CRITICAL: Email body must be under 200 words."
- Edit `SYSTEM_PROMPT` in `tools/generate_emails.py`

---

## Prompt Customization

To customize the email tone or content, edit:
- `SYSTEM_PROMPT` in `tools/generate_emails.py` — overall instructions and voice
- `build_user_prompt()` function — what deal/buyer info is provided per email

After editing, test with 1 match:
```bash
# Generate just the first match
python -c "
import json
from pathlib import Path
matches = json.loads(Path('.tmp/matches.json').read_text())
# Temporarily save just one match
Path('.tmp/test_match.json').write_text(json.dumps([matches[0]], indent=2))
"
python tools/generate_emails.py --matches .tmp/test_match.json --out .tmp/test_draft.json
cat .tmp/test_draft.json
```

---

## Changelog
| Date | Change |
|------|--------|
| 2026-02-17 | Initial implementation. Haiku by default, Sonnet for A-grade option. |
