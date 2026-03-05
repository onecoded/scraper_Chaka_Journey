"""
trends.py — Idea generation engine.

Pulls trending topics from:
  1. Google Trends (via pytrends — free, no API key)
  2. Reddit hot posts (via praw — read-only, free)
  3. RSS feeds (via feedparser — free)

Then uses Claude to brainstorm content ideas based on trends + past top-performing posts.
Falls back to raw trend headlines if Claude API is unavailable.

Caches trend API results for 24 hours in SQLite to avoid hammering free-tier APIs.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SOCIAL_NICHE = os.getenv("SOCIAL_NICHE", "business acquisitions")
BRAND_NAME = os.getenv("SOCIAL_BRAND_NAME", os.getenv("BROKER_COMPANY", "Valar Brokers"))
REDDIT_SUBREDDITS = os.getenv("REDDIT_SUBREDDITS", "Entrepreneur,smallbusiness")
RSS_FEEDS = os.getenv("RSS_FEEDS", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "SocialPoster/1.0")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONTENT_MODEL = os.getenv("EMAIL_MODEL", "claude-haiku-4-5-20251001")


# ── GOOGLE TRENDS ─────────────────────────────────────────────────────────────

def get_google_trends(niche: str, timeframe: str = "now 7-d") -> list:
    """
    Fetch rising search queries for the niche keyword using pytrends.

    Returns list of {"keyword": str, "value": int, "source": "google_trends"}.
    Caches results for 24 hours. Returns [] if pytrends not installed or fails.
    """
    from . import db as db_module
    cached = db_module.get_cached_trends("google_trends", niche)
    if cached is not None:
        print(f"  [TRENDS] Google Trends (cached): {len(cached)} topics")
        return cached

    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("  [WARN] pytrends not installed. Run: pip install pytrends")
        return []

    try:
        print(f"  [TRENDS] Fetching Google Trends for '{niche}'...")
        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([niche], timeframe=timeframe, geo="US")
        related = pytrends.related_queries()

        results = []
        if niche in related and related[niche].get("rising") is not None:
            df = related[niche]["rising"]
            for _, row in df.head(10).iterrows():
                results.append({
                    "keyword": str(row.get("query", "")),
                    "value": int(row.get("value", 0)),
                    "source": "google_trends",
                })
        elif niche in related and related[niche].get("top") is not None:
            df = related[niche]["top"]
            for _, row in df.head(10).iterrows():
                results.append({
                    "keyword": str(row.get("query", "")),
                    "value": int(row.get("value", 0)),
                    "source": "google_trends",
                })

        db_module.set_cached_trends("google_trends", niche, results)
        print(f"  [TRENDS] Google Trends: {len(results)} topics found")
        return results

    except Exception as e:
        print(f"  [WARN] Google Trends failed: {e}")
        return []


# ── REDDIT ────────────────────────────────────────────────────────────────────

def get_reddit_trends(subreddits: list = None, limit: int = 10) -> list:
    """
    Fetch top posts from relevant subreddits using praw.

    Uses read-only mode (no auth needed for public subs) if client credentials
    are not set. Caches per subreddit for 24 hours.

    Returns list of {"title": str, "score": int, "url": str, "source": "reddit",
                     "subreddit": str}.
    """
    if subreddits is None:
        subreddits = [s.strip() for s in REDDIT_SUBREDDITS.split(",") if s.strip()]

    if not subreddits:
        return []

    try:
        import praw
    except ImportError:
        print("  [WARN] praw not installed. Run: pip install praw")
        return []

    cache_key = ",".join(sorted(subreddits))
    from . import db as db_module
    cached = db_module.get_cached_trends("reddit", cache_key)
    if cached is not None:
        print(f"  [TRENDS] Reddit (cached): {len(cached)} posts")
        return cached

    try:
        print(f"  [TRENDS] Fetching Reddit trends from r/{', r/'.join(subreddits)}...")

        # Reddit requires credentials even for read-only in recent praw versions
        # Use a read-only instance or fall back to requests-based scraping
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
                read_only=True,
            )
        else:
            # Anonymous read via requests fallback
            return _reddit_fallback_scrape(subreddits, limit, db_module, cache_key)

        results = []
        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.hot(limit=limit):
                    if not post.stickied:
                        results.append({
                            "title": post.title,
                            "score": post.score,
                            "url": f"https://reddit.com{post.permalink}",
                            "source": "reddit",
                            "subreddit": sub_name,
                        })
            except Exception as e:
                print(f"  [WARN] Reddit r/{sub_name} failed: {e}")
                continue

        db_module.set_cached_trends("reddit", cache_key, results)
        print(f"  [TRENDS] Reddit: {len(results)} posts found")
        return results

    except Exception as e:
        print(f"  [WARN] Reddit trends failed: {e}")
        return []


def _reddit_fallback_scrape(subreddits: list, limit: int,
                             db_module, cache_key: str) -> list:
    """Fallback: scrape Reddit JSON API without praw credentials."""
    import requests
    import time

    results = []
    headers = {"User-Agent": REDDIT_USER_AGENT}
    for sub_name in subreddits[:3]:  # limit to 3 subs without auth
        try:
            url = f"https://www.reddit.com/r/{sub_name}/hot.json?limit={limit}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    p = post.get("data", {})
                    if not p.get("stickied"):
                        results.append({
                            "title": p.get("title", ""),
                            "score": p.get("score", 0),
                            "url": f"https://reddit.com{p.get('permalink', '')}",
                            "source": "reddit",
                            "subreddit": sub_name,
                        })
            time.sleep(1)  # be polite to Reddit's API
        except Exception as e:
            print(f"  [WARN] Reddit fallback r/{sub_name}: {e}")
            continue

    if results:
        db_module.set_cached_trends("reddit", cache_key, results)
    print(f"  [TRENDS] Reddit (no-auth): {len(results)} posts found")
    return results


# ── RSS FEEDS ─────────────────────────────────────────────────────────────────

def get_rss_trends(feeds: list = None) -> list:
    """
    Pull latest article titles from RSS feeds using feedparser.

    Returns list of {"title": str, "published": str, "url": str, "source": "rss",
                     "feed_url": str}.
    """
    if feeds is None:
        feeds = [f.strip() for f in RSS_FEEDS.split(",") if f.strip()]

    if not feeds:
        return []

    try:
        import feedparser
    except ImportError:
        print("  [WARN] feedparser not installed. Run: pip install feedparser")
        return []

    results = []
    for feed_url in feeds[:5]:  # cap at 5 feeds
        from . import db as db_module
        cached = db_module.get_cached_trends("rss", feed_url)
        if cached:
            results.extend(cached)
            continue
        try:
            print(f"  [TRENDS] Fetching RSS: {feed_url[:60]}...")
            feed = feedparser.parse(feed_url)
            feed_results = []
            for entry in feed.entries[:10]:
                feed_results.append({
                    "title": entry.get("title", ""),
                    "published": entry.get("published", ""),
                    "url": entry.get("link", ""),
                    "source": "rss",
                    "feed_url": feed_url,
                })
            db_module.set_cached_trends("rss", feed_url, feed_results)
            results.extend(feed_results)
        except Exception as e:
            print(f"  [WARN] RSS feed {feed_url}: {e}")

    print(f"  [TRENDS] RSS: {len(results)} articles found")
    return results


# ── AI IDEA GENERATION ────────────────────────────────────────────────────────

def generate_ideas(niche: str, trend_data: list = None,
                   top_posts: list = None, count: int = 5) -> list:
    """
    Use Claude to brainstorm content ideas based on trends and past performance.

    Falls back to generating ideas directly from trend headlines if Claude unavailable.

    Returns list of dicts: {"title": str, "hook": str, "platforms": list,
                            "trend_source": str, "trend_keyword": str}.
    """
    trend_data = trend_data or []
    top_posts = top_posts or []

    # Build context sections
    trend_lines = []
    for t in trend_data[:15]:
        kw = t.get("keyword") or t.get("title") or ""
        src = t.get("source", "")
        if kw:
            trend_lines.append(f"- {kw} [{src}]")

    top_lines = []
    for p in top_posts[:5]:
        title = p.get("idea_title", "")
        eng = p.get("total_engagement", 0)
        platform = p.get("platform", "")
        if title:
            top_lines.append(f"- \"{title}\" → {eng} engagements on {platform}")

    trend_section = "\n".join(trend_lines) or "(no trend data available)"
    top_section = "\n".join(top_lines) or "(no past posts yet)"

    prompt = f"""You are a content strategist for "{BRAND_NAME}", a {niche} brand.

