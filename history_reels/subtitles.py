import os
import re
from history_reels.jobs import GenerationJob


_RASTER_CAPTION_LANGUAGES = {"urdu", "arabic"}


def uses_rasterized_captions(job: GenerationJob) -> bool:
    """Use Pillow/RAQM for scripts that libass can fail to shape on Windows."""
    language = str(getattr(job, "CONTENT_LANGUAGE", "") or "").strip().lower()
    if language in _RASTER_CAPTION_LANGUAGES:
        return True
    captions = getattr(job, "CAPTIONS", []) or []
    return any(
        "\u0600" <= character <= "\u08ff"
        for caption in captions
        for character in str(caption)
    )


def _plain_caption_text(text) -> str:
    return str(text or "").replace("**", "").replace("\r\n", "\n").replace("\r", "\n")


_LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9]")


def _font_for_text(text, primary_font, fallback_font):
    if fallback_font is not None and _LATIN_OR_DIGIT.search(str(text or "")):
        return fallback_font
    return primary_font


def _load_mixed_script_fallback(ImageFont, job, font_size):
    configured = str(getattr(job, "CAPTION_FALLBACK_FONT_PATH", "") or "").strip()
    windows_dir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        configured,
        os.path.join(windows_dir, "Fonts", "arial.ttf"),
        os.path.join(windows_dir, "Fonts", "segoeui.ttf"),
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(
                candidate,
                font_size,
                layout_engine=ImageFont.Layout.RAQM,
            )
        except (OSError, ValueError):
            continue
    raise RuntimeError(
        "Mixed Urdu/English captions need a font with both Arabic and Latin glyphs. "
        "Configure CAPTION_FALLBACK_FONT_PATH and retry."
    )


