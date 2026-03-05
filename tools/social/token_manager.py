"""
token_manager.py — Meta (Facebook/Instagram) OAuth token management.

Handles:
  1. The OAuth flow to get initial tokens (--refresh-token command)
  2. Token type detection (short-lived vs long-lived vs page token)
  3. Expiry checking and warnings

Token types:
  - Short-lived user token: valid 1-2 hours (from initial OAuth)
  - Long-lived user token: valid 60 days (exchange short → long)
  - Page access token: NEVER expires (derived from long-lived user token)
    ← This is what we want for automation

Setup flow:
  1. Create Facebook App at developers.facebook.com (Business type)
  2. Add products: "Instagram Graph API" and "Pages API"
  3. Set redirect URI in App → Facebook Login → Valid OAuth Redirect URIs
  4. Run: python tools/run_social.py --refresh-token
  5. Tokens are saved to .env automatically

Docs:
  - Meta Graph API: https://developers.facebook.com/docs/graph-api
  - Long-lived tokens: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
"""

import os
import json
import time
import requests
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from dotenv import load_dotenv, set_key

load_dotenv()

META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_GRAPH_URL = "https://graph.facebook.com/v21.0"
META_AUTH_URL = "https://www.facebook.com/dialog/oauth"
META_TOKEN_URL = f"{META_GRAPH_URL}/oauth/access_token"

# Config sidecar file for expiry tracking
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_DIR / ".tmp" / "social" / "meta_token_config.json"
ENV_PATH = BASE_DIR / ".env"

# Required OAuth permissions
SCOPES = [
    "pages_manage_posts",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_insights",
    "pages_show_list",
    "business_management",
]


def _load_token_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_token_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def check_token_expiry() -> dict:
    """
    Check if the Meta access token is nearing expiry.

    Returns dict with:
      - "token_type": "page" | "long_lived" | "short_lived" | "unknown"
      - "expires_in_days": int or None
      - "warning": bool (True if < 10 days or token is short-lived)
      - "message": str
    """
    config = _load_token_config()
    token_type = config.get("token_type", "unknown")
    expires_at = config.get("expires_at")

    if token_type == "page":
        return {
            "token_type": "page",
            "expires_in_days": None,
            "warning": False,
            "message": "Page access token (never expires)"
        }

    if expires_at:
        days_left = (expires_at - time.time()) / 86400
        warning = days_left < 10
        return {
            "token_type": token_type,
            "expires_in_days": int(days_left),
            "warning": warning,
            "message": f"{token_type} token expires in {int(days_left)} days"
        }

    return {
        "token_type": "unknown",
        "expires_in_days": None,
        "warning": True,
        "message": "Token expiry unknown. Run --refresh-token to re-authorize."
    }


