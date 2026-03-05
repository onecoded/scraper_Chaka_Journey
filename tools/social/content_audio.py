"""
content_audio.py — AI music generation via HuggingFace MusicGen (free tier).

Model: facebook/musicgen-small
  - Generates ~15-30 seconds of music from a text description
  - Available on HuggingFace Inference API free tier (rate-limited)
  - Returns WAV audio bytes

This module is OPTIONAL — controlled by HF_AUDIO_ENABLED env var.
If disabled or if generation fails, the video will be silent (no audio).
"""

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_AUDIO_ENABLED = os.getenv("HF_AUDIO_ENABLED", "true").lower() == "true"
SOCIAL_NICHE = os.getenv("SOCIAL_NICHE", "business acquisitions")

MUSICGEN_MODEL = "facebook/musicgen-small"
HF_API_BASE = "https://api-inference.huggingface.co/models"

# Niche → mood mapping for music prompts
NICHE_MOOD_MAP = {
    "business acquisitions": "professional corporate background music, piano and strings, calm and confident",
    "entrepreneurship": "upbeat motivational background music, moderate tempo, inspiring",
    "marketing": "creative energetic background music, modern electronic, positive",
    "real estate": "elegant ambient background music, sophisticated, cinematic",
    "finance": "sophisticated jazz background music, professional, smooth",
    "fitness": "energetic pump-up music, drums and bass, 120bpm, no lyrics",
    "health": "calm healing music, gentle piano, nature sounds",
    "technology": "modern electronic ambient music, futuristic, clean beats",
    "food": "upbeat cheerful background music, light and playful",
    "travel": "adventurous world music, inspiring, cinematic",
}


def build_mood_prompt(idea: dict) -> str:
    """
    Map idea niche + title to a MusicGen text prompt.

    Returns:
        Music description string (e.g. "upbeat corporate background, piano, 120bpm").
    """
    niche = (idea.get("niche") or SOCIAL_NICHE).lower()
    title = idea.get("title", "")

    # Find best match in niche map
    for key, mood in NICHE_MOOD_MAP.items():
        if key in niche or niche in key:
            return mood

    # Generic fallback
    return "professional background music, calm and engaging, suitable for social media"


def generate_audio(mood_prompt: str, output_path: Path,
                   duration_seconds: int = 15) -> Path | None:
    """
    Generate background music using HuggingFace MusicGen.

    Args:
        mood_prompt: Text description of the desired music
        output_path: Where to save the WAV file
        duration_seconds: Approximate duration (MusicGen generates ~10-30s clips)

    Returns:
        output_path on success, None on failure (caller should handle gracefully).
    """
    if not HF_AUDIO_ENABLED:
        print("  [AUDIO] Skipped (HF_AUDIO_ENABLED=false in .env)")
        return None

    if not HF_TOKEN:
        print("  [AUDIO] Skipped — HF_TOKEN not set in .env")
        return None

    url = f"{HF_API_BASE}/{MUSICGEN_MODEL}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": mood_prompt,
        "parameters": {
            "max_new_tokens": duration_seconds * 50,  # approximate token → seconds ratio
        }
    }

    print(f"  [AUDIO] Generating music: '{mood_prompt[:60]}...' ")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=240)

            if resp.status_code == 200:
                audio_bytes = resp.content
                if len(audio_bytes) < 1000:
                    print(f"  [AUDIO] Response too small ({len(audio_bytes)} bytes), likely an error")
                    return None

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(str(output_path), "wb") as f:
                    f.write(audio_bytes)
                print(f"  [AUDIO] Saved: {output_path.name} ({len(audio_bytes)//1024}KB)")
                return output_path

            elif resp.status_code == 503:
                try:
                    wait_time = min(resp.json().get("estimated_time", 30), 120)
                except Exception:
                    wait_time = 30
                print(f"  [AUDIO] MusicGen loading, waiting {wait_time:.0f}s...")
                time.sleep(wait_time)
                continue

            elif resp.status_code == 429:
                print("  [AUDIO] Rate limited, waiting 60s...")
                time.sleep(60)
                continue

            elif resp.status_code == 401:
                print("  [AUDIO] Invalid HF_TOKEN.")
                return None

            else:
                print(f"  [AUDIO] HF error {resp.status_code}: {resp.text[:150]}")
                if attempt < max_retries - 1:
                    time.sleep(10)

        except requests.Timeout:
            print(f"  [AUDIO] Timeout (attempt {attempt+1}). MusicGen can be slow — retrying...")
            time.sleep(5)
        except requests.RequestException as e:
            print(f"  [AUDIO] Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    print(f"  [AUDIO] Failed after {max_retries} attempts. Post will continue without music.")
    return None
