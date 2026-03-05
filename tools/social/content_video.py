"""
content_video.py — Video creation via ffmpeg.

Creates a simple slideshow MP4 from one or more images with optional background audio.

This approach is reliable, free, requires no GPU, and produces platform-ready videos.
Output is 1080x1080 square format for Instagram Reels compatibility.

Requirements:
  - ffmpeg must be installed on the system
  - Windows: winget install ffmpeg  OR  download from https://ffmpeg.org/download.html
  - Check installation: ffmpeg -version
"""

import os
import subprocess
import tempfile
from pathlib import Path


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_ffmpeg_version() -> str:
    """Return ffmpeg version string or 'not found'."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0]
            return first_line.replace("ffmpeg version ", "").split(" ")[0]
    except Exception:
        pass
    return "not found"


def create_slideshow_video(image_paths: list,
                           audio_path: Path | None,
                           output_path: Path,
                           duration_per_image: float = 4.0,
                           target_duration: int = 30,
                           fps: int = 30) -> Path | None:
    """
    Create an MP4 video from images with optional audio overlay.

    Strategy:
      1. Write a concat input file listing each image with duration
      2. Call ffmpeg to assemble: images → video stream
      3. If audio provided: overlay and loop audio to match video length
      4. Encode to H.264 + AAC, square 1080x1080 format

    Args:
        image_paths: list of Path objects pointing to image files
        audio_path: optional Path to WAV/MP3 audio file (used as background music)
        output_path: where to write the final MP4
        duration_per_image: seconds each image is shown (default 4.0)
        target_duration: target total video length in seconds (default 30)
        fps: frames per second (default 30)

    Returns:
        output_path on success, None on failure.
    """
    if not check_ffmpeg():
        print("  [VIDEO] Skipped — ffmpeg not found.")
        print("         Install: winget install ffmpeg  OR  https://ffmpeg.org/download.html")
        return None

    if not image_paths:
        print("  [VIDEO] Skipped — no images provided.")
        return None

    # Filter to existing images
    valid_images = [p for p in image_paths if Path(p).exists()]
    if not valid_images:
        print("  [VIDEO] Skipped — no valid image files found.")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate how many times to loop images to reach target duration
    total_images_needed = max(len(valid_images),
                               int(target_duration / duration_per_image))
    # Loop image list to fill duration
    looped_images = []
    while len(looped_images) < total_images_needed:
        looped_images.extend(valid_images)
    looped_images = looped_images[:total_images_needed]

    print(f"  [VIDEO] Building slideshow: {len(looped_images)} frames × {duration_per_image}s = {len(looped_images)*duration_per_image:.0f}s")

    # Write concat input file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, encoding="utf-8") as f:
        concat_file = f.name
        for img_path in looped_images:
            # Use forward slashes for ffmpeg compatibility on Windows
            safe_path = str(img_path).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
            f.write(f"duration {duration_per_image}\n")
        # Add last frame again (ffmpeg concat demuxer quirk)
        safe_path = str(looped_images[-1]).replace("\\", "/")
        f.write(f"file '{safe_path}'\n")

    try:
        # Build ffmpeg command
        vf = (
            "scale=1080:1080:force_original_aspect_ratio=decrease,"
            "pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=white,"
            "format=yuv420p"
        )

        if audio_path and Path(audio_path).exists():
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-i", str(audio_path),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",                      # end when shortest stream ends
                "-movflags", "+faststart",         # optimize for streaming
                str(output_path)
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an",                             # no audio
                "-movflags", "+faststart",
                str(output_path)
            ]

        print(f"  [VIDEO] Encoding MP4...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout
        )

        if result.returncode == 0 and output_path.exists():
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"  [VIDEO] Saved: {output_path.name} ({size_mb:.1f}MB)")
            return output_path
        else:
            print(f"  [VIDEO] ffmpeg failed (code {result.returncode})")
            if result.stderr:
                # Print last few lines of stderr for debugging
                stderr_lines = result.stderr.strip().splitlines()
                for line in stderr_lines[-5:]:
                    print(f"          {line}")
            return None

    except subprocess.TimeoutExpired:
        print("  [VIDEO] ffmpeg timed out after 5 minutes.")
        return None
    except Exception as e:
        print(f"  [VIDEO] Unexpected error: {e}")
        return None
    finally:
        try:
            Path(concat_file).unlink(missing_ok=True)
        except Exception:
            pass
