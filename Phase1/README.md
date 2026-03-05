# Phase 1 — Claim Intake & Mileage Automation
### Insurance Adjuster AI Assistant

---

## What This Does

When a carrier sends you a claim assignment email in Gmail, this system automatically:

1. **Parses** the email using Claude AI — extracts claim number, carrier, insured name, risk address, date of loss, peril, RCV, adjuster contacts, and more
2. **Checks for duplicates** by claim number and email ID
3. **Creates a Drive folder** structured as: `Insurance Claims / Carrier / YYYY-MM / ClaimNum - Insured Name` (with Photos, Documents, Estimates sub-folders)
4. **Saves the assignment email** as a text file inside the Drive folder
5. **Calculates mileage** from `26 Hanapepe Pl, Honolulu, HI 96825` to the risk address (one-way, round-trip, estimated drive time, IRS reimbursement)
6. **Downloads a route map PNG** and saves it to the claim folder
7. **Logs a formatted row** in your Claims Google Sheet with clickable links to the folder, Google Maps directions, and the route map

All of this runs automatically every 15 minutes in the background — no manual action required.

---

## Files in This Package

| File | Purpose |
|------|---------|
| `GAS/1_Config.gs` | All settings — fill in your API keys here |
| `GAS/2_Utils.gs` | Shared utility functions |
| `GAS/3_EmailParser.gs` | Claude AI email parsing logic |
| `GAS/4_SheetManager.gs` | Google Sheets read/write operations |
| `GAS/5_DriveManager.gs` | Drive folder creation and file saving |
| `GAS/6_MapsManager.gs` | Mileage calculation and route map download |
| `GAS/7_Main.gs` | Main orchestration — what runs on the trigger |
| `GAS/8_Setup.gs` | One-time setup functions + spreadsheet menu |
| `GAS/appsscript.json` | Apps Script manifest (timezone, services) |

---

## Prerequisites

Before setup, you need:

- [x] A **Google account** with Gmail and Google Drive
- [ ] An **Anthropic API key** (Claude) — free trial credits included
- [ ] A **Google Maps API key** — ~$0.005/request, low volume = essentially free
- [ ] A new **Google Sheet** created for your claims

---

## Setup Guide

### Step A — Get Your Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up / log in
3. Click **API Keys** in the left sidebar
4. Click **Create Key** → copy the key (starts with `sk-ant-...`)
5. Save it — you can't see it again

---

### Step B — Get Your Google Maps API Key

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing) → name it "Claims Automation"
3. Click **APIs & Services** → **Enable APIs and Services**
4. Search for and **Enable** each of these three APIs:
   - `Directions API`
   - `Distance Matrix API`
   - `Maps Static API`
5. Go to **APIs & Services** → **Credentials**
6. Click **Create Credentials** → **API Key**
7. Copy the key → click **Edit** → restrict it to the 3 APIs above

---

### Step C — Create Google Drive Folder