def exchange_for_long_lived_token(short_token: str) -> tuple:
    """
    Exchange a short-lived user token for a long-lived one (valid 60 days).

    Returns:
        (long_lived_token: str, expires_in_seconds: int)
    Raises:
        RuntimeError on API failure.
    """
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "fb_exchange_token": short_token,
    }
    resp = requests.get(META_TOKEN_URL, params=params, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    token = data.get("access_token")
    expires = data.get("expires_in", 5184000)  # default 60 days
    if not token:
        raise RuntimeError(f"No access_token in response: {data}")
    return token, expires


def get_page_access_token(user_token: str, page_id: str) -> str:
    """
    Exchange a long-lived user token for a Page access token.
    Page tokens derived from long-lived user tokens never expire.

    Returns:
        page_access_token string.
    Raises:
        RuntimeError if page not found or API fails.
    """
    resp = requests.get(
        f"{META_GRAPH_URL}/me/accounts",
        params={"access_token": user_token},
        timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch pages: {resp.text}")

    pages = resp.json().get("data", [])
    for page in pages:
        if page.get("id") == str(page_id) or page.get("name"):
            # If page_id matches OR there's only one page, use it
            if page.get("id") == str(page_id):
                return page["access_token"]

    # If exact match not found, list available pages
    if pages:
        print("\n  Available Facebook Pages:")
        for p in pages:
            print(f"    ID: {p['id']}  Name: {p.get('name', 'Unknown')}")
        if len(pages) == 1:
            print(f"  Using the only available page: {pages[0]['name']}")
            return pages[0]["access_token"]
        raise RuntimeError(f"Page ID '{page_id}' not found. Set META_PAGE_ID to one of the IDs above.")

    raise RuntimeError("No Facebook Pages found. Make sure your account manages a Facebook Page.")


def get_instagram_user_id(page_id: str, page_token: str) -> str | None:
    """
    Get the Instagram Business Account ID linked to the Facebook Page.

    Returns:
        Instagram user ID string, or None if not linked.
    """
    resp = requests.get(
        f"{META_GRAPH_URL}/{page_id}",
        params={
            "fields": "instagram_business_account",
            "access_token": page_token,
        },
        timeout=15
    )
    if resp.status_code == 200:
        data = resp.json()
        ig = data.get("instagram_business_account")
        if ig:
            return ig.get("id")
    return None


def _write_env_key(key: str, value: str) -> None:
    """Update a key in the .env file."""
    if ENV_PATH.exists():
        set_key(str(ENV_PATH), key, value)
    else:
        print(f"  [WARN] .env not found at {ENV_PATH}")


def run_oauth_flow() -> bool:
    """
    Interactive OAuth flow to get Meta tokens.

    Steps:
    1. Print the auth URL
    2. Prompt user to visit it and paste back the redirect URL
    3. Extract code from URL → exchange for short token → long token → page token
    4. Save everything to .env

    Returns True on success.
    """
    if not META_APP_ID or not META_APP_SECRET:
        print("\n[ERROR] META_APP_ID and META_APP_SECRET must be set in .env first.")
        print("\nSetup steps:")
        print("  1. Go to: https://developers.facebook.com/apps/")
        print("  2. Click 'Create App' → Select 'Business' type")
        print("  3. Add products: 'Instagram Graph API' and 'Pages API'")
        print("  4. Settings → Basic → copy App ID and App Secret → add to .env")
        print("  5. Facebook Login → Settings → Valid OAuth Redirect URIs:")
        print("     Add: https://localhost/callback")
        print("  6. Re-run: python tools/run_social.py --refresh-token")
        return False

    # Build auth URL
    redirect_uri = "https://localhost/callback"
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }
    auth_url = f"{META_AUTH_URL}?{urlencode(params)}"

    print("\n" + "="*60)
    print("META OAUTH AUTHORIZATION")
    print("="*60)
    print("\n[STEP 1] Open this URL in your browser and authorize the app:")
    print(f"\n  {auth_url}\n")

    try:
        webbrowser.open(auth_url)
        print("  (Attempting to open in your browser automatically...)")
    except Exception:
        pass

    print("\n[STEP 2] After authorizing, you'll be redirected to localhost.")
    print("  The page will show an error — that's expected.")
    print("  Copy the FULL URL from your browser address bar and paste it below.")

    try:
        redirect_response = input("\nPaste the redirect URL here: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[CANCELLED]")
        return False

    if not redirect_response:
        print("[ERROR] No URL provided.")
        return False

    # Extract code from URL
    try:
        parsed = urlparse(redirect_response)
        code = parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            print(f"[ERROR] Could not find 'code' parameter in URL: {redirect_response}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to parse redirect URL: {e}")
        return False

    print("\n[STEP 3] Exchanging code for access tokens...")

    # Exchange code for short-lived token
    try:
        resp = requests.post(META_TOKEN_URL, data={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": redirect_uri,
            "code": code,
        }, timeout=15)

        if resp.status_code != 200:
            print(f"[ERROR] Token exchange failed: {resp.text}")
            return False

        short_token = resp.json().get("access_token")
        if not short_token:
            print(f"[ERROR] No access_token in response: {resp.json()}")
            return False

        print("  ✓ Got short-lived user token")

    except Exception as e:
        print(f"[ERROR] Token exchange request failed: {e}")
        return False

    # Exchange for long-lived token
    try:
        long_token, expires_in = exchange_for_long_lived_token(short_token)
        print(f"  ✓ Got long-lived user token (valid {expires_in//86400} days)")
    except Exception as e:
        print(f"[ERROR] Long-lived token exchange failed: {e}")
        return False

    # Get Page access token
    page_id = os.getenv("META_PAGE_ID", "").strip()
    if not page_id:
        print("\n  Fetching your Facebook Pages to find the Page ID...")
        resp = requests.get(
            f"{META_GRAPH_URL}/me/accounts",
            params={"access_token": long_token},
            timeout=15
        )
        if resp.status_code == 200:
            pages = resp.json().get("data", [])
            if pages:
                print("\n  Your Facebook Pages:")
                for p in pages:
                    print(f"    ID: {p['id']}  →  {p.get('name', 'Unknown')}")
                try:
                    page_id = input("\n  Enter the Page ID to use: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("[CANCELLED]")
                    return False

    if not page_id:
        print("[ERROR] No Page ID provided.")
        return False

    try:
        page_token = get_page_access_token(long_token, page_id)
        print("  ✓ Got Page access token (never expires)")
    except Exception as e:
        print(f"[ERROR] Page token failed: {e}")
        return False

    # Get Instagram User ID
    print("\n[STEP 4] Looking up Instagram Business Account...")
    ig_user_id = get_instagram_user_id(page_id, page_token)
    if ig_user_id:
        print(f"  ✓ Found Instagram User ID: {ig_user_id}")
    else:
        print("  ! Instagram Business Account not found.")
        print("    Make sure your Instagram account is:")
        print("    - A Business or Creator account (not Personal)")
        print("    - Connected to your Facebook Page")
        print("    Instagram posting will be skipped until this is set up.")

    # Save to .env
    print("\n[STEP 5] Saving tokens to .env...")
    _write_env_key("META_PAGE_ID", page_id)
    _write_env_key("META_PAGE_ACCESS_TOKEN", page_token)
    if ig_user_id:
        _write_env_key("META_IG_USER_ID", ig_user_id)

    # Save config for expiry tracking
    _save_token_config({
        "token_type": "page",
        "page_id": page_id,
        "ig_user_id": ig_user_id,
        "obtained_at": time.time(),
        "expires_at": None,  # page tokens don't expire
    })

    print("\n" + "="*60)
    print("AUTHORIZATION COMPLETE")
    print("="*60)
    print(f"  Page ID:       {page_id}")
    print(f"  IG User ID:    {ig_user_id or 'not found'}")
    print(f"  Token type:    Page (never expires)")
    print(f"\n  Tokens saved to .env")
    print(f"  Run: python tools/run_social.py --check-config to verify")

    return True
