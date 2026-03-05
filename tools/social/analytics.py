"""
analytics.py — Fetch engagement metrics from Meta Insights API and generate reports.

Fetches:
  - Facebook post metrics: impressions, reach, reactions, comments, shares, clicks
  - Instagram media metrics: likes, comments, saves, reach, impressions

Stores snapshots in SQLite engagement table for trend analysis.
Report shows top posts, platform averages, and 30-day engagement trend.
"""

import os
import requests
from dotenv import load_dotenv
from . import db as db_module
from .utils import format_table

load_dotenv()

META_GRAPH_URL = "https://graph.facebook.com/v21.0"
META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")


# ── METRIC FETCHERS ───────────────────────────────────────────────────────────

def fetch_facebook_post_insights(post_id: str, access_token: str) -> dict:
    """
    Fetch engagement metrics for a Facebook post.

    Returns:
        dict with metric keys or {} on failure.
    """
    metrics = [
        "post_impressions",
        "post_impressions_unique",
        "post_engaged_users",
        "post_clicks",
        "post_reactions_by_type_total",
    ]

    try:
        resp = requests.get(
            f"{META_GRAPH_URL}/{post_id}/insights",
            params={
                "metric": ",".join(metrics),
                "access_token": access_token,
            },
            timeout=15
        )
        if resp.status_code != 200:
            return {}

        data = resp.json().get("data", [])
        result = {}
        for item in data:
            name = item.get("name", "")
            values = item.get("values", [{}])
            val = values[0].get("value", 0) if values else 0

            if name == "post_impressions":
                result["impressions"] = val if isinstance(val, int) else 0
            elif name == "post_impressions_unique":
                result["reach"] = val if isinstance(val, int) else 0
            elif name == "post_engaged_users":
                result["clicks"] = val if isinstance(val, int) else 0
            elif name == "post_reactions_by_type_total":
                if isinstance(val, dict):
                    result["likes"] = sum(val.values())
                else:
                    result["likes"] = 0

        # Fetch comments count separately
        try:
            comment_resp = requests.get(
                f"{META_GRAPH_URL}/{post_id}",
                params={
                    "fields": "comments.summary(true)",
                    "access_token": access_token,
                },
                timeout=10
            )
            if comment_resp.status_code == 200:
                summary = comment_resp.json().get("comments", {}).get("summary", {})
                result["comments"] = summary.get("total_count", 0)
        except Exception:
            pass

        return result

    except Exception as e:
        print(f"  [ANALYTICS] Facebook insights error for {post_id}: {e}")
        return {}


def fetch_instagram_media_insights(media_id: str, access_token: str) -> dict:
    """
    Fetch engagement metrics for an Instagram post.

    Returns:
        dict with metric keys or {} on failure.
    """
    metrics = ["likes", "comments", "saved", "impressions", "reach", "shares"]

    try:
        resp = requests.get(
            f"{META_GRAPH_URL}/{media_id}/insights",
            params={
                "metric": ",".join(metrics),
                "access_token": access_token,
            },
            timeout=15
        )
        if resp.status_code != 200:
            return {}

        data = resp.json().get("data", [])
        result = {}
        metric_map = {
            "likes": "likes",
            "comments": "comments",
            "saved": "saves",
            "impressions": "impressions",
            "reach": "reach",
            "shares": "shares",
        }

        for item in data:
            name = item.get("name", "")
            val = item.get("values", [{}])[0].get("value", 0) if item.get("values") else 0
            if name in metric_map:
                result[metric_map[name]] = val if isinstance(val, int) else 0

        return result

    except Exception as e:
        print(f"  [ANALYTICS] Instagram insights error for {media_id}: {e}")
        return {}


# ── FETCH ALL ENGAGEMENT ──────────────────────────────────────────────────────

