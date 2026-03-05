"""
utils.py — Shared helpers, paths, and utilities for the social media cross-poster.
"""

import os
import time
import functools
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── PATH CONSTANTS ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.parent        # project root
TMP_DIR = BASE_DIR / ".tmp"
TMP_SOCIAL_DIR = TMP_DIR / "social"
DB_PATH = TMP_DIR / "social.db"

IMAGES_DIR = TMP_SOCIAL_DIR / "images"
AUDIO_DIR = TMP_SOCIAL_DIR / "audio"
VIDEO_DIR = TMP_SOCIAL_DIR / "video"
POSTS_DIR = TMP_SOCIAL_DIR / "posts"


def ensure_dirs() -> None:
    """Create all .tmp/social/* subdirs if they don't exist."""
    for d in [TMP_SOCIAL_DIR, IMAGES_DIR, AUDIO_DIR, VIDEO_DIR, POSTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ── ENV CONFIG ────────────────────────────────────────────────────────────────

def load_env_config() -> dict:
    """
    Read all SOCIAL_* and related env vars into a dict.
    Warns (does not crash) if optional keys are missing.
    Returns dict with None for missing optional keys.
    """
    required = []
    optional = {
        # Meta
        "META_APP_ID": None,
        "META_APP_SECRET": None,
        "META_PAGE_ACCESS_TOKEN": None,
        "META_PAGE_ID": None,
        "META_IG_USER_ID": None,
        # HuggingFace
        "HF_TOKEN": None,
        "HF_IMAGE_MODEL": "black-forest-labs/FLUX.1-schnell",
        "HF_AUDIO_ENABLED": "true",
        # Email
        "EMAIL_BACKEND": "smtp",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": None,
        "SMTP_PASSWORD": None,
        "EMAIL_FROM_NAME": None,
        "EMAIL_FROM_ADDRESS": None,
        # Content
        "SOCIAL_NICHE": "business acquisitions",
        "SOCIAL_BRAND_NAME": os.getenv("BROKER_COMPANY", "Valar Brokers"),
        "SOCIAL_WEBSITE_URL": None,
        "SOCIAL_CTA": None,
        # Trends
        "REDDIT_SUBREDDITS": "Entrepreneur,smallbusiness",
        "RSS_FEEDS": "",
        "REDDIT_CLIENT_ID": None,
        "REDDIT_CLIENT_SECRET": None,
        "REDDIT_USER_AGENT": "SocialPoster/1.0",
        # Anthropic (already in .env for lead gen)
        "ANTHROPIC_API_KEY": None,
    }

    config = {}
    for key, default in optional.items():
        config[key] = os.getenv(key, default)

    return config


# ── RETRY DECORATOR ───────────────────────────────────────────────────────────

def retry(max_attempts: int = 3, delay: float = 5.0, backoff: float = 2.0,
          exceptions: tuple = (Exception,)):
    """
    Decorator: retry a function up to max_attempts times with exponential backoff.

    Usage:
        @retry(max_attempts=3, delay=5.0)
        def my_func(): ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wait = delay
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        print(f"  [RETRY] {func.__name__} failed (attempt {attempt+1}/{max_attempts}): {e}")
                        time.sleep(wait)
                        wait *= backoff
                    else:
                        print(f"  [FAILED] {func.__name__} failed after {max_attempts} attempts: {e}")
            raise last_exc
        return wrapper
    return decorator


# ── TABLE FORMATTER ───────────────────────────────────────────────────────────

def format_table(headers: list, rows: list, col_widths: list = None) -> str:
    """
    Format a list of rows as a padded table (matches run_lead_gen.py print style).

    Args:
        headers: list of column header strings
        rows: list of lists (each row = list of values matching headers)
        col_widths: optional list of min widths; auto-calculated if None

    Returns:
        Formatted string ready to print.
    """
    if not rows and not headers:
        return "(no data)"

    all_rows = [headers] + [[str(v) for v in row] for row in rows]

    if col_widths is None:
        col_widths = [max(len(str(r[i])) for r in all_rows) + 2
                      for i in range(len(headers))]

    lines = []
    header_line = "  ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    sep = "-" * len(header_line)
    lines.append(header_line)
    lines.append(sep)
    for row in rows:
        line = "  ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row))
        lines.append(line)

    return "\n".join(lines)


# ── MISC HELPERS ──────────────────────────────────────────────────────────────

def truncate(text: str, max_chars: int, ellipsis: str = "...") -> str:
    """Truncate text to max_chars, appending ellipsis if cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - len(ellipsis)] + ellipsis


def safe_filename(text: str, max_len: int = 50) -> str:
    """Convert arbitrary text to a filesystem-safe filename component."""
    import re
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    safe = re.sub(r"[\s_-]+", "_", safe).strip("_")
    return safe[:max_len]
