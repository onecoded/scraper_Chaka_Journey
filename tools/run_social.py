"""
run_social.py — Social media content pipeline: idea → content → post → track.

USAGE:
  python tools/run_social.py --ideas                         # Generate ideas interactively
  python tools/run_social.py --ideas --niche "your topic"    # Custom niche for this session
  python tools/run_social.py --create --idea-id 3            # Create content for idea #3
  python tools/run_social.py --create --idea-id 3 --skip-image  # Text only
  python tools/run_social.py --post --post-id 7              # Post to all platforms
  python tools/run_social.py --post --post-id 7 --platforms instagram facebook
  python tools/run_social.py --analytics                     # Fetch engagement from Meta
  python tools/run_social.py --report                        # Print engagement summary
  python tools/run_social.py --list-posts                    # List all posts + status
  python tools/run_social.py --list-ideas                    # List ideas + status
  python tools/run_social.py --add-subscriber email@x.com    # Add newsletter subscriber
  python tools/run_social.py --add-subscriber email@x.com --name "Jane Doe"
  python tools/run_social.py --remove-subscriber email@x.com
  python tools/run_social.py --import-subscribers /path/to/list.csv
  python tools/run_social.py --list-subscribers              # Show subscriber list
  python tools/run_social.py --refresh-token                 # Run Meta OAuth flow
  python tools/run_social.py --check-config                  # Verify all APIs reachable

WORKFLOW:
  1. Run --ideas to get AI-suggested content ideas based on trending topics
  2. Pick an idea → it's saved with status 'approved'
  3. Run --create --idea-id N to generate text + image + audio + video
  4. Run --post --post-id M to publish to Instagram, Facebook, and email
  5. Run --analytics periodically to fetch engagement data
  6. Run --ideas again — top performing posts seed the next batch of ideas

FIRST TIME SETUP:
  1. Add ANTHROPIC_API_KEY to .env (for AI text generation)
  2. Add HF_TOKEN to .env (for AI image/audio generation — free at huggingface.co)
  3. Set up Meta Developer App: https://developers.facebook.com/apps/
  4. Run --refresh-token to authenticate Facebook + Instagram
  5. Set SMTP_USER and SMTP_PASSWORD in .env for email newsletters
  6. Run --check-config to verify everything works
"""

import sys
import argparse
from pathlib import Path

# Add tools/ to Python path
sys.path.insert(0, str(Path(__file__).parent))

from social import db as db_module
from social.utils import ensure_dirs, format_table


