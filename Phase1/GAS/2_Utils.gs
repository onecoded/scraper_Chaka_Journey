// ================================================================
// 2_Utils.gs  —  Shared utility functions
// ================================================================

/**
 * Returns the active spreadsheet (handles bound vs. standalone).
 */
function getSpreadsheet() {
  if (CONFIG.SHEET_ID) {
    return SpreadsheetApp.openById(CONFIG.SHEET_ID);
  }
  return SpreadsheetApp.getActiveSpreadsheet();
}

/**
 * Writes one line to the Activity Log sheet AND to Logger.
 * level: 'INFO' | 'WARN' | 'ERROR'
 */
function log(message, level, details) {
  level = level || 'INFO';
  var fullMsg = '[' + level + '] ' + message + (details ? ' | ' + JSON.stringify(details) : '');
  Logger.log(fullMsg);

  try {
    var ss = getSpreadsheet();
    var logSheet = ss.getSheetByName(CONFIG.LOG_TAB);
    if (!logSheet) {
      logSheet = ss.insertSheet(CONFIG.LOG_TAB);
      logSheet.appendRow(['Timestamp', 'Level', 'Message', 'Details']);
      logSheet.getRange(1, 1, 1, 4).setFontWeight('bold').setBackground('#2c3e50').setFontColor('#ffffff');
    }
    logSheet.appendRow([new Date(), level, message, details ? JSON.stringify(details) : '']);
  } catch (e) {
    Logger.log('Could not write to log sheet: ' + e);
  }
}

/**
 * Gets or creates a Gmail label, including any parent labels needed.
 */
function getOrCreateLabel(labelName) {
  var label = GmailApp.getUserLabelByName(labelName);
  if (label) return label;

  // Create parent labels first if needed
  var parts = labelName.split('/');
  var current = '';
  for (var i = 0; i < parts.length; i++) {
    current = current ? current + '/' + parts[i] : parts[i];
    if (!GmailApp.getUserLabelByName(current)) {
      GmailApp.createLabel(current);
    }
  }
  return GmailApp.getUserLabelByName(labelName);
}

/**
 * Removes characters that are illegal in Drive file/folder names.
 * maxLen defaults to 80.
 */
function sanitize(str, maxLen) {
  if (!str) return 'Unknown';
  maxLen = maxLen || 80;
  return String(str)
    .replace(/[\\/:*?"<>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .substring(0, maxLen);
}

/**
 * Normalises a US phone number to (XXX) XXX-XXXX format.
 */
function normalizePhone(phone) {
  if (!phone) return '';
  var digits = String(phone).replace(/\D/g, '');
  if (digits.length === 10) {
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  }
  if (digits.length === 11 && digits[0] === '1') {
    return '(' + digits.slice(1, 4) + ') ' + digits.slice(4, 7) + '-' + digits.slice(7);
  }
  return phone; // return as-is if unrecognised format
}

/**
 * Case-insensitive check: does text contain any of the given keywords?
 */
function hasKeyword(text, keywords) {
  if (!text || !keywords || !keywords.length) return false;
  var lower = String(text).toLowerCase();
  return keywords.some(function(k) { return lower.indexOf(k.toLowerCase()) !== -1; });
}

/**
 * Sends a brief error alert email to yourself.
 */
function notifyError(context, errorMessage) {
  try {
    GmailApp.sendEmail(
      Session.getEffectiveUser().getEmail(),
      'Claim Automation Error — ' + context,
      'Your claim automation encountered an error.\n\n' +
      'Context: ' + context + '\n' +
      'Error:   ' + errorMessage + '\n\n' +
      'Check the Activity Log tab in your Claims sheet for full details.\n' +
      'Time: ' + new Date().toLocaleString()
    );
  } catch (e) {
    log('Could not send error notification: ' + e.message, 'WARN');
  }
}
