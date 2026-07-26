"""Local-first, original background-track provisioning for reel renders."""

from __future__ import annotations

import os
from typing import Any


MUSIC_VIBES = ("mystery", "epic", "sad", "ancient", "modern", "intense")
MUSIC_LIBRARY_VERSION = 3
MUSIC_TRACK_DURATION_SECONDS = 660
_VIBE_SOUND = {
    # root, harmonic ratios, texture, tone low-pass, movement period
    "mystery": (110, (1.189, 1.498), "pink", 950, 9),
    "epic": (146, (1.498, 2.000), "white", 1800, 6),
    "sad": (174, (1.189, 1.498), "brown", 850, 12),
    "ancient": (196, (1.333, 1.498), "pink", 1350, 10),
    "modern": (220, (1.260, 1.498), "white", 2400, 5),
    "intense": (98, (1.498, 2.000), "brown", 1500, 4),
}


def resolve_music_vibe(vibe: str) -> str:
    normalized = str(vibe or "mystery").strip().lower()
    return normalized if normalized in MUSIC_VIBES else "mystery"


def is_usable_audio(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= 4096
    except OSError:
        return False


def local_track_command(vibe: str, output_path: str, track_index: int = 1) -> list[str]:
    """Build a layered, royalty-free original score using only FFmpeg sources."""
    tone, intervals, noise_color, lowpass, movement = _VIBE_SOUND[resolve_music_vibe(vibe)]
    track_index = max(1, min(5, int(track_index or 1)))
    tone += (track_index - 3) * 4
    harmonic_one = round(tone * intervals[0], 2)
    harmonic_two = round(tone * intervals[1], 2)
    echo_delay = 105 + track_index * 18
    # One continuous bed covers the dashboard's full 10-minute range. It has
    # no baked fade at the loop boundary; the renderer applies one fade only
    # at the actual beginning and end of the finished narration.
    duration = MUSIC_TRACK_DURATION_SECONDS
    tone_input = f"sine=frequency={tone}:sample_rate=48000:duration={duration}"
    harmonic_one_input = f"sine=frequency={harmonic_one}:sample_rate=48000:duration={duration}"
    harmonic_two_input = f"sine=frequency={harmonic_two}:sample_rate=48000:duration={duration}"
    noise_input = f"anoisesrc=color={noise_color}:sample_rate=48000:duration={duration}"
    graph = (
        f"[0:a]volume='0.040*(0.82+0.18*sin(2*PI*t/{movement}))':eval=frame,"
        f"lowpass=f={lowpass},aecho=0.8:0.82:{echo_delay}:0.18[root];"
        f"[1:a]volume='0.024*(0.75+0.25*sin(2*PI*t/{movement + 3}))':eval=frame,"
        f"lowpass=f={int(lowpass * 1.15)}[harmony1];"
        f"[2:a]volume='0.014*(0.70+0.30*sin(2*PI*t/{movement + 5}))':eval=frame,"
        f"lowpass=f={int(lowpass * 1.45)},aecho=0.8:0.75:{echo_delay * 2}:0.12[harmony2];"
        f"[3:a]volume=0.010,highpass=f=80,lowpass=f={int(lowpass * 1.8)}[texture];"
        "[root][harmony1][harmony2][texture]"
        "amix=inputs=4:duration=first:normalize=0,"
        "highpass=f=45,acompressor=threshold=0.12:ratio=2:attack=80:release=500,"
        "alimiter=limit=0.75[mix]"
    )
    return [
        "ffmpeg", "-y", "-f", "lavfi", "-i", tone_input,
        "-f", "lavfi", "-i", harmonic_one_input,
        "-f", "lavfi", "-i", harmonic_two_input,
        "-f", "lavfi", "-i", noise_input,
        "-filter_complex", graph, "-map", "[mix]", "-t", str(duration),
        "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-q:a", "4", output_path,
    ]


def ensure_local_music_track(job: Any) -> str | None:
    """Return a reusable local track, creating it once without any web download."""
    vibe = resolve_music_vibe(getattr(job, "BG_MUSIC_VIBE", "mystery"))
    track_index = max(1, min(5, int(getattr(job, "BG_MUSIC_TRACK_INDEX", 1) or 1)))
    job.BG_MUSIC_VIBE = vibe
    job.BG_MUSIC_TRACK_INDEX = track_index
    os.makedirs(job.MUSIC_DIR, exist_ok=True)
    target = os.path.join(
        job.MUSIC_DIR,
        f"v{MUSIC_LIBRARY_VERSION}_{vibe}_{track_index}.mp3",
    )
    if is_usable_audio(target):
        job.MUSIC_SOURCE = f"local library v{MUSIC_LIBRARY_VERSION}"
        job.MUSIC_PATH = target
        return target

    print(f"Creating local royalty-free '{vibe}' background track (one-time setup)...")
    try:
        from history_reels.ffmpeg_runner import run_command

        run_command(
            local_track_command(vibe, target, track_index),
            timeout=180,
            label="local music generate",
        )
    except Exception as error:
        print(f"Failed to create local background track: {error}")
        return None
    if is_usable_audio(target):
        job.MUSIC_SOURCE = f"local generated v{MUSIC_LIBRARY_VERSION}"
        job.MUSIC_PATH = target
        return target
    return None
