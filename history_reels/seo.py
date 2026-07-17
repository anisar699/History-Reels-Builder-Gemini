import os
from history_reels.jobs import GenerationJob

def write_seo_package(job: GenerationJob):
    attributions_str = "\n".join(f"- {a}" for a in job.VIDEO_ATTRIBUTIONS)
    seo_content = f"""================================================================================
SEO PACKAGE — Facebook + Instagram (Urdu Script + Custom Music)
================================================================================

TITLE / HOOK:
{job.SEO_TITLE}

--------------------------------------------------------------------------------
PRIMARY CAPTION (for Instagram/Facebook feed)
--------------------------------------------------------------------------------
{job.SEO_DESCRIPTION}

HASHTAGS:
{job.SEO_HASHTAGS}

--------------------------------------------------------------------------------
QUICK CAPTION (copy-paste short version)
--------------------------------------------------------------------------------
{job.SEO_SHORT_CAPTION}

--------------------------------------------------------------------------------
MEDIA + MUSIC NOTES
--------------------------------------------------------------------------------
Media: {job.NUM_CLIPS} dynamic video clips downloaded via Pexels/Pixabay API.
Music: Custom Pool Music - Vibe: {job.BG_MUSIC_VIBE} (Track {job.BG_MUSIC_TRACK_INDEX}) - Royalty Free.

CREDITS & ATTRIBUTIONS:
{attributions_str}
================================================================================
"""
    seo_path = os.path.join(job.TOPIC_TEMP_DIR, "output.txt")
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
    with open(seo_path, "w", encoding="utf-8") as f:
        f.write(seo_content)