def cmd_check_config() -> None:
    """Verify all APIs, dependencies, and credentials are configured."""
    import os
    import socket

    print(f"\n{'='*60}")
    print("CONFIGURATION CHECK")
    print(f"{'='*60}")

    checks = []

    # Claude API
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key and key != "sk-ant-REPLACE_ME":
        checks.append(("Claude API (text gen)", "OK", "key set"))
    else:
        checks.append(("Claude API (text gen)", "MISSING", "add ANTHROPIC_API_KEY to .env"))

    # HuggingFace
    hf_token = os.getenv("HF_TOKEN", "")
    hf_model = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    if hf_token:
        checks.append(("HuggingFace (image/audio)", "OK", hf_model.split("/")[-1]))
    else:
        checks.append(("HuggingFace (image/audio)", "MISSING",
                       "add HF_TOKEN to .env — free at huggingface.co"))

    # Meta / Facebook
    meta_token = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    meta_page = os.getenv("META_PAGE_ID", "")
    if meta_token and meta_token not in ("", "REPLACE_ME"):
        checks.append(("Facebook (Meta API)", "OK", f"Page ID: {meta_page or 'not set'}"))
    else:
        checks.append(("Facebook (Meta API)", "MISSING",
                       "run: python tools/run_social.py --refresh-token"))

    # Instagram
    ig_id = os.getenv("META_IG_USER_ID", "")
    if ig_id and ig_id != "REPLACE_ME":
        checks.append(("Instagram (Meta API)", "OK", f"IG User: {ig_id}"))
    else:
        checks.append(("Instagram (Meta API)", "NOT SET",
                       "run --refresh-token (connects to your FB Page)"))

    # Email / SMTP
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    if smtp_user and smtp_pass:
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        try:
            sock = socket.create_connection((smtp_host, smtp_port), timeout=5)
            sock.close()
            checks.append(("Email SMTP", "OK", f"{smtp_user} via {smtp_host}"))
        except Exception as e:
            checks.append(("Email SMTP", "UNREACHABLE", str(e)))
    else:
        checks.append(("Email SMTP", "MISSING",
                       "add SMTP_USER + SMTP_PASSWORD to .env"))

    # ffmpeg
    try:
        from social.content_video import get_ffmpeg_version
        ver = get_ffmpeg_version()
        if ver != "not found":
            checks.append(("ffmpeg (video)", "OK", f"v{ver}"))
        else:
            checks.append(("ffmpeg (video)", "MISSING",
                           "winget install ffmpeg  OR  https://ffmpeg.org/download.html"))
    except Exception:
        checks.append(("ffmpeg (video)", "ERROR", "import failed"))

    # Python packages
    for pkg, desc in [("pytrends", "Google Trends"), ("praw", "Reddit trends"),
                      ("feedparser", "RSS feeds"), ("PIL", "image processing")]:
        try:
            __import__(pkg)
            checks.append((f"{pkg} ({desc})", "OK", ""))
        except ImportError:
            checks.append((f"{pkg} ({desc})", "MISSING", f"pip install {pkg if pkg != 'PIL' else 'Pillow'}"))

    # Database
    try:
        ensure_dirs()
        db_module.init_db()
        stats = db_module.get_stats()
        checks.append(("SQLite database", "OK",
                       f"{stats['posts_total']} posts, {stats['subscribers_active']} subscribers"))
    except Exception as e:
        checks.append(("SQLite database", "ERROR", str(e)))

    # Print results
    print(f"\n  {'Component':<30} {'Status':<10} Notes")
    print("  " + "-" * 70)
    for component, status, note in checks:
        icon = "+" if status == "OK" else ("!" if status in ("MISSING", "NOT SET") else "x")
        print(f"  {icon} {component:<28} {status:<10} {note}")

    ok_count = sum(1 for _, s, _ in checks if s == "OK")
    total = len(checks)
    print(f"\n  {ok_count}/{total} checks passed")

    if ok_count < total:
        print("\n  NEXT STEPS:")
        missing = [(c, n) for c, s, n in checks if s != "OK"]
        for i, (component, note) in enumerate(missing, 1):
            print(f"    {i}. {component}: {note}")

    print(f"\n  Config file: .env")
    print(f"  Database:    .tmp/social.db")
    print(f"  Output:      .tmp/social/")


def cmd_list_posts() -> None:
    """List all posts with status."""
    posts = db_module.list_posts(limit=30)
    if not posts:
        print("\n  No posts yet.")
        print("  Start with: python tools/run_social.py --ideas")
        return

    print(f"\n{'='*60}")
    print("POSTS")
    print(f"{'='*60}")
    rows = []
    for p in posts:
        title = (p.get("idea_title") or "(no idea)")[:35]
        status = p.get("status", "")
        has_img = "Y" if p.get("image_path") else "N"
        has_vid = "Y" if p.get("video_path") else "N"
        created = (p.get("created_at") or "")[:10]
        rows.append([p["id"], title, status, has_img, has_vid, created])

    print(format_table(
        ["#", "Topic", "Status", "Img", "Vid", "Created"],
        rows,
        col_widths=[4, 37, 10, 5, 5, 12]
    ))


