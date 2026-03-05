"""
db.py — SQLite schema and all query functions for the social media cross-poster.

Database: .tmp/social.db

Tables:
  ideas          — content concepts (pending/approved/created)
  posts          — generated content (text + media paths)
  platform_posts — per-platform publish records
  engagement     — periodic metric snapshots from analytics fetches
  subscribers    — email newsletter list
  trends_cache   — 24-hour TTL cache for trend API calls
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

from .utils import DB_PATH, ensure_dirs


# ── CONNECTION ─────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set for dict-like access."""
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── SCHEMA INIT ────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    niche           TEXT,
    title           TEXT NOT NULL,
    hook            TEXT,
    platforms       TEXT DEFAULT '["instagram","facebook","email"]',
    trend_source    TEXT,
    trend_keyword   TEXT,
    status          TEXT DEFAULT 'pending',
    approved_at     TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id         INTEGER REFERENCES ideas(id),
    created_at      TEXT DEFAULT (datetime('now')),
    status          TEXT DEFAULT 'draft',
    caption_instagram TEXT,
    caption_facebook  TEXT,
    email_subject   TEXT,
    article_html    TEXT,
    hashtags        TEXT,
    image_path      TEXT,
    audio_path      TEXT,
    video_path      TEXT,
    error_log       TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS platform_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER REFERENCES posts(id),
    platform        TEXT NOT NULL,
    posted_at       TEXT,
    platform_post_id TEXT,
    status          TEXT DEFAULT 'pending',
    error_message   TEXT,
    url             TEXT
);

CREATE TABLE IF NOT EXISTS engagement (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_post_id    INTEGER REFERENCES platform_posts(id),
    fetched_at          TEXT DEFAULT (datetime('now')),
    likes               INTEGER DEFAULT 0,
    comments            INTEGER DEFAULT 0,
    shares              INTEGER DEFAULT 0,
    saves               INTEGER DEFAULT 0,
    reach               INTEGER DEFAULT 0,
    impressions         INTEGER DEFAULT 0,
    clicks              INTEGER DEFAULT 0,
    email_opens         INTEGER DEFAULT 0,
    email_clicks        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscribers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    added_at    TEXT DEFAULT (datetime('now')),
    status      TEXT DEFAULT 'active',
    tags        TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS trends_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    data        TEXT NOT NULL,
    fetched_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(source, keyword)
);
"""


def init_db() -> None:
    """Create all tables if they don't already exist."""
    ensure_dirs()
    conn = get_connection()
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()


# ── IDEAS ─────────────────────────────────────────────────────────────────────

