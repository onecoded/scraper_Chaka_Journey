"""
_browser.py
-----------
Shared Playwright browser helper for all scrapers.
Uses a real Chromium browser to bypass Akamai / bot detection.

Usage (in scraper scripts):
    from _browser import fetch_page, fetch_pages_sync

    html = fetch_page("https://www.bizbuysell.com/florida-businesses-for-sale/")
    pages = fetch_pages_sync([url1, url2], delay=2.0)
"""

import time
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


def _make_browser(playwright, headless: bool = True):
    """Launch a stealth Chromium browser that bypasses bot detection."""
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1366,768",
        ]
    )
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return browser, context


def _apply_stealth(page) -> None:
    """Apply stealth patches to a Playwright page."""
    if HAS_STEALTH:
        Stealth().apply_stealth_sync(page)
    else:
        # Manual minimal stealth without the package
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
        """)


def fetch_page(url: str, wait_selector: str | None = None, timeout_ms: int = 20000, headless: bool = True) -> str:
    """Fetch a single URL using a stealth Chromium browser. Returns HTML."""
    with sync_playwright() as p:
        browser, context = _make_browser(p, headless=headless)
        page = context.new_page()
        _apply_stealth(page)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    pass
            html = page.content()
        except Exception as e:
            print(f"  [BROWSER] Error: {e}")
            html = ""
        finally:
            page.close()
            browser.close()
    return html


def fetch_pages_sync(
    urls: list[str],
    delay: float = 2.0,
    wait_selector: str | None = None,
    timeout_ms: int = 20000,
    headless: bool = True,
) -> list[tuple[str, str]]:
    """
    Fetch multiple URLs sequentially with delay between each.
    Returns list of (url, html) tuples.
    Reuses a single browser session across all URLs for efficiency.
    """
    results = []
    with sync_playwright() as p:
        browser, context = _make_browser(p, headless=headless)
        page = context.new_page()
        _apply_stealth(page)
        try:
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if wait_selector:
                        try:
                            page.wait_for_selector(wait_selector, timeout=6000)
                        except Exception:
                            pass  # Selector may not exist — return whatever loaded
                    html = page.content()
                    results.append((url, html))
                except Exception as e:
                    print(f"  [BROWSER] Error fetching {url}: {e}")
                    results.append((url, ""))
                time.sleep(delay)
        finally:
            page.close()
            browser.close()
    return results
