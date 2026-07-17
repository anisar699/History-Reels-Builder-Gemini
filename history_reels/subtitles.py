import os
from history_reels.jobs import GenerationJob

def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def markdown_to_ass(text):
    text = str(text).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    # Convert newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\N")
    # Convert markdown **text** to ASS bold and golden-yellow color overrides
    parts = text.split("**")
    ass_text = ""
    for i, part in enumerate(parts):
        if i % 2 == 1:
            ass_text += f"{{\\b1\\c&H00FFFF&}}{part}{{\\b0\\c&HFFFFFF&}}"
        else:
            ass_text += part
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
