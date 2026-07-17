"""Per-generation state and isolated workspace management.

The dashboard historically stored mutable generation state directly on
``history_reels.config``.  That made one run capable of changing another
run's files, metadata, media attribution, and render settings.  A
``GenerationJob`` is now the single owner of that mutable state.
"""

from __future__ import annotations

import copy
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _safe_component(value: str, fallback: str = "reel") -> str:
    """Return a filesystem-friendly name while retaining readable titles."""
    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", value).strip()
    return cleaned or fallback


@dataclass
class GenerationJob:
    """A self-contained configuration and workspace for one video render."""

    job_id: str
    workspace: str
    values: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_error: str = ""

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"job_id", "workspace", "values", "created_at", "last_error"}:
            object.__setattr__(self, name, value)
        else:
            self.values[name] = value

    @property
    def short_id(self) -> str:
        return self.job_id.rsplit("-", 1)[-1]

    @property
    def video_path(self) -> str:
        return os.path.join(self.OUTPUT_DIR, f"{self.OUTPUT_NAME}.mp4")

    @property
    def seo_path(self) -> str:
        return os.path.join(self.OUTPUT_DIR, f"{self.OUTPUT_NAME}.txt")

    def prepare_workspace(self) -> None:
        os.makedirs(self.TOPIC_TEMP_DIR, exist_ok=False)

    def reset_runtime_state(self) -> None:
        self.SLIDE_TIMINGS = []
        self.DOWNLOADED_VIDEO_IDS = set()
        self.VIDEO_ATTRIBUTIONS = []
        self.TRANSITION_OFFSETS = []
        self.NUM_CLIPS = 0
        self.last_error = ""

    def apply_script(self, ai_data: dict[str, Any], track_index: int) -> None:
        self.TOPIC_TITLE = ai_data["title"]
        self.TOPIC_YEAR = ai_data["year"]
        self.BG_MUSIC_VIBE = ai_data["bg_music_vibe"]
        self.BG_MUSIC_TRACK_INDEX = track_index

        clean_title = _safe_component(self.TOPIC_TITLE, "history_reel")
        clean_year = _safe_component(self.TOPIC_YEAR, "history")
        # The job suffix prevents two simultaneous renders from overwriting a
        # deliverable that has the same title and year.
        self.OUTPUT_NAME = f"{clean_title} {clean_year} Asad Voice {self.short_id}"

        self.CAPTIONS = ai_data.get("captions", [])
        self.NARRATIONS = ai_data.get("narrations", [])
        if not self.CAPTIONS and "caption_text_1" in ai_data:
            self.CAPTIONS = [ai_data.get(f"caption_text_{i}", "") for i in range(1, 5)]
        if not self.NARRATIONS and "narration_text_1" in ai_data:
            self.NARRATIONS = [ai_data.get(f"narration_text_{i}", "") for i in range(1, 5)]

        self.FULL_SPEECH_TEXT = " ".join(n for n in self.NARRATIONS if n.strip())
        self.QUERIES = list(ai_data["queries"])
        self.SEO_TITLE = ai_data.get("seo_title", f"{self.TOPIC_TITLE} ({self.TOPIC_YEAR})")
        self.SEO_DESCRIPTION = ai_data.get("seo_description", self.FULL_SPEECH_TEXT)
        self.SEO_HASHTAGS = ai_data.get("seo_hashtags", "#History #UrduMysteries")
        self.SEO_SHORT_CAPTION = ai_data.get("seo_short_caption", self.FULL_SPEECH_TEXT[:100])


def create_generation_job(runtime_config: Any) -> GenerationJob:
    """Snapshot uppercase runtime settings into a new, unique job workspace.

    API keys and render options are captured when the user starts a job, so a
    later dashboard interaction cannot alter an already-running pipeline.
    """
    values = {
        key: copy.deepcopy(value)
        for key, value in vars(runtime_config).items()
        if key.isupper()
    }
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    jobs_root = os.path.join(values["TEMP_DIR"], "jobs")
    workspace = os.path.join(jobs_root, job_id)
    values["TOPIC_TEMP_DIR"] = workspace
    values["LAST_ERROR_MESSAGE"] = ""
    values["SLIDE_TIMINGS"] = []
    values["DOWNLOADED_VIDEO_IDS"] = set()
    values["VIDEO_ATTRIBUTIONS"] = []
    values["TRANSITION_OFFSETS"] = []
    return GenerationJob(job_id=job_id, workspace=workspace, values=values)
