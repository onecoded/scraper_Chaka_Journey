"""
social/__init__.py — Public orchestration API for the social media cross-poster.

Exposes:
  run_idea_session()        — interactive idea generation
  run_content_creation()    — generate all content for an approved idea
  run_post()                — post content to one or more platforms
  run_analytics_fetch()     — fetch engagement from Meta API
  run_report()              — print engagement report

All functions follow the same graceful-degradation pattern:
  - Each content type (image, audio, video) is optional
  - Platform failures don't block other platforms
  - All errors are logged to the posts.error_log field
"""

import os
from pathlib import Path
from datetime import datetime

from . import db as db_module
from .utils import ensure_dirs, IMAGES_DIR, AUDIO_DIR, VIDEO_DIR
from .trends import run_idea_session
from .analytics import fetch_all_engagement, generate_report
from .subscribers import manage_subscribers


def run_content_creation(idea_id: int, skip_image: bool = False) -> int | None:
    """
    Orchestrate full content generation for an approved idea.

    Steps:
      1. Load idea from DB
      2. Generate text (caption IG, caption FB, hashtags, email article) — REQUIRED
      3. Generate image via HuggingFace (optional)
      4. Generate audio via MusicGen (optional, needs HF_TOKEN)
      5. Create video slideshow via ffmpeg (optional, needs image + ffmpeg)
      6. Save post to DB

    Returns post_id on success, None if text generation fails.
    """
    ensure_dirs()
    db_module.init_db()

    idea = db_module.get_idea(idea_id)
    if not idea:
        print(f"[ERROR] Idea #{idea_id} not found. Run --list-ideas to see available ideas.")
        return None

    print(f"\n{'='*60}")
    print(f"CONTENT CREATION — Idea #{idea_id}")
    print(f"Topic: {idea['title']}")
    if idea.get("hook"):
        print(f"Angle: {idea['hook']}")
    print(f"{'='*60}")

    errors = []

    # ── STEP 1: Text generation (REQUIRED) ────────────────────────────────────
    print("\n[STEP 1] Generating text content...")
    try:
        from .content_text import generate_all_text
        texts = generate_all_text(idea)
    except Exception as e:
        print(f"[ERROR] Text generation failed: {e}")
        print("Cannot create a post without text content.")
        return None

    # ── STEP 2: Image generation (optional) ───────────────────────────────────
    image_path = None
    if not skip_image:
        print("\n[STEP 2] Generating image...")
        try:
            from .content_image import generate_image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_out = IMAGES_DIR / f"idea_{idea_id}_{timestamp}.png"
            image_path = generate_image(idea, img_out)
            if image_path is None:
                errors.append("Image generation failed or HF_TOKEN not set")
        except Exception as e:
            errors.append(f"Image error: {e}")
            print(f"  [WARN] Image failed: {e}")
    else:
        print("\n[STEP 2] Image skipped (--skip-image)")
        errors.append("Image skipped by user (--skip-image)")

    # ── STEP 3: Audio generation (optional) ───────────────────────────────────
    audio_path = None
    hf_audio_enabled = os.getenv("HF_AUDIO_ENABLED", "true").lower() == "true"
    if hf_audio_enabled and os.getenv("HF_TOKEN"):
        print("\n[STEP 3] Generating background music...")
        try:
            from .content_audio import build_mood_prompt, generate_audio
            mood = build_mood_prompt(idea)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_out = AUDIO_DIR / f"idea_{idea_id}_{timestamp}.wav"
            audio_path = generate_audio(mood, audio_out)
            if audio_path is None:
                errors.append("Audio generation failed")
        except Exception as e:
            errors.append(f"Audio error: {e}")
            print(f"  [WARN] Audio failed: {e}")
    else:
        print("\n[STEP 3] Audio skipped (HF_AUDIO_ENABLED=false or HF_TOKEN not set)")

    # ── STEP 4: Video creation (optional, requires image) ─────────────────────
    video_path = None
    if image_path:
        print("\n[STEP 4] Creating video slideshow...")
        try:
            from .content_video import create_slideshow_video, check_ffmpeg
            if check_ffmpeg():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_out = VIDEO_DIR / f"idea_{idea_id}_{timestamp}.mp4"
                video_path = create_slideshow_video(
                    image_paths=[image_path],
                    audio_path=audio_path,
                    output_path=video_out,
                    duration_per_image=5.0,
                    target_duration=30,
                )
                if video_path is None:
                    errors.append("Video creation failed (ffmpeg error)")
            else:
                errors.append("Video skipped — ffmpeg not installed")
                print("  [STEP 4] Video skipped (ffmpeg not found)")
        except Exception as e:
            errors.append(f"Video error: {e}")
            print(f"  [WARN] Video failed: {e}")
    else:
        print("\n[STEP 4] Video skipped (no image available)")

    # ── SAVE POST ─────────────────────────────────────────────────────────────
    post_id = db_module.insert_post(
        idea_id=idea_id,
        caption_instagram=texts.get("caption_instagram"),
        caption_facebook=texts.get("caption_facebook"),
        email_subject=texts.get("email_subject"),
        article_html=texts.get("article_html"),
        hashtags=texts.get("hashtags"),
        image_path=str(image_path) if image_path else None,
        audio_path=str(audio_path) if audio_path else None,
        video_path=str(video_path) if video_path else None,
        error_log=errors,
    )
    db_module.update_idea_status(idea_id, "created")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"CONTENT READY — Post #{post_id}")
    print(f"{'='*60}")
    print(f"  Text:      OK (IG caption, FB caption, email article)")
    print(f"  Image:     {'OK → ' + str(image_path.name) if image_path else 'SKIPPED'}")
    print(f"  Audio:     {'OK → ' + str(audio_path.name) if audio_path else 'SKIPPED'}")
    print(f"  Video:     {'OK → ' + str(video_path.name) if video_path else 'SKIPPED'}")
    if errors:
        print(f"  Warnings:  {len(errors)} (stored in DB)")
    print(f"\n  Run next: python tools/run_social.py --post --post-id {post_id}")

    return post_id