def insert_idea(title: str, hook: str = None, niche: str = None,
                platforms: list = None, trend_source: str = None,
                trend_keyword: str = None) -> int:
    """Insert a new idea. Returns the new idea ID."""
    conn = get_connection()
    try:
        platforms_json = json.dumps(platforms or ["instagram", "facebook", "email"])
        cur = conn.execute(
            """INSERT INTO ideas (title, hook, niche, platforms, trend_source, trend_keyword)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, hook, niche, platforms_json, trend_source, trend_keyword)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_idea(idea_id: int) -> Optional[dict]:
    """Fetch one idea by ID. Returns dict or None."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["platforms"] = json.loads(d.get("platforms") or "[]")
        return d
    finally:
        conn.close()


def list_ideas(status: str = None, limit: int = 20) -> list:
    """List ideas, optionally filtered by status. Newest first."""
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM ideas WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ideas ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["platforms"] = json.loads(d.get("platforms") or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


def update_idea_status(idea_id: int, status: str) -> None:
    """Update the status of an idea (pending/approved/rejected/created)."""
    conn = get_connection()
    try:
        approved_at = datetime.utcnow().isoformat() if status == "approved" else None
        conn.execute(
            "UPDATE ideas SET status=?, approved_at=? WHERE id=?",
            (status, approved_at, idea_id)
        )
        conn.commit()
    finally:
        conn.close()


# ── POSTS ─────────────────────────────────────────────────────────────────────

def insert_post(idea_id: int, caption_instagram: str = None,
                caption_facebook: str = None, email_subject: str = None,
                article_html: str = None, hashtags: str = None,
                image_path: str = None, audio_path: str = None,
                video_path: str = None, error_log: list = None) -> int:
    """Insert a new post record. Returns new post ID."""
    conn = get_connection()
    try:
        errors_json = json.dumps(error_log or [])
        cur = conn.execute(
            """INSERT INTO posts
               (idea_id, caption_instagram, caption_facebook, email_subject,
                article_html, hashtags, image_path, audio_path, video_path, error_log)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (idea_id, caption_instagram, caption_facebook, email_subject,
             article_html, hashtags, image_path, audio_path, video_path, errors_json)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_post(post_id: int) -> Optional[dict]:
    """Fetch one post by ID. Returns dict or None."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["error_log"] = json.loads(d.get("error_log") or "[]")
        return d
    finally:
        conn.close()


def list_posts(status: str = None, limit: int = 20) -> list:
    """List posts with joined idea title. Newest first."""
    conn = get_connection()
    try:
        sql = """
            SELECT p.*, i.title as idea_title, i.niche
            FROM posts p
            LEFT JOIN ideas i ON p.idea_id = i.id
            {where}
            ORDER BY p.id DESC LIMIT ?
        """
        if status:
            rows = conn.execute(
                sql.format(where="WHERE p.status=?"), (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                sql.format(where=""), (limit,)
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["error_log"] = json.loads(d.get("error_log") or "[]")
            result.append(d)
        return result
    finally:
        conn.close()


def update_post_status(post_id: int, status: str, error: str = None) -> None:
    """Update post status. Optionally append an error to error_log."""
    conn = get_connection()
    try:
        if error:
            row = conn.execute("SELECT error_log FROM posts WHERE id=?", (post_id,)).fetchone()
            errors = json.loads(row["error_log"] or "[]") if row else []
            errors.append(error)
            conn.execute(
                "UPDATE posts SET status=?, error_log=? WHERE id=?",
                (status, json.dumps(errors), post_id)
            )
        else:
            conn.execute("UPDATE posts SET status=? WHERE id=?", (status, post_id))
        conn.commit()
    finally:
        conn.close()


# ── PLATFORM POSTS ─────────────────────────────────────────────────────────────

def insert_platform_post(post_id: int, platform: str) -> int:
    """Create a platform_posts record for one platform. Returns new ID."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO platform_posts (post_id, platform) VALUES (?, ?)",
            (post_id, platform)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_platform_post(pp_id: int, status: str,
                         platform_post_id: str = None,
                         url: str = None, error: str = None) -> None:
    """Update a platform_posts record after posting attempt."""
    conn = get_connection()
    try:
        posted_at = datetime.utcnow().isoformat() if status == "posted" else None
        conn.execute(
            """UPDATE platform_posts
               SET status=?, platform_post_id=?, url=?, error_message=?, posted_at=?
               WHERE id=?""",
            (status, platform_post_id, url, error, posted_at, pp_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_posted_platform_posts() -> list:
    """Return all platform_posts with status='posted' (for analytics fetching)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM platform_posts WHERE status='posted' AND platform_post_id IS NOT NULL"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ── ENGAGEMENT ────────────────────────────────────────────────────────────────

def insert_engagement(platform_post_id: int, **metrics) -> None:
    """
    Insert an engagement snapshot for a platform post.
    Valid metric keys: likes, comments, shares, saves, reach, impressions,
                       clicks, email_opens, email_clicks
    """
    valid = {"likes", "comments", "shares", "saves", "reach", "impressions",
             "clicks", "email_opens", "email_clicks"}
    cols = [k for k in metrics if k in valid]
    if not cols:
        return
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    vals = [metrics[c] for c in cols]
    conn = get_connection()
    try:
        conn.execute(
            f"INSERT INTO engagement (platform_post_id, {col_names}) VALUES (?, {placeholders})",
            [platform_post_id] + vals
        )
        conn.commit()
    finally:
        conn.close()


def get_top_posts(limit: int = 10) -> list:
    """
    Return top-performing posts by total engagement (for seeding idea generation).
    Joins posts → ideas to include idea titles.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                i.title as idea_title,
                i.niche,
                pp.platform,
                SUM(e.likes + e.comments + e.shares + e.saves) as total_engagement,
                MAX(e.reach) as peak_reach
            FROM engagement e
            JOIN platform_posts pp ON e.platform_post_id = pp.id
            JOIN posts p ON pp.post_id = p.id
            JOIN ideas i ON p.idea_id = i.id
            GROUP BY pp.id
            ORDER BY total_engagement DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_engagement_summary() -> list:
    """
    Return aggregated engagement per post for the report command.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                p.id as post_id,
                i.title as idea_title,
                p.created_at,
                pp.platform,
                pp.posted_at,
                pp.url,
                COALESCE(SUM(e.likes), 0) as likes,
                COALESCE(SUM(e.comments), 0) as comments,
                COALESCE(SUM(e.shares), 0) as shares,
                COALESCE(SUM(e.saves), 0) as saves,
                COALESCE(MAX(e.reach), 0) as reach,
                COALESCE(SUM(e.email_opens), 0) as email_opens
            FROM posts p
            LEFT JOIN ideas i ON p.idea_id = i.id
            LEFT JOIN platform_posts pp ON pp.post_id = p.id
            LEFT JOIN engagement e ON e.platform_post_id = pp.id
            WHERE p.status IN ('posted', 'partial')
            GROUP BY pp.id
            ORDER BY p.id DESC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ── SUBSCRIBERS ───────────────────────────────────────────────────────────────

def add_subscriber(email: str, first_name: str = None, last_name: str = None) -> bool:
    """
    Add an email subscriber. Returns True if added, False if already exists.
    """
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, first_name, last_name) VALUES (?,?,?)",
            (email.strip().lower(), first_name, last_name)
        )
        conn.commit()
        return conn.execute(
            "SELECT changes()"
        ).fetchone()[0] > 0
    finally:
        conn.close()


def remove_subscriber(email: str) -> bool:
    """Mark subscriber as unsubscribed. Returns True if found."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE subscribers SET status='unsubscribed' WHERE email=?",
            (email.strip().lower(),)
        )
        conn.commit()
        return conn.execute("SELECT changes()").fetchone()[0] > 0
    finally:
        conn.close()


def get_active_subscribers() -> list:
    """Return all active subscribers as list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE status='active' ORDER BY added_at"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_subscribers() -> dict:
    """Return subscriber counts by status."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM subscribers GROUP BY status"
        ).fetchall()
        return {row["status"]: row["n"] for row in rows}
    finally:
        conn.close()


# ── TRENDS CACHE ──────────────────────────────────────────────────────────────

def get_cached_trends(source: str, keyword: str, ttl_hours: int = 24) -> Optional[list]:
    """
    Return cached trend data if fresher than ttl_hours, else None.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT data, fetched_at FROM trends_cache
               WHERE source=? AND keyword=?""",
            (source, keyword)
        ).fetchone()
        if row is None:
            return None
        from datetime import timezone
        fetched = datetime.fromisoformat(row["fetched_at"])
        age_hours = (datetime.utcnow() - fetched).total_seconds() / 3600
        if age_hours > ttl_hours:
            return None
        return json.loads(row["data"])
    finally:
        conn.close()


def set_cached_trends(source: str, keyword: str, data: list) -> None:
    """Upsert trend data into the cache."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO trends_cache (source, keyword, data, fetched_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (source, keyword, json.dumps(data))
        )
        conn.commit()
    finally:
        conn.close()


# ── DB STATS ──────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return a dict of key counts for --check-config output."""
    conn = get_connection()
    try:
        def count(table, where=""):
            q = f"SELECT COUNT(*) FROM {table}"
            if where:
                q += f" WHERE {where}"
            return conn.execute(q).fetchone()[0]

        return {
            "ideas_total": count("ideas"),
            "ideas_approved": count("ideas", "status='approved'"),
            "posts_total": count("posts"),
            "posts_posted": count("posts", "status='posted'"),
            "subscribers_active": count("subscribers", "status='active'"),
        }
    finally:
        conn.close()