def fetch_all_engagement() -> int:
    """
    Fetch engagement for all posted platform_posts records.

    Returns:
        Count of successfully updated posts.
    """
    token = os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)
    if not token or token == "REPLACE_ME":
        print("  [ANALYTICS] META_PAGE_ACCESS_TOKEN not set. Skipping engagement fetch.")
        return 0

    posted = db_module.get_posted_platform_posts()
    if not posted:
        print("  [ANALYTICS] No posted content found to fetch insights for.")
        return 0

    print(f"  [ANALYTICS] Fetching insights for {len(posted)} posts...")
    updated = 0

    for pp in posted:
        platform = pp.get("platform", "")
        platform_post_id = pp.get("platform_post_id", "")

        if not platform_post_id:
            continue

        metrics = {}
        try:
            if platform == "facebook":
                metrics = fetch_facebook_post_insights(platform_post_id, token)
            elif platform == "instagram":
                metrics = fetch_instagram_media_insights(platform_post_id, token)
            else:
                continue  # email analytics not tracked via API

            if metrics:
                db_module.insert_engagement(pp["id"], **metrics)
                updated += 1
                total_eng = metrics.get("likes", 0) + metrics.get("comments", 0)
                print(f"    {platform} {platform_post_id[:15]}... → {total_eng} engagements")

        except Exception as e:
            print(f"    [WARN] {platform} {platform_post_id}: {e}")

    print(f"  [ANALYTICS] Updated {updated}/{len(posted)} posts")
    return updated


# ── REPORT ────────────────────────────────────────────────────────────────────

def generate_report() -> str:
    """
    Generate and print an engagement summary report.

    Returns the report as a string.
    """
    rows = db_module.get_engagement_summary()

    if not rows:
        msg = (
            "\n  No engagement data yet.\n"
            "  Post some content, then run: python tools/run_social.py --analytics\n"
        )
        print(msg)
        return msg

    # Sort by total engagement descending
    for row in rows:
        row["total_eng"] = (
            row.get("likes", 0) +
            row.get("comments", 0) +
            row.get("shares", 0) +
            row.get("saves", 0)
        )

    rows_sorted = sorted(rows, key=lambda r: r["total_eng"], reverse=True)

    # Platform averages
    platform_stats = {}
    for row in rows:
        p = row.get("platform") or "unknown"
        if p not in platform_stats:
            platform_stats[p] = {"count": 0, "total_eng": 0, "total_reach": 0}
        platform_stats[p]["count"] += 1
        platform_stats[p]["total_eng"] += row["total_eng"]
        platform_stats[p]["total_reach"] += row.get("reach", 0) or row.get("email_opens", 0)

    lines = []
    lines.append("\n" + "="*65)
    lines.append("SOCIAL MEDIA ENGAGEMENT REPORT")
    lines.append("="*65)

    # Top posts table
    lines.append("\nTOP POSTS BY ENGAGEMENT")
    lines.append("-"*65)
    table_rows = []
    for r in rows_sorted[:10]:
        title = (r.get("idea_title") or "Untitled")[:30]
        platform = (r.get("platform") or "")[:10]
        eng = r["total_eng"]
        reach = r.get("reach") or r.get("email_opens", 0)
        posted = (r.get("posted_at") or "")[:10]
        table_rows.append([title, platform, eng, reach, posted])

    lines.append(format_table(
        ["Title", "Platform", "Engagement", "Reach", "Posted"],
        table_rows,
        col_widths=[32, 12, 12, 8, 12]
    ))

    # Platform averages
    if platform_stats:
        lines.append("\nAVERAGE BY PLATFORM")
        lines.append("-"*65)
        avg_rows = []
        for platform, stats in sorted(platform_stats.items()):
            count = stats["count"]
            avg_eng = stats["total_eng"] / count if count else 0
            avg_reach = stats["total_reach"] / count if count else 0
            avg_rows.append([platform, count, f"{avg_eng:.1f}", f"{avg_reach:.0f}"])
        lines.append(format_table(
            ["Platform", "Posts", "Avg Engagement", "Avg Reach"],
            avg_rows,
            col_widths=[15, 7, 16, 12]
        ))

    lines.append("\n" + "="*65)
    report = "\n".join(lines)
    print(report)
    return report
