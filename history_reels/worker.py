"""Entry point for optional restart-recoverable process workers."""

from __future__ import annotations

import argparse

from history_reels import config
from history_reels.cli import generate_video_for_topic
from history_reels.job_manager import JobManager
from history_reels.job_store import JobStore, restore_safe_settings
from history_reels.jobs import create_generation_job


def run_job(output_dir: str, job_id: str) -> bool:
    store = JobStore(output_dir)
    record = store.get_job(job_id)
    if not record or record["status"] != "queued":
        return False
    # Atomic claim prevents two process workers from executing the same job.
    if not store.claim_job(job_id):
        return False
    try:
        request = record["request_json"]
        job = create_generation_job(config)
        restore_safe_settings(job, record.get("settings_json"))
        job.job_id = job_id
        job.workspace = record["workspace"]
        job.TOPIC_TEMP_DIR = record["workspace"]
        job.OUTPUT_DIR = output_dir
        job.history_store = store
        job.status = "running"
        result = generate_video_for_topic(
            topic=request.get("topic"),
            provider=request.get("provider", "auto"),
            manual_script_data=request.get("manual_script_data"),
            is_raw_script=bool(request.get("is_raw_script")),
            job=job,
        )
        updated = store.get_job(job_id)
        if result and (not updated or updated.get("status") != "succeeded"):
            store.mark_failed_by_id(job_id, "Process worker returned success without marking the render complete.")
            return False

        attempt = int(request.get("attempt") or 1)
        max_attempts = int(request.get("max_attempts") or 1)
        if (
            not result
            and updated
            and updated.get("status") == "failed"
            and attempt < max_attempts
            and JobManager._is_retryable(updated.get("error_message", ""))
        ):
            retry_job = create_generation_job(config)
            restore_safe_settings(retry_job, record.get("settings_json"))
            retry_job.OUTPUT_DIR = output_dir
            retry_job.RETRY_OF = job_id
            retry_id = JobManager(mode="process").submit(
                retry_job,
                topic=request.get("topic"),
                provider=request.get("provider", "auto"),
                manual_script_data=request.get("manual_script_data"),
                is_raw_script=bool(request.get("is_raw_script")),
                attempt=attempt + 1,
                max_attempts=max_attempts,
            )
            store.record_event(
                job_id,
                "warning",
                "retry",
                f"Transient failure detected; automatic retry queued as {retry_id}.",
            )
        return result
    except Exception as error:
        message = f"Process worker failure: {error}"
        store.mark_failed_by_id(job_id, message)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="History Reels background worker")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    return 0 if run_job(args.output_dir, args.job_id) else 1


if __name__ == "__main__":
    raise SystemExit(main())
