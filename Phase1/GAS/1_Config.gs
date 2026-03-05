// ================================================================
// 1_Config.gs  —  Insurance Claim Automation  (Phase 1)
// ================================================================
// UPDATE every value marked  TODO  before running any function.
// This file is the single source of truth for all settings.
// ================================================================

var CONFIG = {

  // ── YOUR HOME ADDRESS (mileage origin) ─────────────────────
  HOME_ADDRESS: '26 Hanapepe Pl, Honolulu, HI 96825',

  // ── GOOGLE SHEET ────────────────────────────────────────────
  // Run this script BOUND to your Claims spreadsheet:
  //   Open the sheet → Extensions → Apps Script → paste code there.
  // If you run it as a standalone project, paste the Sheet ID below.
  SHEET_ID: '',                      // leave blank for bound script
  CLAIMS_TAB:  'Claims',
  LOG_TAB:     'Activity Log',

  // ── GOOGLE DRIVE ROOT FOLDER ─────────────────────────────────
  // TODO: In Google Drive create a folder called "Insurance Claims".
  //       Open it → copy the ID from the URL bar (the long string
  //       after /folders/) and paste it below.
  ROOT_FOLDER_ID: 'YOUR_DRIVE_FOLDER_ID_HERE',

  // ── ANTHROPIC CLAUDE API KEY ─────────────────────────────────
  // TODO: https://console.anthropic.com  → API Keys → Create key
  CLAUDE_API_KEY: 'YOUR_ANTHROPIC_API_KEY_HERE',

  // ── GOOGLE MAPS API KEY ──────────────────────────────────────
  // TODO: https://console.cloud.google.com → APIs & Services
  //   Enable: Directions API, Distance Matrix API, Maps Static API
  //   Create credentials → API Key → paste below
  MAPS_API_KEY: 'YOUR_GOOGLE_MAPS_API_KEY_HERE',

  // ── IRS STANDARD MILEAGE RATE ────────────────────────────────
  // Update each January (2025 & 2026 = $0.70/mile)
  MILEAGE_RATE: 0.70,

  // ── HOW OFTEN TO CHECK GMAIL (minutes) ───────────────────────
  TRIGGER_INTERVAL_MINUTES: 15,

  // ── GMAIL LABELS ─────────────────────────────────────────────
  LABEL_PROCESSED: 'Claims/Processed',
  LABEL_ERROR:     'Claims/Error',
  LABEL_PENDING:   'Claims/Pending',

  // ── GMAIL SEARCH QUERY ───────────────────────────────────────
  // Finds unprocessed emails that look like claim assignments.
  // Tune these keywords if carriers use different subject lines.
  EMAIL_SEARCH: [
    '(',
    'subject:"claim assignment"',
    'OR subject:"new assignment"',
    'OR subject:"new claim"',
    'OR (subject:"assignment" "date of loss")',
    'OR (subject:"claim" "risk address")',
    'OR (subject:"claim" "insured:")',
    'OR (subject:"claim" "date of loss")',
    ')',
    '-label:Claims/Processed',
    '-label:Claims/Error',
  ].join(' '),

  // ── SHEET COLUMN POSITIONS (1-based) ─────────────────────────
  COL: {
    DATE_RECEIVED:   1,  // A  — timestamp email received
    CLAIM_NUMBER:    2,  // B
    CARRIER:         3,  // C
    INSURED_NAME:    4,  // D
    RISK_ADDRESS:    5,  // E  — street only
    CITY:            6,  // F
    STATE:           7,  // G
    ZIP:             8,  // H
    DATE_OF_LOSS:    9,  // I
    PERIL:          10,  // J  — cause of loss
    CLAIM_TYPE:     11,  // K  — Residential / Commercial
    RCV:            12,  // L  — Replacement Cost Value
    POLICY_NUMBER:  13,  // M
    CARR_ADJ_NAME:  14,  // N  — carrier/desk adjuster
    CARR_ADJ_PHONE: 15,  // O
    CARR_ADJ_EMAIL: 16,  // P
    INSURED_PHONE:  17,  // Q
    INSURED_EMAIL:  18,  // R
    INSPECTION_DL:  19,  // S  — inspection deadline
    MILES_OW:       20,  // T  — one-way miles
    MILES_RT:       21,  // U  — round-trip miles
    DRIVE_TIME:     22,  // V  — estimated drive time
    MILEAGE_REIMB:  23,  // W  — reimbursement $ (round-trip)
    FOLDER_LINK:    24,  // X  — Drive folder hyperlink
    MAP_LINK:       25,  // Y  — Google Maps directions URL
    MAP_FILE_LINK:  26,  // Z  — Route map PNG saved to Drive
    CONTACT_STATUS: 27,  // AA — New / Contacted / Scheduled
    NOTES:          28,  // AB
    EMAIL_ID:       29,  // AC — Gmail message ID (dedup key)
    IS_DUPLICATE:   30,  // AD — "DUPLICATE" if claim # seen before
  },

  // ── COLUMN HEADERS (must stay in exact same order as COL) ───
  HEADERS: [
    'Date Received',       // 1
    'Claim Number',        // 2
    'Carrier',             // 3
    'Insured Name',        // 4
    'Risk Address',        // 5
    'City',                // 6
    'State',               // 7
    'Zip',                 // 8
    'Date of Loss',        // 9
    'Peril',               // 10
    'Claim Type',          // 11
    'RCV ($)',             // 12
    'Policy Number',       // 13
    'Carrier Adj. Name',   // 14
    'Carrier Adj. Phone',  // 15
    'Carrier Adj. Email',  // 16
    'Insured Phone',       // 17
    'Insured Email',       // 18
    'Inspection Deadline', // 19
    'Miles (One-Way)',     // 20
    'Miles (Round-Trip)',  // 21
    'Drive Time',          // 22
    'Mileage Reimb. ($)',  // 23
    'Claim Folder',        // 24
    'Google Maps',         // 25
    'Route Map',           // 26
    'Contact Status',      // 27
    'Notes',               // 28
    'Email ID',            // 29
    'Duplicate?',          // 30
  ],

};
