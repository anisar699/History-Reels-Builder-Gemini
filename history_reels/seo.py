import os
from history_reels import config

def write_seo_package():
    attributions_str = "\n".join(f"- {a}" for a in config.VIDEO_ATTRIBUTIONS)
    seo_content = f"""================================================================================
SEO PACKAGE — Facebook + Instagram (Urdu Script + Custom Music)
================================================================================

TITLE / HOOK:
{config.SEO_TITLE}

--------------------------------------------------------------------------------
PRIMARY CAPTION (for Instagram/Facebook feed)
--------------------------------------------------------------------------------
{config.SEO_DESCRIPTION}

HASHTAGS:
{config.SEO_HASHTAGS}

--------------------------------------------------------------------------------
QUICK CAPTION (copy-paste short version)
--------------------------------------------------------------------------------
{config.SEO_SHORT_CAPTION}

--------------------------------------------------------------------------------
MEDIA + MUSIC NOTES
--------------------------------------------------------------------------------
Media: {config.NUM_CLIPS} dynamic video clips downloaded via Pexels/Pixabay API.
Music: Custom Pool Music - Vibe: {config.BG_MUSIC_VIBE} (Track {config.BG_MUSIC_TRACK_INDEX}) - Royalty Free.

CREDITS & ATTRIBUTIONS:
{attributions_str}
================================================================================
"""
    seo_path = os.path.join(config.TOPIC_TEMP_DIR, "output.txt")
    os.makedirs(config.TOPIC_TEMP_DIR, exist_ok=True)
    with open(seo_path, "w", encoding="utf-8") as f:
        f.write(seo_content)
