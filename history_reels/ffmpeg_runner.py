"""Shared media-tool runner with timeouts, stderr capture, and cancel hooks."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any, Mapping, Sequence


class RenderError(RuntimeError):
    """Structured failure from ffmpeg/ffprobe/edge-tts style tools."""

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str] | None = None,
        returncode: int | None = None,
        stderr_tail: str = "",
    ) -> None:
        super().__init__(message)
        self.command = list(command or [])
        self.returncode = returncode
        self.stderr_tail = stderr_tail


_ACTIVE_LOCK = threading.Lock()
_ACTIVE_PROCESSES: dict[str, list[subprocess.Popen]] = {}

# Conservative defaults: long enough for real reels, short enough to free a hung worker.
DEFAULT_TIMEOUT_SECONDS = 600
PROBE_TIMEOUT_SECONDS = 30
CLIP_TIMEOUT_SECONDS = 180
AUDIO_TIMEOUT_SECONDS = 300
MERGE_TIMEOUT_SECONDS = 900
TTS_TIMEOUT_SECONDS = 180


def _tail(text: str, limit: int = 1200) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _register(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESSES.setdefault(job_id, []).append(process)


def _unregister(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _ACTIVE_LOCK:
        active = _ACTIVE_PROCESSES.get(job_id) or []
        _ACTIVE_PROCESSES[job_id] = [item for item in active if item is not process and item.poll() is None]
        if not _ACTIVE_PROCESSES[job_id]:
            _ACTIVE_PROCESSES.pop(job_id, None)


def kill_job_processes(job_id: str) -> int:
    """Terminate any tracked media subprocesses for a job (best-effort hard cancel)."""
    if not job_id:
        return 0
    with _ACTIVE_LOCK:
        processes = list(_ACTIVE_PROCESSES.get(job_id) or [])
    killed = 0
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            killed += 1
        except OSError:
            try:
                process.kill()
                killed += 1
            except OSError:
                pass
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESSES.pop(job_id, None)
    return killed


def build_subprocess_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy the process environment without permanently mutating globals."""
    env = dict(os.environ)
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    return env


def run_command(
    cmd: Sequence[str],
    *,
    check: bool = True,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    job_id: str | None = None,
    capture_output: bool = True,
    text: bool = True,
    stdin=subprocess.DEVNULL,
    label: str = "media tool",
) -> subprocess.CompletedProcess:
    """Run a media command with timeout, stderr capture, and optional job kill tracking."""
    command = [str(part) for part in cmd]
    process_env = build_subprocess_env(env) if env is not None else None
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=process_env,
        stdin=stdin,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
    )
    _register(job_id, process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        _unregister(job_id, process)
        raise RenderError(
            f"{label} timed out after {timeout}s: {' '.join(command[:6])}",
            command=command,
            returncode=process.returncode,
            stderr_tail=_tail(str(stderr or "")),
        ) from error
    finally:
        _unregister(job_id, process)

    completed = subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout if capture_output else None,
        stderr=stderr if capture_output else None,
    )
    if check and completed.returncode != 0:
        stderr_tail = _tail(str(completed.stderr or completed.stdout or ""))
        detail = f": {stderr_tail}" if stderr_tail else ""
        raise RenderError(
            f"{label} failed (exit {completed.returncode}){detail}",
            command=command,
            returncode=completed.returncode,
            stderr_tail=stderr_tail,
        )
    return completed


def probe_media_streams(path: str, *, select: str = "v:0", entries: str = "width,height") -> str:
    completed = run_command(
        [
            "ffprobe", "-v", "error",
            "-select_streams", select,
            "-show_entries", f"stream={entries}",
            "-of", "csv=p=0",
            path,
        ],
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
        label="ffprobe",
    )
    return str(completed.stdout or "").strip()


def get_media_dimensions(path: str) -> tuple[int, int]:
    """Return width/height for video or still image via ffprobe."""
    try:
        raw = probe_media_streams(path)
        if not raw:
            return 0, 0
        parts = raw.split(",")
        return int(parts[0]), int(parts[1])
    except (RenderError, IndexError, ValueError, TypeError) as error:
        print(f"Warning: Could not read dimensions of {path}: {error}")
        return 0, 0


def has_audio_stream(path: str) -> bool:
    completed = run_command(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            path,
        ],
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
        label="ffprobe",
    )
    return bool(str(completed.stdout or "").strip())


def write_fontconfig_file(job: Any) -> str:
    """Write a job-local fonts.conf and return its path (no global env mutation)."""
    font_dirs = {
        os.path.dirname(os.path.abspath(getattr(job, "FONT_PATH", "") or "")),
        os.path.join(getattr(job, "OUTPUT_DIR", ""), "fonts"),
        getattr(job, "ASSETS_DIR", "") or "",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    }
    font_dir_lines = "\n".join(
        f"    <dir>{directory.replace(chr(92), '/')}</dir>"
        for directory in sorted(font_dirs)
        if directory and os.path.exists(directory)
    )
    fonts_conf_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
{font_dir_lines}
    <dir>WINDOWSFONTDIR</dir>
    <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
</fontconfig>
"""
    fonts_conf_path = os.path.join(job.TOPIC_TEMP_DIR, "fonts.conf")
    with open(fonts_conf_path, "w", encoding="utf-8") as handle:
        handle.write(fonts_conf_content)
    print(f"Fontconfig local file configured: {fonts_conf_path}")
    return fonts_conf_path
