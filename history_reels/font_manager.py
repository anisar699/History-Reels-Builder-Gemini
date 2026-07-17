"""Caption-font selection and validation shared by the dashboard and pipeline."""

from __future__ import annotations

import os
from typing import Any, Callable


FONT_PRESETS: dict[str, dict[str, Any]] = {
    "Jameel Noori Nastaleeq": {
        "language": "Urdu",
        "family": "Jameel Noori Nastaleeq",
        "filename": "Jameel Noori Nastaleeq.ttf",
        "url": "https://raw.githubusercontent.com/abid-mujtaba/ttf-jameel-noori-nastaleeq/master/Jameel%20Noori%20Nastaleeq.ttf",
        "bold": False,
    },
    "Noto Nastaliq Urdu": {
        "language": "Urdu",
        "family": "Noto Nastaliq Urdu",
        "filename": "NotoNastaliqUrdu-Bold.ttf",
        "url": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoNastaliqUrdu/NotoNastaliqUrdu-Bold.ttf",
        "bold": True,
    },
    "Montserrat Bold": {
        "language": "Latin",
        "family": "Montserrat",
        "filename": "Montserrat-Bold.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
        "bold": True,
    },
    "Roboto Bold": {
        "language": "Latin",
        "family": "Roboto",
        "filename": "Roboto-Bold.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
        "bold": True,
    },
    "Noto Sans Devanagari": {
        "language": "Hindi",
        "family": "Noto Sans Devanagari",
        "filename": "NotoSansDevanagari.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf",
        "bold": False,
    },
    "Noto Sans Arabic": {
        "language": "Arabic",
        "family": "Noto Sans Arabic",
        "filename": "NotoSansArabic.ttf",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansarabic/NotoSansArabic%5Bwdth%2Cwght%5D.ttf",
        "bold": False,
    },
}

LANGUAGE_FONT_OPTIONS = {
    "Urdu": ["Jameel Noori Nastaleeq", "Noto Nastaliq Urdu"],
    "English": ["Montserrat Bold", "Roboto Bold"],
    "Hindi": ["Noto Sans Devanagari"],
    "Arabic": ["Noto Sans Arabic"],
    "Roman Urdu": ["Montserrat Bold", "Roboto Bold"],
}


def font_options_for_language(language: str) -> list[str]:
    return list(LANGUAGE_FONT_OPTIONS.get(str(language), LANGUAGE_FONT_OPTIONS["English"]))


def get_font_preset(name: str) -> dict[str, Any]:
    return dict(FONT_PRESETS.get(str(name), FONT_PRESETS["Jameel Noori Nastaleeq"]))


def is_usable_font(path: str) -> bool:
    """Reject empty/error-page downloads while allowing valid compact fonts."""
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= 1024
    except OSError:
        return False


def font_family_from_file(path: str, fallback: str) -> str:
    """Read a font's display family when fontTools is installed; fail safely otherwise."""
    font = None
    try:
        from fontTools.ttLib import TTFont  # Optional at runtime for legacy installs.

        font = TTFont(path, lazy=True)
        names = font["name"].names
        for preferred_id in (16, 1):  # Typographic family, then legacy family.
            for record in names:
                if record.nameID == preferred_id:
                    try:
                        value = record.toUnicode().strip()
                    except Exception:
                        value = ""
                    if value:
                        return value
    except Exception:
        pass
    finally:
        if font is not None:
            try:
                font.close()
            except Exception:
                pass
    return fallback


def prepare_caption_font(job: Any, download: Callable[[str, str], None]) -> str:
    """Resolve a job's selected font without ever replacing a valid custom file."""
    custom_path = str(getattr(job, "CUSTOM_FONT_PATH", "") or "").strip()
    if is_usable_font(custom_path):
        saved_family = str(getattr(job, "CUSTOM_FONT_FAMILY", "") or "").strip()
        fallback_family = saved_family or os.path.splitext(os.path.basename(custom_path))[0]
        job.FONT_PATH = custom_path
        job.CAPTION_FONT_FAMILY = saved_family or font_family_from_file(custom_path, fallback_family)
        job.CAPTION_FONT_BOLD = bool(getattr(job, "CUSTOM_FONT_BOLD", False))
        return custom_path

    preset = get_font_preset(getattr(job, "CAPTION_FONT_PRESET", "Jameel Noori Nastaleeq"))
    font_path = os.path.join(job.ASSETS_DIR, preset["filename"])
    job.FONT_PATH = font_path
    job.CAPTION_FONT_FAMILY = preset["family"]
    job.CAPTION_FONT_BOLD = bool(preset.get("bold", False))
    # Compatibility with existing code and older saved job records.
    job.URDU_FONT_NAME = preset["family"]
    if not is_usable_font(font_path):
        print(f"Caption font '{preset['family']}' not found. Downloading it once...")
        try:
            download(preset["url"], font_path)
        except Exception as error:
            print(f"Failed to download caption font '{preset['family']}': {error}")
    return font_path
