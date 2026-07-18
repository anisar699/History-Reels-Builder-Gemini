"""Durable, local-only lifecycle records for reel generation jobs."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


VALID_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
SENSITIVE_SETTING_MARKERS = ("API_KEY", "PASSWORD", "SECRET", "TOKEN")
EPHEMERAL_SETTING_NAMES = {
    "DOWNLOADED_VIDEO_IDS",
    "LAST_ERROR_MESSAGE",
    "OUTPUT_DIR",
    "OUTPUT_NAME",
    "SLIDE_TIMINGS",
    "TEMP_DIR",
    "TOPIC_TEMP_DIR",
    "TRANSITION_OFFSETS",
    "VIDEO_ATTRIBUTIONS",
}
LEGACY_SETTING_NAMES = {
    "music_vibe": "BG_MUSIC_VIBE",
    "voice_provider": "VOICE_PROVIDER",
    "voice_id": "VOICE_ID",
    "media_preference": "MEDIA_PREFERENCE",
    "target_duration": "TARGET_DURATION",
}


def _is_persistable_setting(name: str, value: Any) -> bool:
    if not name.isupper() or name in EPHEMERAL_SETTING_NAMES:
        return False
    if any(marker in name for marker in SENSITIVE_SETTING_MARKERS):
        return False
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        print(f"Serialization failed for {name}: {e}")
        return False
    return True


def snapshot_safe_settings(job: Any) -> dict[str, Any]:
    """Persist reproducible job options while excluding credentials/runtime state."""
    values = getattr(job, "values", {})
    return {
        name: value
        for name, value in values.items()
        if _is_persistable_setting(name, value)
    }


def restore_safe_settings(job: Any, settings: dict[str, Any] | None) -> None:
    """Restore only settings that pass the same credential-safe allow rules."""
    for raw_name, value in (settings or {}).items():
        name = LEGACY_SETTING_NAMES.get(str(raw_name), str(raw_name))
        if _is_persistable_setting(name, value):
            setattr(job, name, value)


def categorize_error(error_message: str) -> str:
    """Map raw failures to stable, UI-friendly categories."""
    message = str(error_message).lower()
    if "cancel" in message:
        return "cancelled"
    if "validation" in message or "input validation" in message:
        return "validation"
    if "api key" in message or "credential" in message or "unauthorized" in message or "forbidden" in message:
        return "credentials"
    if "timeout" in message or "network" in message or "connection" in message or "rate limit" in message or "429" in message:
        return "network"
    if "download" in message or "pexels" in message or "pixabay" in message or "media" in message:
        return "media"
    if "ffmpeg" in message or "ffprobe" in message or "render" in message:
        return "rendering"
    if "font" in message or "music" in message or "dependency" in message:
        return "environment"
    return "unknown"


class JobCancelledError(RuntimeError):
    """Raised when a queued cancellation request reaches a safe checkpoint."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """A small SQLite store shared safely by dashboard sessions on one machine."""

    def __init__(self, output_dir: str):
        self.path = os.path.join(output_dir, "job_history.sqlite3")
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    output_name TEXT NOT NULL DEFAULT '',
                    output_video_path TEXT NOT NULL DEFAULT '',
                    output_seo_path TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    error_category TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    retry_of TEXT NOT NULL DEFAULT '',
                    attempt INTEGER NOT NULL DEFAULT 1,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_stage TEXT NOT NULL DEFAULT 'queued',
                    request_json TEXT NOT NULL DEFAULT '{}',
                    settings_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "retry_of" not in columns:
                try:
                    connection.execute("ALTER TABLE jobs ADD COLUMN retry_of TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
            for column, definition in {
                "attempt": "INTEGER NOT NULL DEFAULT 1",
                "max_attempts": "INTEGER NOT NULL DEFAULT 1",
                "progress": "INTEGER NOT NULL DEFAULT 0",
                "current_stage": "TEXT NOT NULL DEFAULT 'queued'",
                "error_category": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in columns:
                    try:
                        connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
                    except sqlite3.OperationalError:
                        pass
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER,
                    message TEXT NOT NULL
                )
                """
            )

    def create_job(self, job: Any, request: dict[str, Any]) -> None:
        settings = snapshot_safe_settings(job)
        topic = str(request.get("label") or request.get("topic") or "Untitled reel")[:500]
        provider = str(request.get("provider") or "auto")[:100]
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, created_at, updated_at, status, topic, provider,
                    workspace, retry_of, attempt, max_attempts, request_json, settings_json
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.created_at,
                    _now(),
                    topic,
                    provider,
                    job.TOPIC_TEMP_DIR,
                    str(request.get("retry_of") or ""),
                    int(request.get("attempt") or 1),
                    int(request.get("max_attempts") or 1),
                    json.dumps(request, ensure_ascii=False, default=str),
                    json.dumps(settings, ensure_ascii=False),
                ),
            )
        self.record_event(job.job_id, "info", "queued", "Job queued.", progress=0)

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, "running", current_stage="starting", progress=1)
        self.record_event(job_id, "info", "starting", "Worker started.", progress=1)

    def mark_succeeded(self, job: Any) -> None:
        output_name = getattr(job, "OUTPUT_NAME", "")
        output_dir = getattr(job, "OUTPUT_DIR", "")
        
        # Use job's path properties if available to respect CUSTOM_SAVE_DIR
        video_path = getattr(job, "video_path", os.path.join(output_dir, f"{output_name}.mp4") if output_name else "")
        seo_path = getattr(job, "seo_path", os.path.join(output_dir, f"{output_name}.txt") if output_name else "")

        self._update(
            job.job_id,
            "succeeded",
            output_name=output_name,
            output_video_path=video_path,
            output_seo_path=seo_path,
            current_stage="completed",
            progress=100,
        )
        self.record_event(job.job_id, "info", "completed", "Generation completed.", progress=100)

    def mark_failed(self, job: Any, error_message: str) -> None:
        self.mark_failed_by_id(job.job_id, error_message)

    def mark_failed_by_id(self, job_id: str, error_message: str) -> None:
        """Finalize a job that failed before a complete job object is available."""
        self._update(
            job_id,
            "failed",
            error_message=error_message,
            error_category=categorize_error(error_message),
            current_stage="failed",
        )
        self.record_event(job_id, "error", "failed", error_message)

    def mark_cancelled(self, job: Any, reason: str = "Cancellation requested") -> None:
        self._update(
            job.job_id,
            "cancelled",
            error_message=reason,
            error_category="cancelled",
            current_stage="cancelled",
        )
        self.record_event(job.job_id, "warning", "cancelled", reason)

    def update_progress(self, job_id: str, stage: str, progress: int, message: str) -> None:
        safe_progress = max(0, min(100, int(progress)))
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET current_stage = ?, progress = ?, updated_at = ? WHERE job_id = ?",
                (stage, safe_progress, _now(), job_id),
            )
        self.record_event(job_id, "info", stage, message, progress=safe_progress)

    def record_event(self, job_id: str, level: str, stage: str, message: str, progress: int | None = None) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO job_events (job_id, created_at, level, stage, progress, message) VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, _now(), level, stage, progress, str(message)[:2000]),
            )

    def _update(self, job_id: str, status: str, **fields: Any) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unsupported job status: {status}")
        assignments = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, _now()]
        for field_name, field_value in fields.items():
            assignments.append(f"{field_name} = ?")
            values.append(field_value)
        values.append(job_id)
        with self._connection() as connection:
            connection.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id = ?", values)

    def request_cancellation(self, job_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET cancel_requested = 1, updated_at = ?
                WHERE job_id = ? AND status IN ('queued', 'running')
                """,
                (_now(), job_id),
            )
            return cursor.rowcount == 1

    def cancellation_requested(self, job_id: str) -> bool:
        record = self.get_job(job_id)
        if record and record.get("status") == "cancelled":
            return True
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def get_retry_request(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT request_json FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if not row:
            return None
        try:
            request = json.loads(row["request_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        return request if isinstance(request, dict) else None

    def list_events(self, job_id: str, limit: int = 25) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT created_at, level, stage, progress, message
                FROM job_events WHERE job_id = ? ORDER BY id DESC LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        for key in ("request_json", "settings_json"):
            try:
                record[key] = json.loads(record[key])
            except (TypeError, json.JSONDecodeError):
                record[key] = {}
        return record

    def list_queued_job_ids(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute("SELECT job_id FROM jobs WHERE status = 'queued' ORDER BY created_at").fetchall()
        return [row["job_id"] for row in rows]

    def cleanup_history(self, older_than_days: int) -> int:
        """Remove terminal history only; rendered output files are never touched."""
        cutoff = datetime.now(timezone.utc).timestamp() - max(1, int(older_than_days)) * 86400
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT job_id, created_at FROM jobs WHERE status IN ('succeeded', 'failed', 'cancelled')"
            ).fetchall()
            ids = [
                row["job_id"] for row in rows
                if datetime.fromisoformat(row["created_at"]).timestamp() < cutoff
            ]
            if ids:
                for i in range(0, len(ids), 500):
                    chunk_ids = ids[i:i + 500]
                    placeholders = ",".join("?" for _ in chunk_ids)
                    connection.execute(f"DELETE FROM job_events WHERE job_id IN ({placeholders})", chunk_ids)
                    connection.execute(f"DELETE FROM jobs WHERE job_id IN ({placeholders})", chunk_ids)
        return len(ids)

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT job_id, created_at, updated_at, status, topic, provider,
                       output_name, output_video_path, output_seo_path,
                       error_message, cancel_requested, retry_of,
                       attempt, max_attempts, progress, current_stage, error_category
                FROM jobs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def get_dashboard_metrics(output_dir: str) -> dict[str, Any]:
    """Calculate dashboard metrics for total completed videos and storage used."""
    total_completed = 0
    total_storage_bytes = 0

    if os.path.exists(output_dir):
        store = JobStore(output_dir)
        try:
            with store._connection() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) as count FROM jobs WHERE status IN ('completed', 'succeeded')"
                ).fetchone()
                if row:
                    total_completed = row["count"]
        except Exception:
            pass

        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if not os.path.islink(file_path):
                    total_storage_bytes += os.path.getsize(file_path)

    return {
        "total_completed_videos": total_completed,
        "total_storage_bytes": total_storage_bytes,
        "total_storage_mb": round(total_storage_bytes / (1024 * 1024), 2) if total_storage_bytes else 0.0
    }

