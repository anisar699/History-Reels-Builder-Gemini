import os
from history_reels.jobs import GenerationJob

def write_seo_package(job: GenerationJob):
    attributions = getattr(job, "VIDEO_ATTRIBUTIONS", [])
    attributions_str = "\n".join(f"- {a}" for a in attributions)
    music_vibe = getattr(job, 'BG_MUSIC_VIBE', '')
    music_track_index = getattr(job, 'BG_MUSIC_TRACK_INDEX', '')
    music_note = f"{getattr(job, 'MUSIC_SOURCE', 'local library').title()} original track — Vibe: {music_vibe} (Track {music_track_index})."
    
    seo_title = getattr(job, 'SEO_TITLE', '')
    seo_description = getattr(job, 'SEO_DESCRIPTION', '')
    seo_hashtags = getattr(job, 'SEO_HASHTAGS', '')
    seo_short_caption = getattr(job, 'SEO_SHORT_CAPTION', '')
    num_clips = getattr(job, 'NUM_CLIPS', 0)

    seo_content = f"""================================================================================
REEL PUBLISHING PACKAGE — Short-Form Video
================================================================================

TITLE / HOOK:
{seo_title}

--------------------------------------------------------------------------------
PRIMARY SOCIAL CAPTION
--------------------------------------------------------------------------------
{seo_description}

HASHTAGS:
{seo_hashtags}

--------------------------------------------------------------------------------
QUICK CAPTION (copy-paste short version)
--------------------------------------------------------------------------------
{seo_short_caption}

--------------------------------------------------------------------------------
MEDIA + MUSIC NOTES
--------------------------------------------------------------------------------
Creative brief: {getattr(job, 'CONTENT_NICHE', 'General')} · {getattr(job, 'CONTENT_LANGUAGE', 'Urdu')} · {getattr(job, 'CONTENT_TONE', 'Engaging & Clear')}
Target platform: {getattr(job, 'TARGET_PLATFORM', 'Instagram Reels')} · Visual style: {getattr(job, 'VISUAL_STYLE', 'Cinematic')}
Media: {num_clips} dynamic visual clips from the configured media sources.
Media quality profile: {getattr(job, 'MEDIA_QUALITY_PROFILE', 'balanced')} (minimum source dimension: {getattr(job, 'MIN_MEDIA_DIMENSION', 480)}px).
Music: {music_note}

CREDITS & ATTRIBUTIONS:
{attributions_str}
================================================================================
"""
    seo_path = os.path.join(job.TOPIC_TEMP_DIR, "output.txt")
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
        f.write(seo_content)