def cmd_list_ideas() -> None:
    """List all ideas with status."""
    ideas = db_module.list_ideas(limit=20)
    if not ideas:
        print("\n  No ideas yet.")
        print("  Run: python tools/run_social.py --ideas")
        return

    print(f"\n{'='*60}")
    print("IDEAS")
    print(f"{'='*60}")
    rows = []
    for idea in ideas:
        title = idea.get("title", "")[:45]
        status = idea.get("status", "")
        source = idea.get("trend_source") or "manual"
        created = (idea.get("created_at") or "")[:10]
        rows.append([idea["id"], title, status, source, created])

    print(format_table(
        ["#", "Title", "Status", "Source", "Created"],
        rows,
        col_widths=[4, 47, 10, 15, 12]
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Social media cross-poster: idea → content → post → analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/run_social.py --ideas
  python tools/run_social.py --create --idea-id 3
  python tools/run_social.py --post --post-id 7
  python tools/run_social.py --check-config
        """
    )

    # Idea generation
    parser.add_argument("--ideas", action="store_true",
                        help="Interactive idea generation session")
    parser.add_argument("--niche", default=None,
                        help="Override content niche for idea generation")

    # Content creation
    parser.add_argument("--create", action="store_true",
                        help="Generate content for an approved idea")
    parser.add_argument("--idea-id", type=int, metavar="N",
                        help="Idea ID to create content for (use with --create)")
    parser.add_argument("--skip-image", action="store_true",
                        help="Skip image/audio/video generation (text only)")

    # Posting
    parser.add_argument("--post", action="store_true",
                        help="Publish a post to platforms")
    parser.add_argument("--post-id", type=int, metavar="N",
                        help="Post ID to publish (use with --post)")
    parser.add_argument("--platforms", nargs="+",
                        choices=["instagram", "facebook", "email"],
                        default=["instagram", "facebook", "email"],
                        help="Platforms to post to (default: all)")

    # Analytics
    parser.add_argument("--analytics", action="store_true",
                        help="Fetch latest engagement from Meta API")
    parser.add_argument("--report", action="store_true",
                        help="Print engagement summary report")

    # Subscribers
    parser.add_argument("--add-subscriber", metavar="EMAIL",
                        help="Add an email subscriber")
    parser.add_argument("--remove-subscriber", metavar="EMAIL",
                        help="Remove an email subscriber")
    parser.add_argument("--import-subscribers", metavar="CSV_FILE",
                        help="Bulk import subscribers from CSV (email,first_name,last_name)")
    parser.add_argument("--list-subscribers", action="store_true",
                        help="List active email subscribers")
    parser.add_argument("--name", metavar="'First Last'",
                        help="Name for --add-subscriber")

    # Setup / auth
    parser.add_argument("--refresh-token", action="store_true",
                        help="Run Meta OAuth flow to get/refresh tokens")
    parser.add_argument("--check-config", action="store_true",
                        help="Verify all APIs, tokens, and dependencies")

    # List / info
    parser.add_argument("--list-posts", action="store_true",
                        help="List all posts with status")
    parser.add_argument("--list-ideas", action="store_true",
                        help="List all ideas with status")

    args = parser.parse_args()

    # Init DB on every run
    ensure_dirs()
    db_module.init_db()

    # Check token expiry warning
    try:
        from social.token_manager import check_token_expiry
        expiry = check_token_expiry()
        if expiry.get("warning"):
            print(f"\n  [WARNING] {expiry['message']}")
            print("  Run: python tools/run_social.py --refresh-token")
    except Exception:
        pass

    # ── DISPATCH ──────────────────────────────────────────────────────────────

    if args.check_config:
        cmd_check_config()

    elif args.refresh_token:
        from social.token_manager import run_oauth_flow
        run_oauth_flow()

    elif args.ideas:
        from social import run_idea_session
        run_idea_session(niche=args.niche)

    elif args.create:
        if not args.idea_id:
            print("[ERROR] --create requires --idea-id N")
            print("  Use --list-ideas to see available ideas.")
            sys.exit(1)
        from social import run_content_creation
        run_content_creation(args.idea_id, skip_image=args.skip_image)

    elif args.post:
        if not args.post_id:
            print("[ERROR] --post requires --post-id N")
            print("  Use --list-posts to see available posts.")
            sys.exit(1)
        from social import run_post
        run_post(args.post_id, platforms=args.platforms)

    elif args.analytics:
        from social import run_analytics_fetch
        run_analytics_fetch()

    elif args.report:
        from social import run_report
        run_report()

    elif args.add_subscriber:
        from social import manage_subscribers
        manage_subscribers("add", email=args.add_subscriber, name=args.name)

    elif args.remove_subscriber:
        from social import manage_subscribers
        manage_subscribers("remove", email=args.remove_subscriber)

    elif args.import_subscribers:
        from social import manage_subscribers
        manage_subscribers("import", csv_file=args.import_subscribers)

    elif args.list_subscribers:
        from social import manage_subscribers
        manage_subscribers("list")

    elif args.list_posts:
        cmd_list_posts()

    elif args.list_ideas:
        cmd_list_ideas()

    else:
        parser.print_help()
        print("\n  Quick start:")
        print("    1. python tools/run_social.py --check-config")
        print("    2. python tools/run_social.py --ideas")
        print("    3. python tools/run_social.py --create --idea-id N")
        print("    4. python tools/run_social.py --post --post-id M")


if __name__ == "__main__":
    main()
