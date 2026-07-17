import os
from history_reels.jobs import GenerationJob

def write_seo_package(job: GenerationJob):
    attributions_str = "\n".join(f"- {a}" for a in job.VIDEO_ATTRIBUTIONS)
    music_note = f"{getattr(job, 'MUSIC_SOURCE', 'local library').title()} original track — Vibe: {job.BG_MUSIC_VIBE} (Track {job.BG_MUSIC_TRACK_INDEX})."
    seo_content = f"""================================================================================
REEL PUBLISHING PACKAGE — Short-Form Video
================================================================================

TITLE / HOOK:
{job.SEO_TITLE}

--------------------------------------------------------------------------------
PRIMARY SOCIAL CAPTION
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
Creative brief: {getattr(job, 'CONTENT_NICHE', 'General')} · {getattr(job, 'CONTENT_LANGUAGE', 'Urdu')} · {getattr(job, 'CONTENT_TONE', 'Engaging & Clear')}
Target platform: {getattr(job, 'TARGET_PLATFORM', 'Instagram Reels')} · Visual style: {getattr(job, 'VISUAL_STYLE', 'Cinematic')}
Media: {job.NUM_CLIPS} dynamic visual clips from the configured media sources.
Media quality profile: {getattr(job, 'MEDIA_QUALITY_PROFILE', 'balanced')} (minimum source dimension: {getattr(job, 'MIN_MEDIA_DIMENSION', 480)}px).
Music: {music_note}

CREDITS & ATTRIBUTIONS:
{attributions_str}
================================================================================
"""
    seo_path = os.path.join(job.TOPIC_TEMP_DIR, "output.txt")
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
    with open(seo_path, "w", encoding="utf-8") as f:
        f.write(seo_content)
