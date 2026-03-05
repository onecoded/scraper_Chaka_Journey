// ================================================================
// 4_SheetManager.gs  —  Google Sheets read / write operations
// ================================================================

/**
 * Returns the Claims sheet, creating it with headers if it doesn't exist.
 */
function getOrCreateClaimsSheet() {
  var ss = getSpreadsheet();
  var sheet = ss.getSheetByName(CONFIG.CLAIMS_TAB);
  if (!sheet) {
    sheet = ss.insertSheet(CONFIG.CLAIMS_TAB, 0);
    log('Created Claims sheet');
  }
  // Initialise headers if the sheet is empty or the first cell is wrong
  if (sheet.getLastRow() === 0 ||
      sheet.getRange(1, 1).getValue() !== CONFIG.HEADERS[0]) {
    initHeaders(sheet);
  }
  return sheet;
}

/**
 * Writes and formats the header row.
 */
function initHeaders(sheet) {
  var headerRange = sheet.getRange(1, 1, 1, CONFIG.HEADERS.length);
  headerRange.setValues([CONFIG.HEADERS]);
  headerRange
    .setBackground('#1a5276')
    .setFontColor('#ffffff')
    .setFontWeight('bold')
    .setFontSize(10)
    .setWrap(false);

  sheet.setFrozenRows(1);

  // Set useful column widths
  var widths = {
    1:  130,  // Date Received
    2:  155,  // Claim Number
    3:  135,  // Carrier
    4:  160,  // Insured Name
    5:  220,  // Risk Address
    6:  120,  // City
    7:   60,  // State
    8:   70,  // Zip
    9:  110,  // Date of Loss
    10: 140,  // Peril
    11: 120,  // Claim Type
    12: 100,  // RCV
    13: 130,  // Policy Number
    14: 160,  // Carrier Adj Name
    15: 140,  // Carrier Adj Phone
    16: 210,  // Carrier Adj Email
    17: 140,  // Insured Phone
    18: 200,  // Insured Email
    19: 140,  // Inspection Deadline
    20: 115,  // Miles OW
    21: 120,  // Miles RT
    22: 110,  // Drive Time
    23: 130,  // Mileage Reimb
    24: 110,  // Claim Folder
    25: 110,  // Google Maps
    26: 100,  // Route Map
    27: 120,  // Contact Status
    28: 260,  // Notes
    29: 160,  // Email ID
    30: 100,  // Duplicate?
  };
  for (var col in widths) {
    sheet.setColumnWidth(Number(col), widths[col]);
  }

  log('Initialised Claims sheet headers');
}

// ----------------------------------------------------------------
// Duplicate detection
// ----------------------------------------------------------------

/**
 * Returns true if the claim number or email ID already exists in the sheet.
 */
function isDuplicate(claimNumber, emailId) {
  var sheet = getOrCreateClaimsSheet();
  if (sheet.getLastRow() <= 1) return false; // headers only

  var c = CONFIG.COL;
  var lastDataRow = sheet.getLastRow() - 1;

  // Check by Gmail message ID (fastest / most reliable)
  if (emailId) {
    var emailIds = sheet.getRange(2, c.EMAIL_ID, lastDataRow, 1).getValues();
    for (var i = 0; i < emailIds.length; i++) {
      if (emailIds[i][0] === emailId) {
        log('Duplicate email ID: ' + emailId, 'WARN');
        return true;
      }
    }
  }

  // Check by claim number
  if (claimNumber) {
    var claimNums = sheet.getRange(2, c.CLAIM_NUMBER, lastDataRow, 1).getValues();
    for (var j = 0; j < claimNums.length; j++) {
      if (claimNums[j][0] &&
          String(claimNums[j][0]).trim().toLowerCase() ===
          String(claimNumber).trim().toLowerCase()) {
        log('Duplicate claim number: ' + claimNumber, 'WARN');
        return true;
      }
    }
  }

  return false;
}

// ----------------------------------------------------------------
// Row insertion
// ----------------------------------------------------------------

/**
 * Appends a new claim row to the sheet.
 * claimData   — parsed fields from EmailParser
 * mileageData — distance/time object from MapsManager (or null)
 * folderUrl   — Drive folder URL (or null)
 * mapsUrl     — Google Maps directions URL (or null)
 * mapFileUrl  — Drive URL of the saved route-map PNG (or null)
 *
 * Returns the row number that was written.
 */
