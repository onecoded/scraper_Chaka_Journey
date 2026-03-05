// ================================================================
// 6_MapsManager.gs  —  Mileage calculation & route map download
// ================================================================

/**
 * Main entry point.  Calculates one-way and round-trip miles from
 * CONFIG.HOME_ADDRESS to riskAddress, estimates drive time, and
 * computes IRS mileage reimbursement.
 *
 * Returns an object:
 *   { milesOneWay, milesRoundTrip, driveTime, reimbursement, polyline }
 * or null if the address cannot be resolved.
 */
function getMileageInfo(riskAddress) {
  if (!riskAddress || riskAddress.trim().length < 5) {
    log('getMileageInfo: no valid risk address provided', 'WARN');
    return null;
  }

  // Prefer Directions API (gives polyline for the static map)
  if (CONFIG.MAPS_API_KEY && CONFIG.MAPS_API_KEY.indexOf('YOUR_') !== 0) {
    return getMileageViaDirectionsAPI(riskAddress);
  }

  // Fallback: GAS built-in Maps service (no API key needed, no polyline)
  log('MAPS_API_KEY not set — using built-in Maps service (no route map)', 'WARN');
  return getMileageViaBuiltIn(riskAddress);
}

// ----------------------------------------------------------------
// Directions API path (recommended)
// ----------------------------------------------------------------

function getMileageViaDirectionsAPI(riskAddress) {
  var url =
    'https://maps.googleapis.com/maps/api/directions/json' +
    '?origin='      + encodeURIComponent(CONFIG.HOME_ADDRESS) +
    '&destination=' + encodeURIComponent(riskAddress) +
    '&mode=driving' +
    '&key='         + CONFIG.MAPS_API_KEY;

  try {
    var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    var data     = JSON.parse(response.getContentText());

    if (data.status !== 'OK') {
      log('Directions API status "' + data.status + '" for: ' + riskAddress, 'WARN');
      return null;
    }

    var leg      = data.routes[0].legs[0];
    var polyline = data.routes[0].overview_polyline.points;
    var milesOW  = leg.distance.value / 1609.344;

    return {
      milesOneWay:    Math.round(milesOW * 10) / 10,
      milesRoundTrip: Math.round(milesOW * 2 * 10) / 10,
      driveTime:      leg.duration.text,
      reimbursement:  Math.round(milesOW * 2 * CONFIG.MILEAGE_RATE * 100) / 100,
      polyline:       polyline,
    };
  } catch (e) {
    log('Directions API error for "' + riskAddress + '": ' + e.message, 'ERROR');
    return null;
  }
}

// ----------------------------------------------------------------
// Built-in GAS Maps service fallback (no API key required)
// ----------------------------------------------------------------

function getMileageViaBuiltIn(riskAddress) {
  try {
    var directions = Maps.newDirectionFinder()
      .setOrigin(CONFIG.HOME_ADDRESS)
      .setDestination(riskAddress)
      .setMode(Maps.DirectionFinder.Mode.DRIVING)
      .getDirections();

    if (!directions || !directions.routes || !directions.routes.length) {
      log('No route found (built-in service) for: ' + riskAddress, 'WARN');
      return null;
    }

    var leg     = directions.routes[0].legs[0];
    var milesOW = leg.distance.value / 1609.344;
    var poly    = directions.routes[0].overview_polyline
                  ? directions.routes[0].overview_polyline.points
                  : null;

    return {
      milesOneWay:    Math.round(milesOW * 10) / 10,
      milesRoundTrip: Math.round(milesOW * 2 * 10) / 10,
      driveTime:      leg.duration.text,
      reimbursement:  Math.round(milesOW * 2 * CONFIG.MILEAGE_RATE * 100) / 100,
      polyline:       poly,
    };
  } catch (e) {
    log('Built-in Maps service error for "' + riskAddress + '": ' + e.message, 'ERROR');
    return null;
  }
}

// ----------------------------------------------------------------
// Google Maps URL (hyperlink in sheet)
// ----------------------------------------------------------------

/**
 * Returns a Google Maps directions URL that opens in browser or app.
 */
function getGoogleMapsUrl(riskAddress) {
  return 'https://www.google.com/maps/dir/?api=1' +
    '&origin='      + encodeURIComponent(CONFIG.HOME_ADDRESS) +
    '&destination=' + encodeURIComponent(riskAddress) +
    '&travelmode=driving';
}

// ----------------------------------------------------------------
// Static map download  →  saved as PNG to Drive
// ----------------------------------------------------------------

/**
 * Downloads a 800×600 PNG showing the route and saves it to the
 * claim's Drive folder.  Returns the Drive file URL or null.
 *
 * polyline — encoded polyline from the Directions API (optional).
 *            Without it, only the two markers are shown.
 */
function downloadMapToDrive(folderId, riskAddress, polyline) {
  if (!CONFIG.MAPS_API_KEY || CONFIG.MAPS_API_KEY.indexOf('YOUR_') === 0) {
    log('MAPS_API_KEY not configured — skipping map download', 'WARN');
    return null;
  }
  if (!folderId) return null;

  try {
    var origin      = encodeURIComponent(CONFIG.HOME_ADDRESS);
    var destination = encodeURIComponent(riskAddress);

    var mapUrl =
      'https://maps.googleapis.com/maps/api/staticmap' +
      '?size=800x600' +
      '&maptype=roadmap' +
      '&markers=color:red%7Clabel:H%7C' + origin +
      '&markers=color:blue%7Clabel:D%7C' + destination;

    if (polyline) {
      mapUrl += '&path=enc:' + encodeURIComponent(polyline);
    }
    mapUrl += '&key=' + CONFIG.MAPS_API_KEY;

    var imgResponse = UrlFetchApp.fetch(mapUrl, { muteHttpExceptions: true });
    if (imgResponse.getResponseCode() !== 200) {
      log('Static Maps API returned ' + imgResponse.getResponseCode(), 'WARN');
      return null;
    }

    // Save PNG bytes to the root claim folder (not sub-folder)
    var fileUrl = saveFileToDrive(
      folderId,
      'Mileage Map.png',
      imgResponse.getContent(),
      'image/png'
    );
    log('Route map PNG saved to Drive');
    return fileUrl;

  } catch (e) {
    log('Error downloading route map: ' + e.message, 'ERROR');
    return null;
  }
}