Current trending topics related to our niche:
{trend_section}

Past top-performing content (by engagement):
{top_section}

Generate {count} fresh content ideas for social media posts (Instagram, Facebook, email newsletter).

For each idea provide:
1. A compelling title (5-10 words)
2. A one-sentence hook/angle that makes people want to read more
3. Which platforms it's best for (instagram, facebook, email — can be all)
4. The trend or topic it connects to

Format each idea as:
IDEA [N]:
TITLE: [title]
HOOK: [hook]
PLATFORMS: [comma-separated: instagram, facebook, email]
TREND: [trend keyword or topic]
---

Focus on practical, actionable content that provides genuine value.
Avoid generic motivational posts. Make it specific to {niche}."""

    ai_ideas = []
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "sk-ant-REPLACE_ME":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=CONTENT_MODEL,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            ai_ideas = _parse_ideas_response(raw, count)
            if ai_ideas:
                print(f"  [IDEAS] Claude generated {len(ai_ideas)} ideas")
        except Exception as e:
            print(f"  [WARN] Claude idea generation failed: {e}")

    # Fallback: convert trend headlines directly into ideas
    if not ai_ideas:
        print("  [IDEAS] Using trend headlines as idea seeds (no Claude API)")
        for item in (trend_data or [])[:count]:
            kw = item.get("keyword") or item.get("title") or ""
            if kw:
                ai_ideas.append({
                    "title": kw,
                    "hook": f"What {kw} means for {niche} professionals.",
                    "platforms": ["instagram", "facebook", "email"],
                    "trend_source": item.get("source", "unknown"),
                    "trend_keyword": kw,
                })

    return ai_ideas[:count]


def _parse_ideas_response(raw: str, expected: int) -> list:
    """Parse Claude's idea response format into list of dicts."""
    ideas = []
    blocks = [b.strip() for b in raw.split("---") if b.strip()]
    for block in blocks:
        if "TITLE:" not in block:
            continue
        idea = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("TITLE:"):
                idea["title"] = line[6:].strip()
            elif line.startswith("HOOK:"):
                idea["hook"] = line[5:].strip()
            elif line.startswith("PLATFORMS:"):
                raw_p = line[10:].strip().lower()
                platforms = [p.strip() for p in raw_p.split(",")
                             if p.strip() in ("instagram", "facebook", "email")]
                idea["platforms"] = platforms or ["instagram", "facebook", "email"]
            elif line.startswith("TREND:"):
                idea["trend_keyword"] = line[6:].strip()
                idea["trend_source"] = "ai_generated"

        if idea.get("title"):
            ideas.append(idea)
        if len(ideas) >= expected:
            break

    return ideas


