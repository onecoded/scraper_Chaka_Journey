"""
poster_meta.py — Post content to Facebook and Instagram via Meta Graph API.

Uses the same Facebook App and Page Access Token for both platforms.

Instagram notes:
  - Requires Business or Creator account connected to a Facebook Page
  - Image posting requires a publicly accessible URL (not a local file)
  - Strategy: upload image to FB Page first (unpublished) → get temporary URL → use for IG
  - Text-only posts are NOT supported on Instagram (will skip IG if no image/video)

Facebook notes:
  - Supports text-only, photo, and video posts
  - Simpler API than Instagram — direct file upload supported

Meta Graph API docs:
  - Facebook: https://developers.facebook.com/docs/graph-api/reference/post
  - Instagram: https://developers.facebook.com/docs/instagram-api/reference/ig-user/media
"""

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

META_GRAPH_URL = "https://graph.facebook.com/v21.0"
META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
META_IG_USER_ID = os.getenv("META_IG_USER_ID", "")


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _graph_get(endpoint: str, params: dict, token: str = None) -> dict:
    """Make a GET request to the Meta Graph API."""
    if token:
        params["access_token"] = token
    resp = requests.get(f"{META_GRAPH_URL}/{endpoint}", params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Graph API GET {endpoint} failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def _graph_post(endpoint: str, data: dict, files: dict = None,
                token: str = None) -> dict:
    """Make a POST request to the Meta Graph API."""
    if token:
        data["access_token"] = token
    resp = requests.post(
        f"{META_GRAPH_URL}/{endpoint}",
        data=data,
        files=files,
        timeout=120
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Graph API POST {endpoint} failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def _validate_credentials() -> None:
    """Raise RuntimeError if required env vars are not set."""
    token = os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)
    page_id = os.getenv("META_PAGE_ID", META_PAGE_ID)
    if not token or token == "REPLACE_ME":
        raise RuntimeError(
            "META_PAGE_ACCESS_TOKEN not set. Run: python tools/run_social.py --refresh-token"
        )
    if not page_id or page_id == "REPLACE_ME":
        raise RuntimeError(
            "META_PAGE_ID not set. Run: python tools/run_social.py --refresh-token"
        )


# ── FACEBOOK POSTING ──────────────────────────────────────────────────────────

def post_facebook_text(message: str, page_id: str = None,
                       access_token: str = None) -> dict:
    """
    Post a text-only message to the Facebook Page.

    Returns:
        dict with 'id' (post ID) key.
    """
    page_id = page_id or os.getenv("META_PAGE_ID", META_PAGE_ID)
    token = access_token or os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)
    return _graph_post(f"{page_id}/feed", {"message": message}, token=token)


def post_facebook_photo(message: str, image_path: Path,
                        page_id: str = None, access_token: str = None) -> dict:
    """
    Post a photo with caption to the Facebook Page.

    Returns:
        dict with 'post_id' key.
    """
    page_id = page_id or os.getenv("META_PAGE_ID", META_PAGE_ID)
    token = access_token or os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)

    with open(image_path, "rb") as f:
        result = _graph_post(
            f"{page_id}/photos",
            {"caption": message},
            files={"source": (image_path.name, f, "image/png")},
            token=token
        )
    return result


def post_facebook_video(description: str, video_path: Path,
                        page_id: str = None, access_token: str = None) -> dict:
    """
    Upload a video to the Facebook Page.

    Returns:
        dict with 'id' key.
    """
    page_id = page_id or os.getenv("META_PAGE_ID", META_PAGE_ID)
    token = access_token or os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)

    with open(video_path, "rb") as f:
        result = _graph_post(
            f"{page_id}/videos",
            {"description": description},
            files={"source": (video_path.name, f, "video/mp4")},
            token=token
        )
    return result


def post_to_facebook(message: str, image_path: Path = None,
                     video_path: Path = None,
                     page_id: str = None,
                     access_token: str = None) -> dict:
    """
    Orchestrator: post to Facebook with the best available content type.
    Priority: video > photo > text.

    Returns:
        dict with keys: platform, post_id, status, error (optional)
    """
    page_id = page_id or os.getenv("META_PAGE_ID", META_PAGE_ID)
    token = access_token or os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)

    try:
        _validate_credentials()

        if video_path and Path(video_path).exists():
            print("  [FACEBOOK] Uploading video...")
            result = post_facebook_video(message, Path(video_path), page_id, token)
            post_id = result.get("id", "")
        elif image_path and Path(image_path).exists():
            print("  [FACEBOOK] Uploading photo...")
            result = post_facebook_photo(message, Path(image_path), page_id, token)
            post_id = result.get("post_id") or result.get("id", "")
        else:
            print("  [FACEBOOK] Posting text...")
            result = post_facebook_text(message, page_id, token)
            post_id = result.get("id", "")

        fb_url = f"https://facebook.com/{post_id.replace('_', '/posts/')}" if post_id else None
        print(f"  [FACEBOOK] Posted successfully (ID: {post_id})")
        return {"platform": "facebook", "post_id": post_id, "status": "posted", "url": fb_url}

    except Exception as e:
        print(f"  [FACEBOOK] Failed: {e}")
        return {"platform": "facebook", "post_id": None, "status": "failed", "error": str(e)}


# ── INSTAGRAM POSTING ─────────────────────────────────────────────────────────

