"""
content_image.py — AI image generation via HuggingFace Inference API (free tier).

Default model: FLUX.1-schnell (black-forest-labs/FLUX.1-schnell)
Fallback model: Stable Diffusion XL (stabilityai/stable-diffusion-xl-base-1.0)

Both are available on HuggingFace's free Inference API — no GPU needed.

Free tier notes:
  - Rate limits apply; the retry logic handles 503 (model loading) and 429 (rate limit)
  - FLUX.1-schnell generates in ~4 steps; very fast once model is warm
  - Cold start can take 30–90 seconds; the retry logic waits appropriately
"""

import os
import io
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
FALLBACK_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONTENT_MODEL = os.getenv("EMAIL_MODEL", "claude-haiku-4-5-20251001")
SOCIAL_NICHE = os.getenv("SOCIAL_NICHE", "business acquisitions")
BRAND_NAME = os.getenv("SOCIAL_BRAND_NAME", os.getenv("BROKER_COMPANY", "Valar Brokers"))

HF_API_BASE = "https://api-inference.huggingface.co/models"


# ── PROMPT BUILDER ────────────────────────────────────────────────────────────

def build_image_prompt(idea: dict, style: str = None) -> str:
    """
    Convert an idea dict into an effective image generation prompt.

    Uses Claude to craft a refined visual prompt if available.
    Falls back to a structured template.

    Args:
        idea: dict with title, hook, niche keys
        style: optional style override (e.g. "illustration", "corporate photography")

    Returns:
        Image prompt string optimized for FLUX/SDXL.
    """
    title = idea.get("title", "")
    hook = idea.get("hook", "")
    niche = idea.get("niche") or SOCIAL_NICHE

    if style is None:
        style = "professional photography, clean minimal background"

    # Try Claude for a refined visual prompt
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "sk-ant-REPLACE_ME":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt_req = f"""Create a visual image generation prompt for this social media post topic.

Topic: {title}
Angle: {hook or title}
Brand niche: {niche}
Image style: {style}

Requirements:
- The image must be suitable for Instagram (1080x1080px square)
- Professional, eye-catching, no text overlays
- Photorealistic or clean illustration
- No watermarks, no people with distorted faces
- Bright, well-lit, high contrast

Return ONLY the image generation prompt (2-3 sentences). No explanation."""

            message = client.messages.create(
                model=CONTENT_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt_req}]
            )
            refined = message.content[0].text.strip()
            if len(refined) > 20:
                return refined
        except Exception:
            pass

    # Template fallback
    niche_visuals = {
        "business acquisitions": "modern corporate office, handshake deal, professional",
        "entrepreneurship": "startup workspace, entrepreneur, growth charts",
        "marketing": "colorful branding elements, creative workspace",
        "real estate": "modern architecture, property exterior, clean lines",
        "finance": "financial data visualization, modern office, wealth symbols",
    }

    visual_context = niche_visuals.get(niche.lower(), f"{niche} themed professional setting")
    return (
        f"Professional photography of {visual_context}. "
        f"Theme: {title}. "
        f"{style}, bright natural lighting, minimalist composition, "
        "no text, no watermarks, high resolution, Instagram-ready square format."
    )


# ── HF API CALLER ─────────────────────────────────────────────────────────────

