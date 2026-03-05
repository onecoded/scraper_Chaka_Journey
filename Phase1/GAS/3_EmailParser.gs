// ================================================================
// 3_EmailParser.gs  —  Claude AI-powered claim email parser
// ================================================================

/**
 * Calls Claude to extract structured claim data from an email.
 *
 * Returns a parsed object on success.
 * Returns null if Claude determines it is NOT a claim assignment.
 * Throws an Error if the API call fails.
 */
function parseClaimEmail(subject, body, senderName, senderEmail) {
  if (!CONFIG.CLAUDE_API_KEY || CONFIG.CLAUDE_API_KEY.indexOf('YOUR_') === 0) {
    throw new Error('Claude API key not configured. Edit CONFIG.CLAUDE_API_KEY in 1_Config.gs');
  }

  var prompt = buildPrompt(subject, body, senderName, senderEmail);

  var payload = {
    model: 'claude-opus-4-6',
    max_tokens: 1500,
    messages: [{ role: 'user', content: prompt }],
  };

  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-api-key': CONFIG.CLAUDE_API_KEY,
      'anthropic-version': '2023-06-01',
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };

  var response;
  try {
    response = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', options);
  } catch (e) {
    throw new Error('Network error reaching Claude API: ' + e.message);
  }

  var code = response.getResponseCode();
  if (code !== 200) {
    throw new Error('Claude API error ' + code + ': ' + response.getContentText().substring(0, 300));
  }

  var responseData = JSON.parse(response.getContentText());
  var rawText = responseData.content[0].text.trim();

  // Extract JSON — Claude sometimes wraps it in markdown code fences
  var parsed;
  try {
    parsed = JSON.parse(rawText);
  } catch (e) {
    var fenceMatch = rawText.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    var braceMatch = rawText.match(/(\{[\s\S]*\})/);
    var jsonStr = fenceMatch ? fenceMatch[1] : (braceMatch ? braceMatch[1] : null);
    if (!jsonStr) {
      throw new Error('No JSON in Claude response: ' + rawText.substring(0, 300));
    }
    try {
      parsed = JSON.parse(jsonStr);
    } catch (e2) {
      throw new Error('Could not parse JSON from Claude: ' + jsonStr.substring(0, 300));
    }
  }

  // If Claude says it's not a claim assignment, return null
  if (!parsed.isClaimEmail) {
    return null;
  }

  // Normalise phone numbers
  if (parsed.insuredPhone)    parsed.insuredPhone    = normalizePhone(parsed.insuredPhone);
  if (parsed.carrierAdjPhone) parsed.carrierAdjPhone = normalizePhone(parsed.carrierAdjPhone);

  return parsed;
}

// ----------------------------------------------------------------
// Prompt builder
// ----------------------------------------------------------------
function buildPrompt(subject, body, senderName, senderEmail) {
  // Truncate body to avoid token limits while keeping the key data
  var truncatedBody = body ? body.substring(0, 4500) : '(no body)';

  return 'You are an expert insurance claim parser for a licensed property insurance adjuster in Hawaii.\n\n' +
    'Analyse the email below and determine whether it is a NEW CLAIM ASSIGNMENT ' +
    '(an insurance company or third-party administrator assigning a claim to an independent adjuster).\n\n' +
    'EMAIL\n' +
    '─────────────────────────────────────────────\n' +
    'Subject : ' + subject + '\n' +
    'From    : ' + senderName + ' <' + senderEmail + '>\n\n' +
    truncatedBody + '\n' +
    '─────────────────────────────────────────────\n\n' +
    'Return ONLY a valid JSON object — no markdown, no commentary. ' +
    'Use null for any field not present in the email.\n\n' +
    '{\n' +
    '  "isClaimEmail"     : true or false — is this a claim assignment?,\n' +
    '  "claimNumber"      : "claim or file number, e.g. LM-2026-001234",\n' +
    '  "carrier"          : "insurance company name, e.g. Liberty Mutual",\n' +
    '  "insuredName"      : "full policyholder name",\n' +
    '  "riskAddress"      : "full property address (street + city + state + zip)",\n' +
    '  "riskStreet"       : "street portion only",\n' +
    '  "riskCity"         : "city only",\n' +
    '  "riskState"        : "two-letter state abbreviation",\n' +
    '  "riskZip"          : "zip code",\n' +
    '  "dateOfLoss"       : "MM/DD/YYYY",\n' +
    '  "peril"            : "cause of loss, e.g. Wind/Hurricane, Water/Flooding, Fire, Hail",\n' +
    '  "claimType"        : "Residential or Commercial",\n' +
    '  "rcv"              : replacement cost value as a plain number or null,\n' +
    '  "policyNumber"     : "policy number",\n' +
    '  "carrierAdjName"   : "name of the carrier/desk adjuster sending the assignment",\n' +
    '  "carrierAdjPhone"  : "carrier adjuster phone number",\n' +
    '  "carrierAdjEmail"  : "carrier adjuster email",\n' +
    '  "insuredPhone"     : "insured/policyholder phone number",\n' +
    '  "insuredEmail"     : "insured/policyholder email",\n' +
    '  "inspectionDeadline": "MM/DD/YYYY if mentioned, else null",\n' +
    '  "notes"            : "any special instructions or coverage notes (max 200 chars)"\n' +
    '}\n\n' +
    'Return ONLY the JSON object.';
}
