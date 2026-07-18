"""Local-first, original background-track provisioning for reel renders."""

from __future__ import annotations

import os
import random
from typing import Any


MUSIC_VIBES = ("mystery", "epic", "sad", "ancient", "modern", "intense")
_VIBE_SOUND = {
    "mystery": (110, "pink", 700),
    "epic": (146, "white", 1100),
    "sad": (174, "brown", 550),
    "ancient": (196, "pink", 900),
    "modern": (220, "white", 1500),
    "intense": (98, "brown", 800),
}


def resolve_music_vibe(vibe: str) -> str:
    normalized = str(vibe or "mystery").strip().lower()
    if normalized == "random":
        return random.choice(MUSIC_VIBES)
    return normalized if normalized in MUSIC_VIBES else "mystery"


def is_usable_audio(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= 4096
    except OSError:
        return False


def local_track_command(vibe: str, output_path: str, track_index: int = 1) -> list[str]:
    """Build a royalty-free original 60s ambient bed using only FFmpeg sources."""
    tone, noise_color, lowpass = _VIBE_SOUND[resolve_music_vibe(vibe)]
    track_index = max(1, min(5, int(track_index or 1)))
    tone += (track_index - 3) * 4
    echo_delay = 90 + track_index * 15
    duration = 60
    tone_input = f"sine=frequency={tone}:sample_rate=44100:duration={duration}"
    noise_input = f"anoisesrc=color={noise_color}:sample_rate=44100:duration={duration}"
    graph = (
        f"[0:a]volume=0.055,lowpass=f={lowpass},aecho=0.8:0.88:{echo_delay}:0.25[tone];"
        "[1:a]volume=0.018,lowpass=f=1800[texture];"
        f"[tone][texture]amix=inputs=2:duration=first,afade=t=in:d=1,afade=t=out:st={duration - 2}:d=2[mix]"
    )
    return [
        "ffmpeg", "-y", "-f", "lavfi", "-i", tone_input,
        "-f", "lavfi", "-i", noise_input,
        "-filter_complex", graph, "-map", "[mix]", "-t", str(duration),
        "-ac", "2", "-c:a", "libmp3lame", "-q:a", "5", output_path,
    ]


def ensure_local_music_track(job: Any) -> str | None:
    """Return a reusable local track, creating it once without any web download."""
    vibe = resolve_music_vibe(getattr(job, "BG_MUSIC_VIBE", "mystery"))
    track_index = max(1, min(5, int(getattr(job, "BG_MUSIC_TRACK_INDEX", 1) or 1)))
    job.BG_MUSIC_VIBE = vibe
    job.BG_MUSIC_TRACK_INDEX = track_index
    os.makedirs(job.MUSIC_DIR, exist_ok=True)
    target = os.path.join(job.MUSIC_DIR, f"{vibe}_{track_index}.mp3")
    if is_usable_audio(target):
        job.MUSIC_SOURCE = "local library"
        return target

    print(f"Creating local royalty-free '{vibe}' background track (one-time setup)...")
    try:
        from history_reels.ffmpeg_runner import run_command

        run_command(
            local_track_command(vibe, target, track_index),
            timeout=120,
            label="local music generate",
        )
    except Exception as error:
        print(f"Failed to create local background track: {error}")
        return None
    if is_usable_audio(target):
        job.MUSIC_SOURCE = "local generated"
        return target
    return None