def _call_hf_image_api(model_id: str, prompt: str, hf_token: str,
                        width: int = 1024, height: int = 1024,
                        max_retries: int = 3) -> bytes | None:
    """
    Call HuggingFace Inference API for image generation.

    Handles:
    - 503: model loading → retry after estimated_time (up to 90s)
    - 429: rate limit → wait 60s
    - 401: bad token → abort
    - Success: returns raw PNG/JPEG bytes

    Returns raw bytes or None on failure.
    """
    if not hf_token:
        print("  [WARN] HF_TOKEN not set. Skipping image generation.")
        print("         Get a free token at: huggingface.co → Settings → Access Tokens")
        return None

    url = f"{HF_API_BASE}/{model_id}"
    headers = {"Authorization": f"Bearer {hf_token}"}

    # Model-specific parameters
    if "FLUX" in model_id or "flux" in model_id:
        payload = {
            "inputs": prompt,
            "parameters": {
                "width": width,
                "height": height,
                "num_inference_steps": 4,   # FLUX.1-schnell optimized for 4 steps
                "guidance_scale": 0.0,      # FLUX.1-schnell uses 0.0
            }
        }
    else:  # SDXL and others
        payload = {
            "inputs": prompt,
            "parameters": {
                "width": width,
                "height": height,
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
            }
        }

    for attempt in range(max_retries):
        try:
            print(f"  [IMAGE] Calling HuggingFace ({model_id.split('/')[-1]})... attempt {attempt+1}")
            resp = requests.post(url, headers=headers, json=payload, timeout=180)

            if resp.status_code == 200:
                # Check it's actually image bytes not a JSON error
                content_type = resp.headers.get("content-type", "")
                if "image" in content_type or resp.content[:4] in (b"\x89PNG", b"\xff\xd8\xff"):
                    return resp.content
                else:
                    # Might be a JSON error in 200 response (some HF models do this)
                    try:
                        err = resp.json()
                        print(f"  [WARN] HF returned JSON instead of image: {err}")
                    except Exception:
                        pass
                    return None

            elif resp.status_code == 503:
                try:
                    wait_time = min(resp.json().get("estimated_time", 25), 90)
                except Exception:
                    wait_time = 25
                print(f"  [IMAGE] Model loading, waiting {wait_time:.0f}s...")
                time.sleep(wait_time)
                continue

            elif resp.status_code == 429:
                print("  [IMAGE] Rate limited, waiting 60s...")
                time.sleep(60)
                continue

            elif resp.status_code == 401:
                print("  [IMAGE] Invalid HF_TOKEN. Check your token at huggingface.co")
                return None

            elif resp.status_code == 404:
                print(f"  [IMAGE] Model {model_id} not found on HF Inference API.")
                return None

            else:
                print(f"  [IMAGE] HF API error {resp.status_code}: {resp.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(10)

        except requests.Timeout:
            print(f"  [IMAGE] Request timed out (attempt {attempt+1})")
            if attempt < max_retries - 1:
                time.sleep(5)
        except requests.RequestException as e:
            print(f"  [IMAGE] Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    print(f"  [IMAGE] All {max_retries} attempts failed for {model_id}")
    return None


# ── MAIN GENERATE FUNCTION ────────────────────────────────────────────────────

def generate_image(idea: dict, output_path: Path,
                   width: int = 1080, height: int = 1080,
                   custom_prompt: str = None) -> Path | None:
    """
    Generate an image for the given idea and save to output_path.

    Args:
        idea: dict with title, hook, niche keys
        output_path: where to save the PNG file
        width/height: image dimensions (default 1080x1080 for Instagram)
        custom_prompt: override the auto-generated prompt

    Returns:
        output_path on success, None on failure.
    """
    hf_token = HF_TOKEN
    if not hf_token:
        print("  [IMAGE] Skipped — HF_TOKEN not set in .env")
        return None

    prompt = custom_prompt or build_image_prompt(idea)
    print(f"  [IMAGE] Prompt: {prompt[:80]}...")

    # Try primary model
    image_bytes = _call_hf_image_api(
        HF_IMAGE_MODEL, prompt, hf_token, width=width, height=height
    )

    # Fallback to SDXL if primary fails
    if image_bytes is None and HF_IMAGE_MODEL != FALLBACK_MODEL:
        print(f"  [IMAGE] Primary model failed, trying fallback ({FALLBACK_MODEL.split('/')[-1]})...")
        image_bytes = _call_hf_image_api(
            FALLBACK_MODEL, prompt, hf_token, width=width, height=height
        )

    if image_bytes is None:
        return None

    # Save with Pillow (resize/compress if needed)
    try:
        from PIL import Image as PILImage

        img = PILImage.open(io.BytesIO(image_bytes))

        # Ensure it's exactly the right size for Instagram
        if img.size != (width, height):
            img = img.resize((width, height), PILImage.LANCZOS)

        # Convert to RGB (FLUX sometimes returns RGBA)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG", optimize=True)
        print(f"  [IMAGE] Saved: {output_path.name} ({img.size[0]}x{img.size[1]})")
        return output_path

    except ImportError:
        # Pillow not installed — save raw bytes
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(output_path), "wb") as f:
            f.write(image_bytes)
        print(f"  [IMAGE] Saved (raw): {output_path.name}")
        return output_path

    except Exception as e:
        print(f"  [IMAGE] Failed to save image: {e}")
        return None
