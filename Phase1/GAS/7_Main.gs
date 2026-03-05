// ================================================================
// 7_Main.gs  —  Orchestration: runs on time trigger every 15 min
// ================================================================

/**
 * PRIMARY TRIGGER FUNCTION
 * Called automatically by the time-based trigger every 15 minutes.
 * Searches Gmail, parses each claim email with Claude, then:
 *   • creates a Drive folder tree
 *   • saves the assignment email to Drive
 *   • calculates round-trip mileage
 *   • downloads a route-map PNG to Drive
 *   • appends a formatted row to the Claims sheet
 */
function processNewClaimEmails() {
  log('=== Claim email scan started ===');

  var processedLabel = getOrCreateLabel(CONFIG.LABEL_PROCESSED);
  var errorLabel     = getOrCreateLabel(CONFIG.LABEL_ERROR);

  // Search Gmail for unprocessed claim assignment emails
  var threads;
  try {
    threads = GmailApp.search(CONFIG.EMAIL_SEARCH, 0, 25);
  } catch (e) {
    log('Gmail search error: ' + e.message, 'ERROR');
    return;
  }

  if (!threads || threads.length === 0) {
    log('No new claim emails found');
    return;
  }

  log('Found ' + threads.length + ' thread(s) to review');

  var counts = { processed: 0, skipped: 0, errors: 0 };

  for (var t = 0; t < threads.length; t++) {
    var thread   = threads[t];
    var messages = thread.getMessages();
    // Use the most recent message in the thread
    var message  = messages[messages.length - 1];

    try {
      var result = processSingleMessage(message);

      if (result === 'processed' || result === 'not_claim' || result === 'duplicate') {
        thread.addLabel(processedLabel);
        if (result === 'processed') counts.processed++;
        else counts.skipped++;
      }

      // Rate-limit: 1-second pause between emails to avoid API throttling
      if (result === 'processed') Utilities.sleep(1500);

    } catch (e) {
      log('Error on "' + message.getSubject() + '": ' + e.message, 'ERROR');
      thread.addLabel(errorLabel);
      counts.errors++;
      if (counts.errors === 1) {
        notifyError(message.getSubject(), e.message);
      }
    }
  }

  log(
    '=== Scan complete  processed:' + counts.processed +
    '  skipped:'  + counts.skipped +
    '  errors:'   + counts.errors + ' ==='
  );
}

// ----------------------------------------------------------------
// Single email processor
// ----------------------------------------------------------------

/**
 * Processes one Gmail message.
 * Returns 'processed' | 'not_claim' | 'duplicate'
 * Throws on unrecoverable error.
 */
function processSingleMessage(message) {
  var emailId    = message.getId();
  var subject    = message.getSubject();
  var plainBody  = message.getPlainBody();
  var htmlBody   = message.getBody();
  var sender     = message.getFrom();
  var receivedAt = message.getDate();

  // Body: prefer plain text; strip HTML tags as fallback
  var body = plainBody || htmlBody.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

  // Parse sender into name + email address
  var senderMatch = sender.match(/^"?([^"<]+?)"?\s*<?([^>]*)>?\s*$/);
  var senderName  = senderMatch ? senderMatch[1].trim() : sender;
  var senderEmail = senderMatch ? senderMatch[2].trim() : sender;

  log('Reviewing: "' + subject + '" from ' + senderEmail);

  // ── Step 1: Claude parses the email ──────────────────────────
  var parsed = parseClaimEmail(subject, body, senderName, senderEmail);

  if (!parsed) {
    log('Not a claim assignment — skipping: "' + subject + '"');
    return 'not_claim';
  }

  log('Claim identified: ' + (parsed.claimNumber || 'no #') +
      ' / ' + (parsed.insuredName || 'no name'));

  // ── Step 2: Duplicate check ───────────────────────────────────
  parsed.isDuplicate = isDuplicate(parsed.claimNumber, emailId);
  parsed.emailId     = emailId;
  parsed.receivedAt  = receivedAt;

  if (parsed.isDuplicate) {
    log('Flagging as duplicate: ' + parsed.claimNumber, 'WARN');
    // Still log the row but marked DUPLICATE — don't return early
  }

  // ── Step 3: Build full address string ────────────────────────
  var fullAddress = [
    parsed.riskStreet || parsed.riskAddress,
    parsed.riskCity,
    parsed.riskState,
    parsed.riskZip,
  ].filter(Boolean).join(', ');

  // ── Step 4: Create Drive folder tree ─────────────────────────
  var folderResult = createClaimFolder(
    parsed.carrier,
    parsed.dateOfLoss,
    parsed.claimNumber,
    parsed.insuredName
  );
  var folderId  = folderResult.folderId;
  var folderUrl = folderResult.folderUrl;

  // ── Step 5: Save assignment email to Drive ───────────────────
  if (folderId) {
    saveEmailToFolder(folderId, subject, body, receivedAt);
  }

  // ── Step 6: Mileage + map ─────────────────────────────────────
  var mileageData = null;
  var mapsUrl     = null;
  var mapFileUrl  = null;

  if (fullAddress && fullAddress.length > 10) {
    mileageData = getMileageInfo(fullAddress);
    mapsUrl     = getGoogleMapsUrl(fullAddress);

    if (mileageData && folderId) {
      mapFileUrl = downloadMapToDrive(folderId, fullAddress, mileageData.polyline);
    }
  } else {
    log('Could not build a full risk address — mileage skipped', 'WARN');
  }

  // ── Step 7: Write to Claims sheet ────────────────────────────
  var rowNum = addClaimRow(parsed, mileageData, folderUrl, mapsUrl, mapFileUrl);

  log(
    'DONE — row ' + rowNum + ':  ' +
    (parsed.claimNumber || 'no #') + '  |  ' +
    (parsed.insuredName || 'no name') + '  |  ' +
    (mileageData ? mileageData.milesRoundTrip + ' mi RT' : 'no mileage')
  );

  return 'processed';
}
