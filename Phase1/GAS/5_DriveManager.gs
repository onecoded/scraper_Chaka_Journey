// ================================================================
// 5_DriveManager.gs  —  Google Drive folder and file management
// ================================================================

/**
 * Creates the claim folder hierarchy and returns IDs / URLs.
 *
 * Structure:
 *   Insurance Claims/
 *     {Carrier}/
 *       {YYYY-MM}/            ← based on date of loss
 *         {ClaimNumber} - {InsuredName}/
 *           Photos/
 *           Documents/
 *           Estimates/
 *
 * Returns { folderId, folderUrl } — both null if creation fails or
 * ROOT_FOLDER_ID is not configured.
 */
function createClaimFolder(carrier, dateOfLoss, claimNumber, insuredName) {
  if (!CONFIG.ROOT_FOLDER_ID || CONFIG.ROOT_FOLDER_ID.indexOf('YOUR_') === 0) {
    log('ROOT_FOLDER_ID not configured — skipping Drive folder creation', 'WARN');
    return { folderId: null, folderUrl: null };
  }

  try {
    var rootFolder = DriveApp.getFolderById(CONFIG.ROOT_FOLDER_ID);

    // Level 1: Carrier
    var carrierName = sanitize(carrier || 'Unknown Carrier', 50);
    var carrierFolder = getOrCreateSubfolder(rootFolder, carrierName);

    // Level 2: Year-Month (from date of loss, fallback to today)
    var refDate;
    try {
      refDate = dateOfLoss ? new Date(dateOfLoss) : new Date();
      if (isNaN(refDate.getTime())) refDate = new Date();
    } catch (e) {
      refDate = new Date();
    }
    var monthName = Utilities.formatDate(refDate, Session.getScriptTimeZone(), 'yyyy-MM');
    var monthFolder = getOrCreateSubfolder(carrierFolder, monthName);

    // Level 3: Claim folder
    var parts = [];
    if (claimNumber) parts.push(claimNumber);
    if (insuredName)  parts.push(insuredName);
    var claimFolderName = sanitize(parts.length ? parts.join(' - ') : 'Unknown Claim', 80);
    var claimFolder = getOrCreateSubfolder(monthFolder, claimFolderName);

    // Sub-folders inside the claim folder
    getOrCreateSubfolder(claimFolder, 'Photos');
    getOrCreateSubfolder(claimFolder, 'Documents');
    getOrCreateSubfolder(claimFolder, 'Estimates');

    log('Created claim folder: ' + carrierName + '/' + monthName + '/' + claimFolderName);

    return {
      folderId: claimFolder.getId(),
      folderUrl: claimFolder.getUrl(),
    };

  } catch (e) {
    log('Error creating Drive folder: ' + e.message, 'ERROR');
    return { folderId: null, folderUrl: null };
  }
}

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

/**
 * Returns an existing subfolder by name, or creates it.
 */
function getOrCreateSubfolder(parentFolder, name) {
  var iter = parentFolder.getFoldersByName(name);
  if (iter.hasNext()) return iter.next();
  return parentFolder.createFolder(name);
}

/**
 * Saves a file to a Drive folder.
 * content can be a byte array (for images) or a string (for text).
 * Returns the file's URL, or null on failure.
 */
function saveFileToDrive(folderId, filename, content, mimeType) {
  try {
    var folder = DriveApp.getFolderById(folderId);
    var blob   = Utilities.newBlob(content, mimeType, filename);
    var file   = folder.createFile(blob);
    return file.getUrl();
  } catch (e) {
    log('Error saving file to Drive (' + filename + '): ' + e.message, 'ERROR');
    return null;
  }
}

/**
 * Saves the original assignment email as a plain-text file
 * inside the claim's Documents sub-folder.
 */
function saveEmailToFolder(folderId, subject, body, receivedAt) {
  try {
    var docsFolder = getOrCreateSubfolder(
      DriveApp.getFolderById(folderId), 'Documents'
    );
    var filename = sanitize('Assignment Email - ' + subject, 100) + '.txt';
    var content  = 'CLAIM ASSIGNMENT EMAIL\n' +
                   '='.repeat(60) + '\n' +
                   'Received : ' + receivedAt + '\n' +
                   'Subject  : ' + subject   + '\n' +
                   '='.repeat(60) + '\n\n' +
                   (body || '(no body)');
    var blob = Utilities.newBlob(content, 'text/plain', filename);
    docsFolder.createFile(blob);
    log('Saved assignment email to Drive');
  } catch (e) {
    log('Error saving email to Drive: ' + e.message, 'ERROR');
  }
}