1. Go to [drive.google.com](https://drive.google.com)
2. Click **New** → **New Folder** → name it `Insurance Claims`
3. Open the folder → look at the URL bar:
   `https://drive.google.com/drive/folders/`**`THIS_IS_YOUR_FOLDER_ID`**
4. Copy the folder ID (everything after `/folders/`)

---

### Step D — Create the Google Sheet

1. Go to [sheets.google.com](https://sheets.google.com)
2. Click **Blank spreadsheet**
3. Name it `Insurance Claims Log`
4. Leave it open — you'll attach the script to it next

---

### Step E — Set Up Google Apps Script

1. In your Claims sheet, click **Extensions** → **Apps Script**
2. A new tab opens with a blank `Code.gs` file
3. **Delete all the default code** in `Code.gs`

Now create each file:

**For each `.gs` file in the `GAS/` folder:**

1. In the Apps Script editor, click the **+** button next to "Files"
2. Choose **Script**
3. Name it exactly as shown (e.g., `1_Config`, `2_Utils`, etc.) — no `.gs` extension needed
4. **Paste the entire contents** of that file
5. Repeat for all 8 files

> **Note:** `appsscript.json` is the manifest. To edit it:
> Click the gear icon ⚙️ (Project Settings) → check **"Show appsscript.json manifest file in editor"** → replace its content with the `appsscript.json` contents from this package.

---

### Step F — Fill In Your API Keys

Open `1_Config.gs` in the editor and update these four values:

```javascript
ROOT_FOLDER_ID: 'paste-your-drive-folder-id-here',
CLAUDE_API_KEY: 'sk-ant-your-key-here',
MAPS_API_KEY:   'your-google-maps-api-key-here',
```

> Your home address is pre-filled as `26 Hanapepe Pl, Honolulu, HI 96825`.
> Update `MILEAGE_RATE` each January with the new IRS rate.

---

### Step G — Enable the Maps Advanced Service

1. In the Apps Script editor, click **Services** (+ icon next to Services in left sidebar)
2. Scroll to find **Maps JavaScript API** or **Google Maps Service**
3. Select it and click **Add**

---

### Step H — Run Setup Functions

In the Apps Script editor, use the dropdown to select and run each function:

1. **Select** `setupClaimsSheet` → click **Run ▶**
   - Authorize the script when prompted (click "Allow" for all permissions)
   - This creates your Claims sheet headers and formatting

2. **Select** `setupGmailLabels` → click **Run ▶**
   - Creates `Claims/Processed`, `Claims/Error`, `Claims/Pending` labels in Gmail

3. **Select** `testClaudeAPI` → click **Run ▶**
   - Should show a popup with parsed claim data — confirms Claude is working

4. **Select** `testMileageCalculation` → click **Run ▶**
   - Should show miles and reimbursement — confirms Maps API is working

5. **Select** `setupTimeTrigger` → click **Run ▶**
   - Activates automatic 15-minute scanning

---

### Step I — Test With a Real Email

Send yourself a test claim assignment email (or forward a real one), wait up to 15 minutes, and check your Claims sheet for the new row.

Alternatively, select `manualScanNow` → **Run ▶** to trigger an immediate scan.

---

## Your Claims Sheet — Column Layout

| Col | Field | Source |
|-----|-------|--------|
| A | Date Received | Gmail timestamp |
| B | Claim Number | Claude AI |
| C | Carrier | Claude AI |
| D | Insured Name | Claude AI |
| E | Risk Address | Claude AI |
| F | City | Claude AI |
| G | State | Claude AI |
| H | Zip | Claude AI |
| I | Date of Loss | Claude AI |
| J | Peril | Claude AI |
| K | Claim Type | Claude AI |
| L | RCV ($) | Claude AI |
| M | Policy Number | Claude AI |
| N | Carrier Adj. Name | Claude AI |
| O | Carrier Adj. Phone | Claude AI |
| P | Carrier Adj. Email | Claude AI |
| Q | Insured Phone | Claude AI |
| R | Insured Email | Claude AI |
| S | Inspection Deadline | Claude AI |
| T | Miles (One-Way) | Google Maps |
| U | Miles (Round-Trip) | Google Maps |
| V | Drive Time | Google Maps |
| W | Mileage Reimb. ($) | Calculated |
| X | Claim Folder | Drive link |
| Y | Google Maps | Directions link |
| Z | Route Map | PNG in Drive |
| AA | Contact Status | Manual (dropdown) |
| AB | Notes | Claude AI |
| AC | Email ID | Gmail |
| AD | Duplicate? | Auto-detected |

---

## Drive Folder Structure

```
Insurance Claims/
  Liberty Mutual/
    2026-02/
      LM-2026-123456 - John Smith/
        Photos/
        Documents/
          Assignment Email - New Claim Assignment.txt
        Estimates/
        Mileage Map.png
  USAA/
    2026-02/
      ...
```

---

## Custom Menu in Your Sheet

After setup, a **"Claims Automation"** menu appears in your spreadsheet:

- **Scan Gmail for New Claims Now** — immediate scan (no waiting for timer)
- **Setup** submenu — re-run any setup step
- **Test** submenu — verify Claude and Maps are working

---

## Tuning the Email Search

The system searches Gmail using the query in `CONFIG.EMAIL_SEARCH`. If you're missing emails from certain carriers, add their subject-line patterns to the search query. Examples:

```javascript
'OR subject:"your assignment"',
'OR subject:"field inspection assignment"',
'OR (subject:"claim" from:libertymutual.com)',
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Emails not being found | Check `CONFIG.EMAIL_SEARCH` matches carrier subject lines. Test by searching Gmail manually. |
| "Claude API error 401" | API key is wrong or expired. Re-check `CONFIG.CLAUDE_API_KEY`. |
| "Claude API error 400" | Prompt too long. Body is auto-truncated at 4,500 chars — this is rare. |
| Mileage shows "No result" | Confirm `CONFIG.MAPS_API_KEY` is correct. Check all 3 APIs are enabled in Cloud Console. |
| Map PNG not saving | Confirm `ROOT_FOLDER_ID` is correct and the script has Drive access. |
| Sheet not updating | Re-run `setupClaimsSheet`. Check Activity Log tab for errors. |
| "Drive folder not created" | Verify `ROOT_FOLDER_ID` in Config.gs. Ensure the folder exists and isn't trashed. |
| Email parsed as "not a claim" | Check email format. You can forward it to yourself and trigger `manualScanNow`. Claude may need the subject line adjusted. |

---

## Costs Estimate (Low Volume — Under 10 Claims/Week)

| Service | Cost |
|---------|------|
| Anthropic Claude (Opus 4.6) | ~$0.015 per email parsed |
| Google Maps Directions API | $0.005 per request |
| Google Maps Static Maps API | $0.002 per image |
| **Estimated per claim** | **~$0.025** |
| **Monthly (10 claims/week)** | **~$1.00** |

---

## What's Coming in Phase 2

- Automated SMS/call outreach to insured at assignment (Twilio)
- Auto-log contact attempts with timestamps (Hawaii DOI compliance)
- Xactanalysis status update automation
- Confirmation text to insured with adjuster info and inspection window

---

*Built for: Licensed IA — Hawaii, Florida, and CAT deployments*
*Carriers: Liberty Mutual, USAA, Allstate, American Modern*
*Platform: Google Apps Script + Claude AI + Google Maps*