def run_post(post_id: int, platforms: list = None) -> dict:
    """
    Publish a post to one or more platforms.

    Args:
        post_id: ID from the posts table
        platforms: list of "instagram", "facebook", "email" (default: all)

    Returns:
        dict mapping platform → result dict.
    """
    if platforms is None:
        platforms = ["instagram", "facebook", "email"]

    ensure_dirs()
    db_module.init_db()

    post = db_module.get_post(post_id)
    if not post:
        print(f"[ERROR] Post #{post_id} not found.")
        return {}

    print(f"\n{'='*60}")
    print(f"PUBLISHING — Post #{post_id}")
    idea_title = "(unknown)"
    idea = db_module.get_idea(post.get("idea_id", 0)) if post.get("idea_id") else None
    if idea:
        idea_title = idea.get("title", "")
    print(f"Topic: {idea_title}")
    print(f"Platforms: {', '.join(platforms)}")
    print(f"{'='*60}")

    results = {}

    for platform in platforms:
        print(f"\n[POSTING] → {platform.upper()}")
        pp_id = db_module.insert_platform_post(post_id, platform)

        try:
            if platform == "instagram":
                from .poster_meta import post_to_instagram
                caption = post.get("caption_instagram") or ""
                hashtags = post.get("hashtags") or ""
                full_caption = f"{caption}\n\n{hashtags}".strip() if hashtags else caption
                result = post_to_instagram(
                    caption=full_caption,
                    image_path=Path(post["image_path"]) if post.get("image_path") else None,
                    video_path=Path(post["video_path"]) if post.get("video_path") else None,
                )

            elif platform == "facebook":
                from .poster_meta import post_to_facebook
                result = post_to_facebook(
                    message=post.get("caption_facebook") or "",
                    image_path=Path(post["image_path"]) if post.get("image_path") else None,
                    video_path=Path(post["video_path"]) if post.get("video_path") else None,
                )

            elif platform == "email":
                from .poster_email import post_to_email
                from .subscribers import list_subscribers
                subs = db_module.get_active_subscribers()
                result = post_to_email(
                    subscribers=subs,
                    subject=post.get("email_subject") or idea_title,
                    html_body=post.get("article_html") or "",
                )

            else:
                result = {"platform": platform, "status": "unknown_platform",
                          "error": f"Unknown platform: {platform}"}

            # Update DB record
            status = result.get("status", "unknown")
            db_module.update_platform_post(
                pp_id,
                status=status if status in ("posted", "failed", "skipped") else "posted",
                platform_post_id=result.get("post_id"),
                url=result.get("url"),
                error=result.get("error"),
            )
            results[platform] = result

        except Exception as e:
            error_str = str(e)
            print(f"  [ERROR] {platform}: {error_str}")
            db_module.update_platform_post(pp_id, "failed", error=error_str)
            results[platform] = {"platform": platform, "status": "failed", "error": error_str}

    # Update overall post status
    statuses = [r.get("status") for r in results.values()]
    if all(s in ("posted", "skipped") for s in statuses):
        db_module.update_post_status(post_id, "posted")
    elif any(s == "posted" for s in statuses):
        db_module.update_post_status(post_id, "partial")
    else:
        db_module.update_post_status(post_id, "failed")

    # Summary
    print(f"\n{'='*60}")
    print("POSTING COMPLETE")
    print(f"{'='*60}")
    for platform, result in results.items():
        status = result.get("status", "unknown")
        icon = "+" if status == "posted" else ("-" if status == "skipped" else "x")
        detail = result.get("url") or result.get("error") or ""
        if detail:
            detail = f"  ({detail[:60]})"
        print(f"  {icon} {platform:<12} {status}{detail}")

    return results


def run_analytics_fetch() -> int:
    """Fetch latest engagement from Meta API. Returns count of updated posts."""
    ensure_dirs()
    db_module.init_db()
    print("\n[ANALYTICS] Fetching engagement data from Meta...")
    return fetch_all_engagement()


def run_report() -> None:
    """Print engagement report."""
    ensure_dirs()
    db_module.init_db()
    generate_report()
