// ================================================================
// 8_Setup.gs  —  One-time setup, test functions, and custom menu
// ================================================================
// Run each function ONCE via Apps Script editor  Run ▶  button.
// The custom menu also appears in your spreadsheet after first load.
// ================================================================

// ----------------------------------------------------------------
// Setup functions  (run in order the first time)
// ----------------------------------------------------------------

/** STEP 1 — Creates and formats the Claims sheet and Activity Log. */
function setupClaimsSheet() {
  try {
    var sheet = getOrCreateClaimsSheet();
    initHeaders(sheet);

    // ── Conditional formatting ────────────────────────────────

    var ss    = getSpreadsheet();
    var rules = sheet.getConditionalFormatRules();
    var dataRows = sheet.getRange(2, 1, 1000, CONFIG.HEADERS.length);

    // Duplicate rows → light red background
    rules.push(
      SpreadsheetApp.newConditionalFormatRule()
        .whenFormula('=$AD2="DUPLICATE"')
        .setBackground('#fde8e8')
        .setRanges([dataRows])
        .build()
    );

    // Contact Status = "New"        → pale yellow
    rules.push(
      SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo('New')
        .setBackground('#fef9e7')
        .setRanges([sheet.getRange(2, CONFIG.COL.CONTACT_STATUS, 1000, 1)])
        .build()
    );

    // Contact Status = "Contacted"  → light green
    rules.push(
      SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo('Contacted')
        .setBackground('#eafaf1')
        .setRanges([sheet.getRange(2, CONFIG.COL.CONTACT_STATUS, 1000, 1)])
        .build()
    );

    // Contact Status = "Scheduled"  → light blue
    rules.push(
      SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo('Scheduled')
        .setBackground('#ebf5fb')
        .setRanges([sheet.getRange(2, CONFIG.COL.CONTACT_STATUS, 1000, 1)])
        .build()
    );

    sheet.setConditionalFormatRules(rules);

    // ── Data validation for Contact Status ───────────────────
    var statusRule = SpreadsheetApp.newDataValidation()
      .requireValueInList(['New', 'Contacted', 'Scheduled', 'Inspected', 'Closed'], true)
      .build();
    sheet.getRange(2, CONFIG.COL.CONTACT_STATUS, 1000, 1).setDataValidation(statusRule);

    SpreadsheetApp.getUi().alert('Step 1 complete — Claims sheet is ready.');
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error in setupClaimsSheet:\n' + e.message);
  }
}

