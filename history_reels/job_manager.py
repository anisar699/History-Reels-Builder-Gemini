"""In-process background queue for local dashboard generation jobs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import os
import subprocess
import sys
from threading import Lock
from typing import Any, Callable

from history_reels.job_store import JobStore, restore_safe_settings
from history_reels.jobs import GenerationJob, create_generation_job, create_retry_job


def _run_generation(**kwargs: Any) -> bool:
    # Delayed import prevents a circular import with the CLI lifecycle helpers.
    from history_reels.cli import generate_video_for_topic

    return generate_video_for_topic(**kwargs)


class JobManager:
    """Submit, cancel, and retry one-machine renders without blocking Streamlit."""

    def __init__(self, max_workers: int = 1, runner: Callable[..., bool] | None = None, mode: str = "thread"):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="history-reel")
        self._runner = runner or _run_generation
        self._futures: dict[str, Future] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self.mode = mode if mode in {"thread", "process"} else "thread"
        self._lock = Lock()

    def submit(
        self,
        job: GenerationJob,
        *,
        topic: Any,
        provider: str,
        manual_script_data: dict[str, Any] | None = None,
        is_raw_script: bool = False,
        attempt: int = 1,
        max_attempts: int | None = None,
    ) -> str:
        request = {
            "label": self._label(topic, manual_script_data),
            "topic": topic,
            "provider": provider,
            "manual_script_data": manual_script_data,
            "is_raw_script": bool(is_raw_script),
            "retry_of": getattr(job, "RETRY_OF", ""),
            "attempt": attempt,
            "max_attempts": max_attempts or int(getattr(job, "MAX_JOB_ATTEMPTS") or 2),
        }
        store = JobStore(job.OUTPUT_DIR)
        job.history_store = store
        job.status = "queued"
        store.create_job(job, request)
        if self.mode == "process":
            self._launch_process(job.OUTPUT_DIR, job.job_id)
            return job.job_id
        future = self._executor.submit(self._execute, job, request)
        with self._lock:
            self._futures[job.job_id] = future
        return job.job_id

    def _launch_process(self, output_dir: str, job_id: str) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "history_reels.worker", "--output-dir", output_dir, "--job-id", job_id],
            cwd=os.getcwd(),
            creationflags=creationflags,
        )
        with self._lock:
            self._processes[job_id] = process

    def _execute(self, job: GenerationJob, request: dict[str, Any]) -> bool:
        if job.history_store:
            record = job.history_store.get_job(job.job_id)
            if record and record.get("status") == "cancelled":
                return False

        try:
            result = self._runner(
                topic=request.get("topic"),
                provider=request.get("provider", "auto"),
                manual_script_data=request.get("manual_script_data"),
                is_raw_script=bool(request.get("is_raw_script")),
                job=job,
            )
        except Exception as error:
            job.status = "failed"
            job.last_error = f"Background worker failure: {error}"
            if job.history_store:
                job.history_store.mark_failed(job, job.last_error)
            result = False

        # A worker must always leave a durable terminal status.  This keeps a
        # faulty integration from displaying a permanently queued render.
        if result and job.status != "succeeded":
            job.last_error = "Generation worker returned success without marking the render complete."
            job.status = "failed"
            if job.history_store:
                job.history_store.mark_failed(job, job.last_error)
            result = False
        elif not result and job.status not in {"failed", "cancelled"}:
            job.last_error = "Generation worker stopped before completing the render."
            job.status = "failed"
            if job.history_store:
                job.history_store.mark_failed(job, job.last_error)

        max_attempts = int(request.get("max_attempts") or 1)
        attempt = int(request.get("attempt") or 1)
        if not result and job.status == "failed" and attempt < max_attempts and self._is_retryable(job.last_error):
            retry_job = create_retry_job(job)
            retry_job.history_store = None
            retry_id = self.submit(
                retry_job,
                topic=request.get("topic"),
                provider=request.get("provider", "auto"),
                manual_script_data=request.get("manual_script_data"),
                is_raw_script=bool(request.get("is_raw_script")),
                attempt=attempt + 1,
                max_attempts=max_attempts,
            )
            if job.history_store:
                job.history_store.record_event(
                    job.job_id,
                    "warning",
                    "retry",
                    f"Transient failure detected; automatic retry queued as {retry_id}.",
                )
        return result

    def cancel(self, output_dir: str, job_id: str) -> bool:
        """Request cancellation, kill tracked media/worker processes, and finalize queued jobs."""
        from history_reels.ffmpeg_runner import kill_job_processes

        store = JobStore(output_dir)
        requested = store.request_cancellation(job_id)
        record = store.get_job(job_id)
        status = str((record or {}).get("status") or "")

        # Queued jobs can be terminalized immediately; running jobs stay
        # cancel_requested until the worker acknowledges or is killed.
        if requested and status == "queued":
            placeholder = type("QueuedJob", (), {"job_id": job_id})()
            store.mark_cancelled(placeholder, "Cancellation requested")

        with self._lock:
            future = self._futures.get(job_id)
            process = self._processes.get(job_id)

        if future:
            future.cancel()

        # Hard-stop tracked ffmpeg/edge-tts children and process workers.
        kill_job_processes(job_id)
        if process and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            except OSError:
                pass
            # If the worker never got a chance to mark cancelled, finalize now.
            latest = store.get_job(job_id)
            if latest and latest.get("status") == "running":
                placeholder = type("QueuedJob", (), {"job_id": job_id})()
                store.mark_cancelled(placeholder, "Cancellation forced by stopping the worker process.")
        return requested

    def recover_queued(self, output_dir: str) -> int:
        """Restart persisted queued jobs when process-worker mode is enabled."""
        if self.mode != "process":
            return 0
        job_ids = JobStore(output_dir).list_queued_job_ids()
        with self._lock:
            active_ids = {
                job_id
                for job_id, process in self._processes.items()
                if process.poll() is None
            }
        recoverable_ids = [job_id for job_id in job_ids if job_id not in active_ids]
        for job_id in recoverable_ids:
            self._launch_process(output_dir, job_id)
        return len(recoverable_ids)

    def reconcile_orphaned_thread_jobs(self, output_dir: str) -> int:
        """Turn jobs stranded by a dashboard restart into retryable failures.

        Thread workers only live for the lifetime of the Streamlit process.
        Queued and running records without an active future are otherwise
        stuck forever after a restart.
        """
        if self.mode != "thread":
            return 0
        store = JobStore(output_dir)
        with self._lock:
            active_ids = {
                job_id
                for job_id, future in self._futures.items()
                if not future.done()
            }
        orphaned_ids = [
            job_id for job_id in store.list_queued_job_ids()
            if job_id not in active_ids
        ]
        for job_id in orphaned_ids:
            store.mark_failed_by_id(
                job_id,
                "Queued render was interrupted before a worker could start. Use Retry to create a fresh render job.",
            )
        stuck_running = [
            job_id for job_id in store.list_running_job_ids()
            if job_id not in active_ids
        ]
        for job_id in stuck_running:
            store.mark_failed_by_id(
                job_id,
                "Running render was interrupted (worker lost after restart). Use Retry to create a fresh render job.",
            )
        return len(orphaned_ids) + len(stuck_running)

    def retry(self, output_dir: str, runtime_config: Any, job_id: str) -> str | None:
        record = JobStore(output_dir).get_job(job_id)
        if not record:
            return None
        request = record.get("request_json")
        if not isinstance(request, dict):
            return None
        job = create_generation_job(runtime_config)
        restore_safe_settings(job, record.get("settings_json"))
        job.RETRY_OF = job_id
        return self.submit(
            job,
            topic=request.get("topic"),
            provider=request.get("provider", "auto"),
            manual_script_data=request.get("manual_script_data"),
            is_raw_script=bool(request.get("is_raw_script")),
        )

    @staticmethod
    def _is_retryable(error_message: str) -> bool:
        message = str(error_message).lower()
        transient_terms = ("timeout", "network", "connection", "rate limit", "429", "download", "ffmpeg", "temporar")
        return any(term in message for term in transient_terms)

    @staticmethod
    def _label(topic: Any, manual_script_data: dict[str, Any] | None) -> str:
        if manual_script_data:
            return str(manual_script_data.get("title", "Manual script"))[:500]
        if isinstance(topic, dict):
            return str(topic.get("title") or topic.get("link") or "Imported article")[:500]
        return str(topic or "Universal creator demo")[:500]


_managers: dict[str, JobManager] = {}
_manager_lock = Lock()


def get_job_manager(mode: str = "thread") -> JobManager:
    normalized_mode = mode if mode in {"thread", "process"} else "thread"
    with _manager_lock:
        if normalized_mode not in _managers:
            _managers[normalized_mode] = JobManager(mode=normalized_mode)
        return _managers[normalized_mode]
