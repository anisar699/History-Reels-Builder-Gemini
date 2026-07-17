"""Real staging acceptance runner for one bounded end-to-end reel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from typing import Any

from history_reels import config
from history_reels.cli import generate_video_for_topic
from history_reels.jobs import create_generation_job


DEFAULT_TOPIC = "The invention of the printing press and how it changed human knowledge"
SUPPORTED_PROVIDERS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def staging_paths(root: Path) -> dict[str, Path]:
    staging_root = root / ".staging"
    return {
        "root": staging_root,
        "assets": staging_root / "assets",
        "output": staging_root / "output",
        "temp": staging_root / "temp",
        "reports": root / "staging_reports",
    }


def preflight(provider: str) -> dict[str, Any]:
    required_tools = ("ffmpeg", "ffprobe", "edge-tts")
    tools = {name: shutil.which(name) for name in required_tools}
    missing = [name for name, path in tools.items() if not path]
    key_name = SUPPORTED_PROVIDERS.get(provider)
    key_available = bool(key_name and getattr(config, key_name, ""))
    checks = {
        "python": platform.python_version(),
        "provider": provider,
        "provider_key_configured": key_available,
        "tools": tools,
        "passed": not missing and key_available,
    }
    if missing:
        checks["error"] = f"Missing required tools: {', '.join(missing)}"
    elif not key_available:
        checks["error"] = f"{key_name or 'Provider API key'} is not configured."
    return checks


def validate_video_artifact(video_path: Path, seo_path: Path, target_duration: float) -> dict[str, Any]:
    if not video_path.is_file() or video_path.stat().st_size <= 0:
        raise RuntimeError(f"Video artifact is missing or empty: {video_path}")
    if not seo_path.is_file() or seo_path.stat().st_size <= 0:
        raise RuntimeError(f"SEO artifact is missing or empty: {seo_path}")

    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration,size",
            "-show_streams", "-of", "json", str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    metadata = json.loads(result.stdout)
    streams = metadata.get("streams", [])
    stream_types = {stream.get("codec_type") for stream in streams}
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    actual_duration = float(metadata.get("format", {}).get("duration") or 0)
    if "video" not in stream_types or "audio" not in stream_types:
        raise RuntimeError("Generated artifact must contain both video and audio streams.")
    if actual_duration < max(5.0, target_duration - 5.0) or actual_duration > target_duration + 8.0:
        raise RuntimeError(
            f"Generated duration {actual_duration:.2f}s is outside the staging tolerance for {target_duration:.2f}s."
        )
    if video_stream.get("codec_name") != "h264" or video_stream.get("pix_fmt") != "yuv420p":
        raise RuntimeError("Generated artifact must use H.264 video with yuv420p pixel format.")
    if audio_stream.get("codec_name") != "aac" or int(audio_stream.get("sample_rate") or 0) != 48_000:
        raise RuntimeError("Generated artifact must use 48 kHz AAC audio.")
    return {
        "video_path": str(video_path.resolve()),
        "seo_path": str(seo_path.resolve()),
        "video_bytes": video_path.stat().st_size,
        "seo_bytes": seo_path.stat().st_size,
        "actual_duration_seconds": round(actual_duration, 3),
        "stream_types": sorted(stream_types),
        "video_codec": video_stream.get("codec_name"),
        "pixel_format": video_stream.get("pix_fmt"),
        "audio_codec": audio_stream.get("codec_name"),
        "audio_sample_rate": int(audio_stream.get("sample_rate") or 0),
    }


def write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"acceptance-{timestamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def classify_acceptance_failure(error: Exception) -> str:
    message = str(error).lower()
    if "insufficient_quota" in message:
        return "blocked_quota"
    if "http 429" in message or "rate_limit_exceeded" in message:
        return "blocked_rate_limit"
    return "failed"


def run_acceptance(topic: str, provider: str, duration: int, project_root: Path, preflight_only: bool = False) -> tuple[bool, Path]:
    paths = staging_paths(project_root)
    checks = preflight(provider)
    report: dict[str, Any] = {
        "phase": 13,
        "started_at": _utc_now(),
        "status": "preflight_failed" if not checks["passed"] else "preflight_passed",
        "topic": topic,
        "provider": provider,
        "target_duration_seconds": duration,
        "preflight": checks,
    }
    if not checks["passed"] or preflight_only:
        report["completed_at"] = _utc_now()
        report_path = write_report(paths["reports"], report)
        return bool(checks["passed"]), report_path

    for path in (paths["assets"], paths["output"], paths["temp"]):
        path.mkdir(parents=True, exist_ok=True)

    config.ASSETS_DIR = str(paths["assets"])
    config.TEMP_DIR = str(paths["temp"])
    config.TOPIC_TEMP_DIR = str(paths["temp"])
    config.OUTPUT_DIR = str(paths["output"])
    config.MUSIC_DIR = str(paths["output"] / "bg_music")
    config.FONT_PATH = str(paths["assets"] / f"{config.URDU_FONT_NAME}.ttf")
    config.TARGET_DURATION = duration
    config.CLIP_DURATION_TARGET = 5.0
    config.VOICE_PROVIDER = "edge-tts"
    config.MEDIA_PREFERENCE = "mixed"
    config.VIDEO_TRANSITION = "fade"
    config.SHOW_WATERMARK = False
    config.INTRO_BUMPER = None
    config.OUTRO_BUMPER = None

    job = create_generation_job(config)
    started = time.monotonic()
    try:
        succeeded = generate_video_for_topic(topic, provider=provider, job=job)
        report["job_id"] = job.job_id
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if not succeeded:
            raise RuntimeError(job.last_error or "Pipeline returned an unsuccessful result.")
        report["artifact"] = validate_video_artifact(Path(job.video_path), Path(job.seo_path), duration)
        report["status"] = "passed"
        report["completed_at"] = _utc_now()
        report_path = write_report(paths["reports"], report)
        return True, report_path
    except Exception as error:
        report["status"] = classify_acceptance_failure(error)
        report["error"] = str(error)[:2000]
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["completed_at"] = _utc_now()
        report_path = write_report(paths["reports"], report)
        return False, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded Phase 13 staging acceptance reel.")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--provider", choices=sorted(SUPPORTED_PROVIDERS), default="groq")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if not 15 <= args.duration <= 60:
        parser.error("--duration must be between 15 and 60 seconds")

    project_root = Path(__file__).resolve().parent.parent
    success, report_path = run_acceptance(
        args.topic.strip() or DEFAULT_TOPIC,
        args.provider,
        args.duration,
        project_root,
        preflight_only=args.preflight_only,
    )
    print(f"Acceptance report: {report_path}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