/** STEP 2 — Creates the Gmail labels the script uses. */
function setupGmailLabels() {
  try {
    getOrCreateLabel(CONFIG.LABEL_PROCESSED);
    getOrCreateLabel(CONFIG.LABEL_ERROR);
    getOrCreateLabel(CONFIG.LABEL_PENDING);
    SpreadsheetApp.getUi().alert(
      'Step 2 complete — Gmail labels created:\n' +
      '  • ' + CONFIG.LABEL_PROCESSED + '\n' +
      '  • ' + CONFIG.LABEL_ERROR     + '\n' +
      '  • ' + CONFIG.LABEL_PENDING
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error creating Gmail labels:\n' + e.message);
  }
}

/**
 * STEP 3 — Creates a time-based trigger that fires every 15 minutes.
 * Safe to re-run: removes old triggers for the same function first.
 */
function setupTimeTrigger() {
  try {
    // Remove any existing triggers for processNewClaimEmails
    var existing = ScriptApp.getProjectTriggers();
    for (var i = 0; i < existing.length; i++) {
      if (existing[i].getHandlerFunction() === 'processNewClaimEmails') {
        ScriptApp.deleteTrigger(existing[i]);
      }
    }

    // Create new trigger
    ScriptApp.newTrigger('processNewClaimEmails')
      .timeBased()
      .everyMinutes(CONFIG.TRIGGER_INTERVAL_MINUTES)
      .create();

    SpreadsheetApp.getUi().alert(
      'Step 3 complete — Auto-trigger set!\n\n' +
      'The system will check Gmail for new claim emails every ' +
      CONFIG.TRIGGER_INTERVAL_MINUTES + ' minutes.'
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error setting trigger:\n' + e.message);
  }
}

/** Runs all three setup steps in sequence. */
function runFullSetup() {
  setupClaimsSheet();
  setupGmailLabels();
  SpreadsheetApp.getUi().alert(
    'Full setup complete!\n\n' +
    'Remaining steps:\n' +
    '1. Fill in API keys in 1_Config.gs\n' +
    '2. Set ROOT_FOLDER_ID in 1_Config.gs\n' +
    '3. Run  Test: Claude API  to verify AI parsing\n' +
    '4. Run  Test: Mileage  to verify distance calc\n' +
    '5. Run  Activate Auto-Trigger  to go live'
  );
}

// ----------------------------------------------------------------
// Test functions
// ----------------------------------------------------------------

/** Tests the Claude API with a realistic fake claim email. */
function testClaudeAPI() {
  try {
    var result = parseClaimEmail(
      'New Claim Assignment — Claim #LM-2026-123456 — Smith',
      'CLAIM ASSIGNMENT NOTIFICATION\n\n' +
      'Insured      : John & Mary Smith\n' +
      'Claim Number : LM-2026-123456\n' +
      'Policy Number: HO-98765432\n' +
      'Carrier      : Liberty Mutual\n' +
      'Date of Loss : 02/10/2026\n' +
      'Cause of Loss: Wind / Hurricane\n' +
      'Risk Address : 456 Kaimana St, Honolulu, HI 96815\n' +
      'RCV          : $185,000\n\n' +
      'Desk Adjuster: Sarah Jones\n' +
      'Phone        : (800) 555-0199\n' +
      'Email        : sjones@libertymutual.com\n\n' +
      'Insured Phone: (808) 555-4321\n' +
      'Please contact insured within 24 hours.\n' +
      'Inspection deadline: 02/17/2026',
      'Liberty Mutual Claims',
      'assignments@libertymutual.com'
    );

    if (result) {
      SpreadsheetApp.getUi().alert(
        'Claude API — PASS\n\n' +
        'Claim #  : ' + result.claimNumber  + '\n' +
        'Carrier  : ' + result.carrier      + '\n' +
        'Insured  : ' + result.insuredName  + '\n' +
        'Address  : ' + result.riskAddress  + '\n' +
        'DOL      : ' + result.dateOfLoss   + '\n' +
        'Peril    : ' + result.peril        + '\n' +
        'RCV      : $' + result.rcv
      );
    } else {
      SpreadsheetApp.getUi().alert('Claude responded but flagged it as NOT a claim email.\nCheck your prompt in 3_EmailParser.gs.');
    }
  } catch (e) {
    SpreadsheetApp.getUi().alert('Claude API — FAIL\n\n' + e.message);
  }
}

/** Tests mileage calculation from home to a Honolulu address. */
function testMileageCalculation() {
  var testAddr = '456 Kaimana St, Honolulu, HI 96815';
  try {
    var result = getMileageInfo(testAddr);
    if (result) {
      SpreadsheetApp.getUi().alert(
        'Mileage Calculation — PASS\n\n' +
        'To      : ' + testAddr + '\n' +
        'One-way : ' + result.milesOneWay    + ' miles\n' +
        'RT      : ' + result.milesRoundTrip + ' miles\n' +
        'Time    : ' + result.driveTime      + '\n' +
        'Reimb.  : $' + result.reimbursement + ' (@ $' + CONFIG.MILEAGE_RATE + '/mi)'
      );
    } else {
      SpreadsheetApp.getUi().alert(
        'Mileage Calculation — No result returned.\n' +
        'Check MAPS_API_KEY or the Maps Advanced Service.'
      );
    }
  } catch (e) {
    SpreadsheetApp.getUi().alert('Mileage Calculation — FAIL\n\n' + e.message);
  }
}

/** Triggers one immediate scan without waiting for the timer. */
function manualScanNow() {
  processNewClaimEmails();
  SpreadsheetApp.getUi().alert(
    'Scan complete.\nCheck the Claims sheet and Activity Log tab for results.'
  );
}

// ----------------------------------------------------------------
// Custom spreadsheet menu  (auto-added when sheet is opened)
// ----------------------------------------------------------------

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Claims Automation')
    .addItem('Scan Gmail for New Claims Now', 'manualScanNow')
    .addSeparator()
    .addSubMenu(
      SpreadsheetApp.getUi().createMenu('Setup')
        .addItem('Run Full Setup (Steps 1-2)', 'runFullSetup')
        .addItem('Step 1 — Init Claims Sheet',  'setupClaimsSheet')
        .addItem('Step 2 — Create Gmail Labels', 'setupGmailLabels')
        .addItem('Step 3 — Activate Auto-Trigger', 'setupTimeTrigger')
    )
    .addSeparator()
    .addSubMenu(
      SpreadsheetApp.getUi().createMenu('Test')
        .addItem('Test: Claude AI Parsing',   'testClaudeAPI')
        .addItem('Test: Mileage Calculation', 'testMileageCalculation')
    )
    .addToUi();
}
