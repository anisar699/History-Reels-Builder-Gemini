import os
from history_reels import config

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
    # Convert newlines
    text = text.replace("\n", "\\N")
    # Convert markdown **text** to ASS bold and golden-yellow color overrides
    parts = text.split("**")
    ass_text = ""
    for i, part in enumerate(parts):
        if i % 2 == 1:
            ass_text += f"{{\\b1\\c&H00FFFF&}}{part}{{\\b0\\c&HFFFFFF&}}"
        else:
            ass_text += part
    return ass_text

def write_ass_subtitles(ass_path):
    start_times = [0.0] + config.SLIDE_TIMINGS[:-1]
    end_times = config.SLIDE_TIMINGS
    captions = [config.CAPTION_TEXT_1, config.CAPTION_TEXT_2, config.CAPTION_TEXT_3, config.CAPTION_TEXT_4]
    
    lines = []
    lines.append("[Script Info]")
    lines.append("Title: History Reel")
    lines.append("ScriptType: v4.00+")
    lines.append("WrapStyle: 0")
    lines.append("PlayResX: 720")
    lines.append("PlayResY: 1280")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # Outline 3, Shadow 2, Alignment 2 (bottom-center), MarginV 450 (lifts it up into center-middle region)
    lines.append("Style: Default,Noto Nastaliq Urdu,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,2,2,30,30,450,1")
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    
    for i in range(4):
        start_str = format_ass_time(start_times[i])
        end_str = format_ass_time(end_times[i])
        ass_text = markdown_to_ass(captions[i])
        lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}")
        
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"ASS subtitle file written: {ass_path}")