function addClaimRow(claimData, mileageData, folderUrl, mapsUrl, mapFileUrl) {
  var sheet = getOrCreateClaimsSheet();
  var c = CONFIG.COL;
  var totalCols = CONFIG.HEADERS.length;

  // Build a flat array of 30 values (blank for columns we'll set as formulas)
  var row = new Array(totalCols).fill('');

  row[c.DATE_RECEIVED   - 1] = claimData.receivedAt || new Date();
  row[c.CLAIM_NUMBER    - 1] = claimData.claimNumber    || '';
  row[c.CARRIER         - 1] = claimData.carrier         || '';
  row[c.INSURED_NAME    - 1] = claimData.insuredName     || '';
  row[c.RISK_ADDRESS    - 1] = claimData.riskStreet      || claimData.riskAddress || '';
  row[c.CITY            - 1] = claimData.riskCity        || '';
  row[c.STATE           - 1] = claimData.riskState       || '';
  row[c.ZIP             - 1] = claimData.riskZip         || '';
  row[c.DATE_OF_LOSS    - 1] = claimData.dateOfLoss      || '';
  row[c.PERIL           - 1] = claimData.peril           || '';
  row[c.CLAIM_TYPE      - 1] = claimData.claimType       || '';
  row[c.RCV             - 1] = claimData.rcv             ? Number(claimData.rcv) : '';
  row[c.POLICY_NUMBER   - 1] = claimData.policyNumber    || '';
  row[c.CARR_ADJ_NAME   - 1] = claimData.carrierAdjName  || '';
  row[c.CARR_ADJ_PHONE  - 1] = claimData.carrierAdjPhone || '';
  row[c.CARR_ADJ_EMAIL  - 1] = claimData.carrierAdjEmail || '';
  row[c.INSURED_PHONE   - 1] = claimData.insuredPhone    || '';
  row[c.INSURED_EMAIL   - 1] = claimData.insuredEmail    || '';
  row[c.INSPECTION_DL   - 1] = claimData.inspectionDeadline || '';
  row[c.CONTACT_STATUS  - 1] = 'New';
  row[c.NOTES           - 1] = claimData.notes           || '';
  row[c.EMAIL_ID        - 1] = claimData.emailId         || '';
  row[c.IS_DUPLICATE    - 1] = claimData.isDuplicate     ? 'DUPLICATE' : '';

  if (mileageData) {
    row[c.MILES_OW      - 1] = mileageData.milesOneWay    || '';
    row[c.MILES_RT      - 1] = mileageData.milesRoundTrip || '';
    row[c.DRIVE_TIME    - 1] = mileageData.driveTime       || '';
    row[c.MILEAGE_REIMB - 1] = mileageData.reimbursement  || '';
  }

  // Write all values at once
  var newRow = sheet.getLastRow() + 1;
  sheet.getRange(newRow, 1, 1, totalCols).setValues([row]);

  // Set hyperlink formulas for the three URL columns
  if (folderUrl) {
    sheet.getRange(newRow, c.FOLDER_LINK)
      .setFormula('=HYPERLINK("' + folderUrl + '","Open Folder")');
  }
  if (mapsUrl) {
    sheet.getRange(newRow, c.MAP_LINK)
      .setFormula('=HYPERLINK("' + mapsUrl + '","View Map")');
  }
  if (mapFileUrl) {
    sheet.getRange(newRow, c.MAP_FILE_LINK)
      .setFormula('=HYPERLINK("' + mapFileUrl + '","Route Map")');
  }

  // Row formatting
  var rowRange = sheet.getRange(newRow, 1, 1, totalCols);
  rowRange.setBackground(newRow % 2 === 0 ? '#eaf4fb' : '#ffffff');

  if (claimData.isDuplicate) {
    rowRange.setBackground('#fde8e8');
    sheet.getRange(newRow, c.IS_DUPLICATE)
      .setFontColor('#c0392b')
      .setFontWeight('bold');
  }

  // Date format for Date Received
  sheet.getRange(newRow, c.DATE_RECEIVED)
    .setNumberFormat('MM/dd/yyyy h:mm am/pm');

  // Currency format
  if (claimData.rcv) {
    sheet.getRange(newRow, c.RCV).setNumberFormat('$#,##0');
  }
  if (mileageData && mileageData.reimbursement) {
    sheet.getRange(newRow, c.MILEAGE_REIMB).setNumberFormat('$#,##0.00');
  }

  return newRow;
}