def _upload_photo_to_fb_unpublished(image_path: Path, page_id: str,
                                     token: str) -> str:
    """
    Upload an image to Facebook Page as unpublished photo.
    Returns the photo ID, which provides a temporary publicly accessible URL
    that Meta's Instagram API can access.
    """
    with open(image_path, "rb") as f:
        result = _graph_post(
            f"{page_id}/photos",
            {"published": "false"},  # don't publish to FB timeline
            files={"source": (image_path.name, f, "image/png")},
            token=token
        )
    return result.get("id", "")


def _get_photo_url(photo_id: str, token: str) -> str:
    """Get the public URL of a Facebook photo by ID."""
    result = _graph_get(photo_id, {"fields": "images"}, token=token)
    images = result.get("images", [])
    if images:
        # Use the largest available image
        return images[0].get("source", "")
    return ""


def create_instagram_image_container(caption: str, image_path: Path,
                                      ig_user_id: str, token: str,
                                      page_id: str) -> str:
    """
    Create an Instagram media container for an image post.

    Strategy: Upload image to FB (unpublished) → get URL → create IG container.

    Returns:
        creation_id (container ID) for use with publish_instagram_container().
    """
    # Upload to Facebook first to get a public URL
    print("  [INSTAGRAM] Uploading image to Facebook (getting public URL)...")
    photo_id = _upload_photo_to_fb_unpublished(image_path, page_id, token)
    if not photo_id:
        raise RuntimeError("Failed to upload image to Facebook for Instagram use")

    image_url = _get_photo_url(photo_id, token)
    if not image_url:
        raise RuntimeError(f"Could not get URL for Facebook photo ID {photo_id}")

    print(f"  [INSTAGRAM] Creating media container...")
    result = _graph_post(
        f"{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
        },
        token=token
    )
    creation_id = result.get("id")
    if not creation_id:
        raise RuntimeError(f"No creation_id in IG media response: {result}")
    return creation_id


def create_instagram_reel_container(caption: str, video_path: Path,
                                     ig_user_id: str, token: str) -> str:
    """
    Create an Instagram Reels media container.

    Returns:
        creation_id for publishing.
    """
    # For video, we need to upload to IG's video endpoint directly
    print("  [INSTAGRAM] Uploading Reel...")
    with open(video_path, "rb") as f:
        result = _graph_post(
            f"{ig_user_id}/media",
            {
                "media_type": "REELS",
                "caption": caption,
                "share_to_feed": "true",
            },
            files={"video_file": (video_path.name, f, "video/mp4")},
            token=token
        )
    creation_id = result.get("id")
    if not creation_id:
        raise RuntimeError(f"No creation_id in IG Reel response: {result}")
    return creation_id


def publish_instagram_container(creation_id: str, ig_user_id: str,
                                  token: str, max_wait_seconds: int = 60) -> dict:
    """
    Publish an Instagram media container.

    For Reels: polls status until ready before publishing (videos need processing time).

    Returns:
        dict with 'id' (post ID).
    """
    # For video containers, wait for processing
    for _ in range(max_wait_seconds // 5):
        status_result = _graph_get(
            creation_id,
            {"fields": "status_code"},
            token=token
        )
        status = status_result.get("status_code", "FINISHED")
        if status == "FINISHED":
            break
        elif status == "ERROR":
            raise RuntimeError(f"Instagram media processing failed: {status_result}")
        time.sleep(5)

    result = _graph_post(
        f"{ig_user_id}/media_publish",
        {"creation_id": creation_id},
        token=token
    )
    return result


def post_to_instagram(caption: str, image_path: Path = None,
                      video_path: Path = None,
                      ig_user_id: str = None,
                      page_id: str = None,
                      access_token: str = None) -> dict:
    """
    Orchestrator: post to Instagram.

    Instagram does not support text-only posts.
    If no image or video is available, returns a 'skipped' result.

    Returns:
        dict with keys: platform, post_id, status, url, error (optional)
    """
    ig_user_id = ig_user_id or os.getenv("META_IG_USER_ID", META_IG_USER_ID)
    page_id = page_id or os.getenv("META_PAGE_ID", META_PAGE_ID)
    token = access_token or os.getenv("META_PAGE_ACCESS_TOKEN", META_PAGE_ACCESS_TOKEN)

    if not ig_user_id or ig_user_id == "REPLACE_ME":
        return {
            "platform": "instagram",
            "post_id": None,
            "status": "skipped",
            "error": "META_IG_USER_ID not set. Connect Instagram to your Facebook Page first."
        }

    if not image_path and not video_path:
        return {
            "platform": "instagram",
            "post_id": None,
            "status": "skipped",
            "error": "Instagram requires an image or video. No media available for this post."
        }

    try:
        _validate_credentials()

        if video_path and Path(video_path).exists():
            creation_id = create_instagram_reel_container(
                caption, Path(video_path), ig_user_id, token
            )
        elif image_path and Path(image_path).exists():
            creation_id = create_instagram_image_container(
                caption, Path(image_path), ig_user_id, token, page_id
            )
        else:
            return {
                "platform": "instagram",
                "post_id": None,
                "status": "skipped",
                "error": "Media files not found on disk."
            }

        result = publish_instagram_container(creation_id, ig_user_id, token)
        post_id = result.get("id", "")
        ig_url = f"https://www.instagram.com/p/{post_id}/" if post_id else None
        print(f"  [INSTAGRAM] Posted successfully (ID: {post_id})")
        return {"platform": "instagram", "post_id": post_id, "status": "posted", "url": ig_url}

    except Exception as e:
        print(f"  [INSTAGRAM] Failed: {e}")
        return {"platform": "instagram", "post_id": None, "status": "failed", "error": str(e)}