def _wrap_caption_lines(draw, text, primary_font, fallback_font, max_width, direction, language):
    """Wrap logical-order text while Pillow/RAQM performs visual RTL shaping."""
    lines = []
    for paragraph in _plain_caption_text(text).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            measuring_font = _font_for_text(candidate, primary_font, fallback_font)
            width = draw.textlength(
                candidate,
                font=measuring_font,
                direction=direction,
                language=language,
            )
            if width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def render_caption_overlays(job: GenerationJob):
    """Render timed transparent PNG captions with reliable complex-text shaping."""
    try:
        from PIL import Image, ImageDraw, ImageFont, features
    except ImportError as error:
        raise RuntimeError(
            "Urdu/Arabic caption rendering requires Pillow with RAQM support. "
            "Install the project's pinned dependencies and retry."
        ) from error

    if not features.check_feature("raqm"):
        raise RuntimeError(
            "This Pillow build has no RAQM support, so Urdu/Arabic text cannot be "
            "shaped safely. Install a Pillow build with libraqm support."
        )

    font_path = os.path.abspath(str(getattr(job, "FONT_PATH", "") or ""))
    if not os.path.isfile(font_path):
        raise FileNotFoundError(f"Caption font was not found: {font_path}")

    width = int(getattr(job, "VIDEO_WIDTH", 720) or 720)
    height = int(getattr(job, "VIDEO_HEIGHT", 1280) or 1280)
    default_size = 52 if height >= 1000 else max(30, int(height * 0.05))
    font_size = int(getattr(job, "CAPTION_FONT_SIZE", default_size) or default_size)
    font = ImageFont.truetype(
        font_path,
        font_size,
        layout_engine=ImageFont.Layout.RAQM,
    )
    fallback_font = _load_mixed_script_fallback(ImageFont, job, font_size)
    language_name = str(getattr(job, "CONTENT_LANGUAGE", "Urdu") or "Urdu").lower()
    language = "ar" if language_name == "arabic" else "ur"
    direction = "rtl"
    captions = getattr(job, "CAPTIONS", []) or []
    if not captions:
        captions = [getattr(job, f"CAPTION_TEXT_{i}", "") for i in range(1, 5)]
    end_times = list(getattr(job, "SLIDE_TIMINGS", []) or [])
    start_times = [0.0] + end_times[:-1]
    margin_v = 450 if height == 1280 else int(height * 0.15)
    padding_x = max(24, int(width * 0.045))
    padding_y = max(16, int(font_size * 0.4))
    stroke_width = max(2, int(round(font_size * 0.075)))
    line_spacing = max(6, int(font_size * 0.18))
    overlays = []

    for index, (caption, start, end) in enumerate(
        zip(captions, start_times, end_times),
        start=1,
    ):
        measuring = Image.new("L", (width, max(height, 1)), 0)
        measure_draw = ImageDraw.Draw(measuring)
        lines = _wrap_caption_lines(
            measure_draw,
            caption,
            font,
            fallback_font,
            width - (padding_x * 2),
            direction,
            language,
        )
        line_fonts = [_font_for_text(line, font, fallback_font) for line in lines]
        metrics = [
            measure_draw.textbbox(
                (0, 0),
                line or " ",
                font=line_font,
                direction=direction,
                language=language,
                stroke_width=stroke_width,
            )
            for line, line_font in zip(lines, line_fonts)
        ]
        text_height = sum(max(1, box[3] - box[1]) for box in metrics)
        band_height = min(
            height,
            text_height + line_spacing * max(0, len(lines) - 1) + padding_y * 2,
        )
        image = Image.new("RGBA", (width, band_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cursor_y = padding_y
        for line, box, line_font in zip(lines, metrics, line_fonts):
            line_height = max(1, box[3] - box[1])
            draw.text(
                (width / 2, cursor_y - box[1]),
                line,
                font=line_font,
                fill=(255, 255, 255, 255),
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0, 235),
                anchor="ma",
                align="center",
                direction=direction,
                language=language,
            )
            cursor_y += line_height + line_spacing

        alpha_box = image.getchannel("A").getbbox()
        if not alpha_box:
            raise RuntimeError(
                f"Caption {index} produced no visible glyphs with "
                f"{os.path.basename(font_path)}."
            )
        overlay_path = os.path.join(job.TOPIC_TEMP_DIR, f"caption_overlay_{index:02d}.png")
        image.save(overlay_path, "PNG")
        overlays.append(
            {
                "path": overlay_path,
                "start": float(start),
                "end": float(end),
                "y": max(0, height - margin_v - band_height),
            }
        )
    return overlays


def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    if s == 60:
        m += 1
        s = 0
    if m >= 60:
        h += 1
        m = m % 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def markdown_to_ass(text):
    text = str(text).replace("\\", "\\\\")
    # Convert newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\N")
    # Convert markdown **text** to ASS bold and golden-yellow color overrides
    parts = text.split("**")
    ass_text = ""
    for i, part in enumerate(parts):
        clean_part = part.replace("{", "\\{").replace("}", "\\}")
        if i % 2 == 1:
            ass_text += f"{{\\b1\\c&H00FFFF&}}{clean_part}{{\\b0\\c&HFFFFFF&}}"
        else:
            ass_text += clean_part
    return ass_text

def write_ass_subtitles(ass_path, job: GenerationJob):
    start_times = [0.0] + job.SLIDE_TIMINGS[:-1]
    end_times = job.SLIDE_TIMINGS
    captions = getattr(job, "CAPTIONS", [])
    if not captions:
        captions = [getattr(job, f"CAPTION_TEXT_{i}", "") for i in range(1, 5)]
    
    lines = []
    lines.append("[Script Info]")
    lines.append("Title: AI Reel")
    lines.append("ScriptType: v4.00+")
    lines.append("WrapStyle: 0")
    width = getattr(job, "VIDEO_WIDTH", 720)
    height = getattr(job, "VIDEO_HEIGHT", 1280)
    margin_v = 450 if height == 1280 else int(height * 0.15)
    
    lines.append(f"PlayResX: {width}")
    lines.append(f"PlayResY: {height}")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    font_name = getattr(job, "CAPTION_FONT_FAMILY", getattr(job, "URDU_FONT_NAME", "Jameel Noori Nastaleeq"))
    default_size = 52 if height >= 1000 else max(30, int(height * 0.05))
    font_size = int(getattr(job, "CAPTION_FONT_SIZE", default_size) or default_size)
    font_bold = -1 if getattr(job, "CAPTION_FONT_BOLD", False) else 0
    lines.append(f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{font_bold},0,0,0,100,100,0,0,1,3,2,2,30,30,{margin_v},1")
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    
    num_slides = min(len(start_times), len(end_times), len(captions))
    for i in range(num_slides):
        start_str = format_ass_time(start_times[i])
        end_str = format_ass_time(end_times[i])
        ass_text = markdown_to_ass(captions[i])
        lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}")
        
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"ASS subtitle file written: {ass_path}")