# ── INTERACTIVE SESSION ───────────────────────────────────────────────────────

def run_idea_session(niche: str = None) -> int | None:
    """
    Interactive idea generation session.

    1. Pull trends from all sources
    2. Show AI-suggested ideas numbered
    3. User picks a number, enters manual idea, or quits
    4. Saves approved idea to DB, returns idea_id

    Returns idea_id (int) or None if user quit/skipped.
    """
    from . import db as db_module

    niche = niche or SOCIAL_NICHE
    print(f"\n{'='*60}")
    print(f"IDEA GENERATOR — Niche: {niche}")
    print(f"{'='*60}")

    # Pull trends
    print("\n[STEP 1] Fetching trending topics...")
    trends = []
    trends.extend(get_google_trends(niche))
    trends.extend(get_reddit_trends())
    trends.extend(get_rss_trends())

    if not trends:
        print("  No trend data found. Using manual input mode.")

    # Past top posts for seeding
    top_posts = db_module.get_top_posts(limit=5)

    # Generate ideas
    print("\n[STEP 2] Generating content ideas...")
    ideas = generate_ideas(niche, trend_data=trends, top_posts=top_posts, count=5)

    if not ideas:
        ideas = [
            {"title": "Enter your own idea below", "hook": "",
             "platforms": ["instagram", "facebook", "email"],
             "trend_source": "manual", "trend_keyword": ""},
        ]

    # Display ideas
    print(f"\n{'='*60}")
    print("SUGGESTED CONTENT IDEAS")
    print(f"{'='*60}")
    for i, idea in enumerate(ideas, 1):
        print(f"\n  [{i}] {idea['title']}")
        if idea.get("hook"):
            print(f"      Hook: {idea['hook']}")
        if idea.get("trend_keyword"):
            print(f"      Trend: {idea['trend_keyword']} ({idea.get('trend_source','')})")

    print(f"\n{'─'*60}")
    print("Options: [1-5] Select idea  [m] Type your own  [q] Quit")

    # User input loop
    while True:
        try:
            choice = input("\nYour choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[CANCELLED]")
            return None

        if choice == "q":
            print("[QUIT] No idea saved.")
            return None

        if choice == "m":
            try:
                title = input("Idea title: ").strip()
                if not title:
                    print("Title cannot be empty.")
                    continue
                hook = input("Hook/angle (optional, press Enter to skip): ").strip()
                selected = {
                    "title": title,
                    "hook": hook,
                    "platforms": ["instagram", "facebook", "email"],
                    "trend_source": "manual",
                    "trend_keyword": "",
                }
            except (EOFError, KeyboardInterrupt):
                print("\n[CANCELLED]")
                return None
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ideas):
                selected = ideas[idx]
                break
            print(f"Please enter a number between 1 and {len(ideas)}")
        except ValueError:
            print("Invalid input. Enter a number, 'm', or 'q'.")

    # Save to DB
    idea_id = db_module.insert_idea(
        title=selected["title"],
        hook=selected.get("hook", ""),
        niche=niche,
        platforms=selected.get("platforms", ["instagram", "facebook", "email"]),
        trend_source=selected.get("trend_source"),
        trend_keyword=selected.get("trend_keyword"),
    )
    db_module.update_idea_status(idea_id, "approved")

    print(f"\n[SAVED] Idea #{idea_id}: \"{selected['title']}\"")
    print(f"  Run next: python tools/run_social.py --create --idea-id {idea_id}")

    return idea_id
