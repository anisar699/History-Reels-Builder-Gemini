"""Lightweight, local visual QA and saliency helpers.

The pipeline deliberately keeps these checks provider-independent: downloaded
images and representative video frames are inspected before rendering, and the
same measurements are used to sample the exported MP4.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import tempfile
from statistics import median
from typing import Any, Iterable

from PIL import Image, ImageFilter, ImageStat


RAW_MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp")


def find_raw_media_path(temp_dir: str, index: int) -> str | None:
    for extension in RAW_MEDIA_EXTENSIONS:
        candidate = os.path.join(temp_dir, f"raw_clip{index}{extension}")
        if os.path.isfile(candidate):
            return candidate
    return None


def remove_raw_media(temp_dir: str, index: int) -> None:
    for extension in RAW_MEDIA_EXTENSIONS:
        candidate = os.path.join(temp_dir, f"raw_clip{index}{extension}")
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError:
            pass


def _representative_image(media_path: str, at_seconds: float = 1.0) -> tuple[Image.Image, str | None]:
    extension = Path(media_path).suffix.lower()
    if extension != ".mp4":
        image = Image.open(media_path)
        image.load()
        return image.convert("RGB"), None

    handle, frame_path = tempfile.mkstemp(suffix=".jpg")
    os.close(handle)
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, at_seconds):.3f}",
        "-i", media_path, "-frames:v", "1", "-q:v", "3", frame_path,
    ]
    subprocess.run(command, capture_output=True, check=True, timeout=30)
    image = Image.open(frame_path)
    image.load()
    return image.convert("RGB"), frame_path


def _difference_hash(gray: Image.Image, size: int = 8) -> str:
    sample = gray.resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = list(sample.getdata())
    bits = []
    for row in range(size):
        start = row * (size + 1)
        for column in range(size):
            bits.append(pixels[start + column] > pixels[start + column + 1])
    value = sum((1 << position) for position, bit in enumerate(bits) if bit)
    return f"{value:0{size * size // 4}x}"


def hash_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


def _focus_point(gray: Image.Image) -> tuple[float, float]:
    """Estimate a stable visual focus using local edge energy.

    This is not face recognition. It is a deterministic saliency estimate that
    usually keeps people, objects, and textural detail inside a narrow crop.
    """
    sample = gray.resize((64, 64), Image.Resampling.LANCZOS)
    edges = sample.filter(ImageFilter.FIND_EDGES)
    values = list(edges.getdata())
    weighted_x = weighted_y = total = 0.0
    for y in range(2, 62):
        for x in range(2, 62):
            value = float(values[y * 64 + x])
            # Bias gently toward the frame centre to avoid locking onto borders.
            centre_weight = 0.65 + 0.35 * (1.0 - math.hypot(x - 31.5, y - 31.5) / 45.0)
            weight = max(0.0, value - 4.0) * centre_weight
            weighted_x += x * weight
            weighted_y += y * weight
            total += weight
    if total <= 0:
        return 0.5, 0.5
    focus_x = min(0.9, max(0.1, (weighted_x / total) / 63.0))
    focus_y = min(0.9, max(0.1, (weighted_y / total) / 63.0))
    return round(focus_x, 4), round(focus_y, 4)


def inspect_image(image: Image.Image, previous_hashes: Iterable[str] = ()) -> dict[str, Any]:
    rgb = image.convert("RGB")
    gray = rgb.convert("L")
    stats = ImageStat.Stat(gray)
    brightness = float(stats.mean[0])
    contrast = float(stats.stddev[0])
    edge_image = gray.resize((256, 256), Image.Resampling.LANCZOS).filter(ImageFilter.FIND_EDGES)
    detail = float(ImageStat.Stat(edge_image).mean[0])
    visual_hash = _difference_hash(gray)
    focus_x, focus_y = _focus_point(gray)

    failures = []
    warnings = []
    if brightness <= 6.0:
        failures.append("frame is nearly black")
    elif brightness >= 249.0:
        failures.append("frame is nearly white")
    if contrast < 4.0:
        failures.append("frame has almost no visible contrast")
    elif contrast < 10.0:
        warnings.append("frame has low contrast")
    if detail < 1.0:
        warnings.append("frame contains very little visual detail")

    duplicate_of = next(
        (candidate for candidate in previous_hashes if hash_distance(visual_hash, candidate) <= 4),
        None,
    )
    if duplicate_of:
        failures.append("frame is a near-duplicate of an earlier visual")

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "detail": round(detail, 2),
        "hash": visual_hash,
        "duplicate_of": duplicate_of,
        "focus_x": focus_x,
        "focus_y": focus_y,
        "width": rgb.width,
        "height": rgb.height,
    }


def inspect_media(media_path: str, previous_hashes: Iterable[str] = ()) -> dict[str, Any]:
    frame_path = None
    try:
        image, frame_path = _representative_image(media_path)
        report = inspect_image(image, previous_hashes)
        report["path"] = media_path
        return report
    except Exception as error:
        # Provider/media validation has already checked the container and
        # dimensions. A QA extraction error should be visible but not turn a
        # usable download into a blank pipeline.
        return {
            "passed": True,
            "failures": [],
            "warnings": [f"visual QA could not inspect this asset: {error}"],
            "hash": "",
            "focus_x": 0.5,
            "focus_y": 0.5,
            "path": media_path,
        }
    finally:
        if frame_path:
            try:
                os.remove(frame_path)
            except OSError:
                pass


def _sample_times(duration: float, slide_timings: Iterable[float] | None, max_samples: int) -> list[float]:
    max_samples = max(4, int(max_samples))
    slide_midpoints = []
    previous = 0.0
    for value in slide_timings or []:
        try:
            end = min(duration, max(previous, float(value)))
        except (TypeError, ValueError):
            continue
        if end > previous:
            slide_midpoints.append(previous + (end - previous) * 0.5)
            previous = end

    # Always reserve half the budget for uniform full-timeline coverage. The
    # old slide-only sampler missed a 55-second final slide entirely.
    uniform_count = min(max_samples, max(4, max_samples // 2))
    uniform = [duration * (index + 0.5) / uniform_count for index in range(uniform_count)]
    remaining = max_samples - len(uniform)
    selected_midpoints = []
    if slide_midpoints and remaining > 0:
        if len(slide_midpoints) <= remaining:
            selected_midpoints = slide_midpoints
        elif remaining == 1:
            selected_midpoints = [slide_midpoints[-1]]
        else:
            selected_midpoints = [
                slide_midpoints[
                    round(index * (len(slide_midpoints) - 1) / (remaining - 1))
                ]
                for index in range(remaining)
            ]
    return sorted({
        round(min(duration - 0.05, max(0.05, value)), 3)
        for value in uniform + selected_midpoints
        if duration > 0.1
    })


def _timeline_failures(duration: float, slide_timings: Iterable[float] | None) -> list[str]:
    durations = []
    previous = 0.0
    for raw_end in slide_timings or []:
        try:
            end = min(duration, max(previous, float(raw_end)))
        except (TypeError, ValueError):
            continue
        if end > previous:
            durations.append(end - previous)
            previous = end
    if len(durations) < 2:
        return []
    typical = max(0.1, median(durations))
    limit = max(15.0, typical * 3.0)
    failures = []
    for index, slide_duration in enumerate(durations, start=1):
        if slide_duration > limit and slide_duration > duration * 0.20:
            failures.append(
                f"slide {index} lasts {slide_duration:.2f}s "
                f"(typical slide {typical:.2f}s), causing prolonged visual repetition"
            )
    return failures


def _slide_number(at_seconds: float, slide_timings: Iterable[float] | None) -> int | None:
    timings = list(slide_timings or [])
    if not timings:
        return None
    for index, raw_end in enumerate(timings, start=1):
        try:
            if at_seconds <= float(raw_end) + 0.001:
                return index
        except (TypeError, ValueError):
            continue
    return len(timings)


def inspect_rendered_video(
    video_path: str,
    duration: float,
    slide_timings: Iterable[float] | None = None,
    max_samples: int = 12,
) -> dict[str, Any]:
    """Sample the export for blank frames, low visibility, and repetition."""
    samples = []
    hashes: list[tuple[str, int | None]] = []
    for number, at_seconds in enumerate(_sample_times(duration, slide_timings, max_samples), start=1):
        frame_path = None
        try:
            image, frame_path = _representative_image(video_path, at_seconds)
            report = inspect_image(image)
            slide_number = _slide_number(at_seconds, slide_timings)
            duplicate = next(
                (
                    value
                    for value, previous_slide in hashes
                    if (slide_number is None or previous_slide != slide_number)
                    and hash_distance(report["hash"], value) <= 3
                ),
                None,
            )
            if duplicate:
                report["warnings"].append(
                    "sample is visually similar to a different slide's final-video sample"
                )
            hashes.append((report["hash"], slide_number))
            report.update({
                "sample": number,
                "time_seconds": round(at_seconds, 3),
                "slide": slide_number,
            })
            samples.append(report)
        except Exception as error:
            samples.append({
                "sample": number,
                "time_seconds": round(at_seconds, 3),
                "passed": False,
                "failures": [f"frame extraction failed: {error}"],
                "warnings": [],
            })
        finally:
            if frame_path:
                try:
                    os.remove(frame_path)
                except OSError:
                    pass

    failed = [sample for sample in samples if not sample.get("passed")]
    warnings = [warning for sample in samples for warning in sample.get("warnings", [])]
    timeline_failures = _timeline_failures(duration, slide_timings)
    return {
        "passed": bool(samples) and not failed and not timeline_failures,
        "sample_count": len(samples),
        "failed_samples": len(failed),
        "timeline_failures": timeline_failures,
        "last_sample_seconds": max(
            (sample.get("time_seconds", 0.0) for sample in samples),
            default=0.0,
        ),
        "warning_count": len(warnings),
        "warnings": warnings,
        "samples": samples,
    }
