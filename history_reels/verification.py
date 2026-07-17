"""No-network configuration matrix and post-render deliverable verification."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from history_reels.font_manager import font_options_for_language, get_font_preset
from history_reels.music_library import MUSIC_VIBES, resolve_music_vibe


VERIFICATION_MATRIX = (
    {"id": "urdu-vertical", "language": "Urdu", "ratio": (720, 1280), "music": True, "quality": "balanced"},
    {"id": "english-landscape", "language": "English", "ratio": (1280, 720), "music": True, "quality": "high"},
    {"id": "hindi-square", "language": "Hindi", "ratio": (1080, 1080), "music": False, "quality": "balanced"},
    {"id": "arabic-vertical", "language": "Arabic", "ratio": (720, 1280), "music": True, "quality": "high"},
    {"id": "roman-urdu-vertical", "language": "Roman Urdu", "ratio": (720, 1280), "music": True, "quality": "balanced"},
)


def run_verification_matrix() -> dict[str, Any]:
    """Check representative language, layout, music, and quality combinations."""
    cases = []
    for case in VERIFICATION_MATRIX:
        language = case["language"]
        fonts = font_options_for_language(language)
        font = get_font_preset(fonts[0])
        width, height = case["ratio"]
        errors = []
        if not fonts or not font.get("family") or not font.get("url"):
            errors.append("No usable caption font preset.")
        if width < 480 or height < 480:
            errors.append("Frame dimensions are below the minimum supported size.")
        if case["music"] and any(resolve_music_vibe(vibe) != vibe for vibe in MUSIC_VIBES):
            errors.append("Local music library does not support all configured vibes.")
        if case["quality"] not in {"balanced", "high"}:
            errors.append("Unknown media quality profile.")
        cases.append({
            **case,
            "caption_font": font["family"],
            "passed": not errors,
            "errors": errors,
        })
    return {"passed": all(case["passed"] for case in cases), "cases": cases}


def verify_deliverable(job: Any) -> dict[str, Any]:
    """Validate the final exported MP4 and SEO package before marking a job ready."""
    video_path = Path(job.video_path)
    seo_path = Path(job.seo_path)
    if not video_path.is_file() or video_path.stat().st_size < 1024:
        raise RuntimeError("Verification failed: final MP4 is missing or too small.")
    if not seo_path.is_file() or seo_path.stat().st_size == 0:
        raise RuntimeError("Verification failed: final SEO package is missing or empty.")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-show_streams", "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    stream_types = {stream.get("codec_type") for stream in streams}
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    actual_width, actual_height = int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)
    expected_width, expected_height = int(job.VIDEO_WIDTH), int(job.VIDEO_HEIGHT)
    duration = float(metadata.get("format", {}).get("duration") or 0)
    if {"audio", "video"} - stream_types:
        raise RuntimeError("Verification failed: final MP4 must contain audio and video streams.")
    if (actual_width, actual_height) != (expected_width, expected_height):
        raise RuntimeError(f"Verification failed: expected {expected_width}x{expected_height}, got {actual_width}x{actual_height}.")
    if duration <= 0:
        raise RuntimeError("Verification failed: final MP4 has no measurable duration.")
    if video_stream.get("codec_name") != "h264":
        raise RuntimeError("Verification failed: final video must use the H.264 codec.")
    if video_stream.get("pix_fmt") != "yuv420p":
        raise RuntimeError("Verification failed: final video must use yuv420p for broad platform compatibility.")
    if audio_stream.get("codec_name") != "aac":
        raise RuntimeError("Verification failed: final audio must use the AAC codec.")
    if int(audio_stream.get("sample_rate") or 0) != 48_000:
        raise RuntimeError("Verification failed: final audio must use a 48 kHz sample rate.")
    if int(audio_stream.get("channels") or 0) < 1:
        raise RuntimeError("Verification failed: final audio stream has no usable channels.")

    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "video_path": str(video_path),
        "seo_path": str(seo_path),
        "video_bytes": video_path.stat().st_size,
        "seo_bytes": seo_path.stat().st_size,
        "duration_seconds": round(duration, 3),
        "stream_types": sorted(stream_types),
        "dimensions": [actual_width, actual_height],
        "expected_dimensions": [expected_width, expected_height],
        "video_codec": video_stream.get("codec_name"),
        "pixel_format": video_stream.get("pix_fmt"),
        "audio_codec": audio_stream.get("codec_name"),
        "audio_sample_rate": int(audio_stream.get("sample_rate") or 0),
        "audio_channels": int(audio_stream.get("channels") or 0),
        "job_settings": {
            "language": getattr(job, "CONTENT_LANGUAGE", "Urdu"),
            "caption_font": getattr(job, "CAPTION_FONT_FAMILY", ""),
            "music_vibe": getattr(job, "BG_MUSIC_VIBE", "mystery"),
            "media_quality": getattr(job, "MEDIA_QUALITY_PROFILE", "balanced"),
        },
        "matrix": run_verification_matrix(),
    }
    report_dir = Path(job.OUTPUT_DIR) / "verification_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{job.OUTPUT_NAME}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    job.VERIFICATION_REPORT_PATH = str(report_path)
    return report
