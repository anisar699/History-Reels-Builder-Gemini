import os
import subprocess
from history_reels import config
from history_reels.subtitles import write_ass_subtitles

def get_video_dimensions(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        parts = res.stdout.strip().split(",")
        return int(parts[0]), int(parts[1])
    except (subprocess.CalledProcessError, IndexError, ValueError) as e:
        print(f"Warning: Could not read dimensions of {path}: {e}")
        return 0, 0

def build_video_frames(voice_dur):
    print("Extracting clips from source videos...")
    
    target_clip_dur = getattr(config, "CLIP_DURATION_TARGET", 5.0)
    divisor = max(0.1, target_clip_dur - config.CROSSFADE_DUR)
    estimated_clips = int(round((voice_dur - config.CROSSFADE_DUR) / divisor))
    
    repeats = 2 if target_clip_dur < 4.0 else 1
    max_available = len(config.QUERIES) * repeats
    num_clips = max(4, min(estimated_clips, max_available))
    
    config.NUM_CLIPS = num_clips
    
    total_visual_dur = voice_dur + (config.NUM_CLIPS - 1) * config.CROSSFADE_DUR
    clip_dur = total_visual_dur / config.NUM_CLIPS
    print(f"Dynamic clip duration: {clip_dur:.2f}s (Target: {target_clip_dur:.2f}s, Cuts: {config.NUM_CLIPS}) (Total video duration: {voice_dur:.2f}s)")
    
    clips = []
    for i in range(1, config.NUM_CLIPS + 1):
        raw_path_mp4 = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{i}.mp4")
        raw_path_jpg = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{i}.jpg")
        raw_path_png = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{i}.png")
        
        clip_path = os.path.join(config.TOPIC_TEMP_DIR, f"clip{i}.mp4")
        clips.append(clip_path)
        
        if os.path.exists(raw_path_mp4):
            # Process Video Clip
            w, h = get_video_dimensions(raw_path_mp4)
            if w <= 0 or h <= 0:
                print(f"Warning: Invalid dimensions ({w}x{h}) for clip {i}. Skipping.")
                # Create a black placeholder clip
                cmd = [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"color=c=black:s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:d={clip_dur:.3f}:r={config.FPS}",
                    "-an", clip_path
                ]
                subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
                continue
            target_aspect = config.VIDEO_WIDTH / config.VIDEO_HEIGHT
            if (w / h) > target_aspect:
                crop_h = h
                crop_w = int(h * target_aspect)
                if crop_w % 2 != 0:
                    crop_w += 1
            else:
                crop_w = w
                crop_h = int(w / target_aspect)
                if crop_h % 2 != 0:
                    crop_h += 1

            crop_w = min(crop_w, w - (w % 2))
            crop_h = min(crop_h, h - (h % 2))
            offset_x = max(0, (w - crop_w) // 2)
            offset_y = max(0, (h - crop_h) // 2)
                
            vf = f"crop={crop_w}:{crop_h}:{offset_x}:{offset_y},scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}"
            cmd = [
                "ffmpeg", "-y", "-ss", "0.0", "-stream_loop", "-1", "-i", raw_path_mp4, "-t", f"{clip_dur:.3f}",
                "-vf", vf, "-an", "-r", str(config.FPS), clip_path
            ]
            subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
            
        else:
            # Process Image Clip (Convert to video using Ken Burns zoom effect)
            img_path = raw_path_jpg if os.path.exists(raw_path_jpg) else raw_path_png
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"Error: No video or image clip found for index {i}")
                
            scale_w = int(config.VIDEO_WIDTH * 2)
            scale_h = int(config.VIDEO_HEIGHT * 2)
            vf_zoom = f"scale={scale_w}:{scale_h},zoompan=z='zoom+0.0005':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(config.FPS * clip_dur)}:s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT},fps={config.FPS}"
            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", img_path, "-t", f"{clip_dur:.3f}",
                "-vf", vf_zoom, "-an", "-r", str(config.FPS), clip_path
            ]
            subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
        
    print("Crossfading clips...")
    silent_temp = os.path.join(config.TOPIC_TEMP_DIR, "silent_temp.mp4")
    
    if config.NUM_CLIPS <= 1:
        import shutil
        if clips:
            shutil.copy2(clips[0], silent_temp)
        return
        
    filter_parts = []
    last_label = "0:v"
    curr_offset = clip_dur - config.CROSSFADE_DUR
    config.TRANSITION_OFFSETS = []
    
    transition_style = getattr(config, "VIDEO_TRANSITION", "fade").lower()
    allowed_transitions = ["fade", "slideleft", "slideright", "slideup", "slidedown", "wipeleft", "wiperight", "zoomin", "dissolve", "pixelize", "radial"]
    
    for i in range(1, config.NUM_CLIPS):
        config.TRANSITION_OFFSETS.append(curr_offset)
        out_label = f"v{i}"
        t_style = transition_style
        if t_style == "random":
            import random
            t_style = random.choice(allowed_transitions)
        elif t_style not in allowed_transitions:
            t_style = "fade"
            
        filter_parts.append(f"[{last_label}][{i}:v]xfade=transition={t_style}:duration={config.CROSSFADE_DUR}:offset={curr_offset:.3f}[{out_label}]")
        last_label = out_label
        curr_offset += max(0.1, clip_dur - config.CROSSFADE_DUR)
        
    filter_complex = ";".join(filter_parts)
    
    cmd_fade = ["ffmpeg", "-y"]
    for c in clips:
        cmd_fade.extend(["-i", c])
    cmd_fade.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]", "-r", str(config.FPS), silent_temp
    ])
    subprocess.run(cmd_fade, check=True, stdin=subprocess.DEVNULL)

def setup_fontconfig():
    fonts_dir = os.path.join(config.OUTPUT_DIR, "fonts")
    fonts_dir_clean = fonts_dir.replace("\\", "/")
    
    fonts_conf_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <dir>{fonts_dir_clean}</dir>
</fontconfig>
"""
    fonts_conf_path = os.path.join(config.TOPIC_TEMP_DIR, "fonts.conf")
    with open(fonts_conf_path, "w", encoding="utf-8") as f:
        f.write(fonts_conf_content)
        
    os.environ["FONTCONFIG_FILE"] = fonts_conf_path
    print(f"Fontconfig local file configured: {fonts_conf_path}")

def generate_whoosh_sound():
    whoosh_path = os.path.join(config.TOPIC_TEMP_DIR, "whoosh.wav")
    if os.path.exists(whoosh_path):
        return whoosh_path
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "aevalsrc=sin(2*PI*(180+500*sin(PI*t/0.5))*t):d=0.5",
        "-af", "volume='sin(PI*t/0.5)':eval=frame",
        whoosh_path
    ]
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
    return whoosh_path

def run_ffmpeg(voice_dur):
    print("Mixing background music and voiceover...")
    drone_wav = os.path.join(config.TOPIC_TEMP_DIR, "drone.wav")
    music_mp3 = os.path.join(config.MUSIC_DIR, f"{config.BG_MUSIC_VIBE}_{config.BG_MUSIC_TRACK_INDEX}.mp3")
    voice_mp3 = os.path.join(config.TOPIC_TEMP_DIR, "voice.mp3")
    
    # Mix audio with dynamic filters
    ducking = getattr(config, "AUDIO_DUCKING", True)
    mastering = getattr(config, "VOICE_MASTERING", True)
    trans_sfx = getattr(config, "TRANSITION_SFX", False)
    
    # 1. Voice processing chain
    voice_filter = f"[1:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS"
    if mastering:
        voice_filter += ",equalizer=f=100:width_type=h:width=100:g=4,equalizer=f=3500:width_type=h:width=2000:g=2,acompressor=threshold=0.08:ratio=3:attack=20:release=150"
    voice_filter += ",volume=1.8"
    
    # 2. Music processing chain
    music_vol = 0.25 if ducking else 0.15
    fade_out_st = max(0.0, voice_dur - 0.8)
    music_filter = f"[0:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={fade_out_st:.3f}:d=0.8,volume={music_vol}"
    
    # 3. Filter complex composition
    filter_parts = []
    use_whooshes = trans_sfx and bool(getattr(config, "TRANSITION_OFFSETS", []))
    whoosh_input_index = 2
    
    if ducking:
        filter_parts.append(f"{voice_filter}[voice_full]")
        filter_parts.append("[voice_full]asplit=2[sc][voice]")
        filter_parts.append(f"{music_filter}[music_raw]")
        filter_parts.append("[music_raw][sc]sidechaincompress=threshold=0.1:ratio=5:attack=80:release=350[music]")
    else:
        filter_parts.append(f"{voice_filter}[voice]")
        filter_parts.append(f"{music_filter}[music]")
        
    if use_whooshes:
        offsets = config.TRANSITION_OFFSETS
        num_t = len(offsets)
        filter_parts.append(f"[{whoosh_input_index}:a]asplit={num_t}" + "".join(f"[w{j}]" for j in range(num_t)))
        for j, off in enumerate(offsets):
            offset_ms = int(off * 1000)
            filter_parts.append(f"[w{j}]adelay={offset_ms}|{offset_ms},volume=0.45[whoosh{j}]")
        filter_parts.append("".join(f"[whoosh{j}]" for j in range(num_t)) + f"amix=inputs={num_t}:duration=first[whoosh_mix]")
        filter_parts.append("[music][voice][whoosh_mix]amix=inputs=3:duration=first:dropout_transition=2[pre_out]")
    else:
        filter_parts.append("[music][voice]amix=inputs=2:duration=first:dropout_transition=2[pre_out]")
        
    ambient_sound = getattr(config, "AMBIENT_SOUND", None)
    if ambient_sound:
        if ambient_sound == "rain":
            filter_parts.append(f"anoisesrc=a=0.15:c=pink:d={voice_dur:.3f},lowpass=f=1200[amb];[pre_out][amb]amix=inputs=2:duration=first:dropout_transition=2[out]")
        elif ambient_sound == "wind":
            filter_parts.append(f"anoisesrc=a=0.3:c=brown:d={voice_dur:.3f},lowpass=f=500[amb];[pre_out][amb]amix=inputs=2:duration=first:dropout_transition=2[out]")
        elif ambient_sound == "rumble":
            filter_parts.append(f"anoisesrc=a=0.4:c=brown:d={voice_dur:.3f},lowpass=f=80[amb];[pre_out][amb]amix=inputs=2:duration=first:dropout_transition=2[out]")
        else:
            filter_parts.append("[pre_out]acopy[out]")
    else:
        filter_parts.append("[pre_out]acopy[out]")
        
    filter_complex = ";".join(filter_parts)
    
    cmd_audio = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", music_mp3, "-i", voice_mp3
    ]
    if use_whooshes:
        whoosh_wav = generate_whoosh_sound()
        cmd_audio.extend(["-i", whoosh_wav])
        
    cmd_audio.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]", drone_wav
    ])
    subprocess.run(cmd_audio, check=True, stdin=subprocess.DEVNULL)
    
    # Write ASS subtitle file
    ass_filename = "subtitles.ass"
    ass_path = os.path.join(config.TOPIC_TEMP_DIR, ass_filename)
    write_ass_subtitles(ass_path)
    
    # Configure Fontconfig
    setup_fontconfig()
    
    print("Merging audio and video with color grading, fades, ASS subtitles, and custom overlays...")
    output_mp4 = os.path.join(config.TOPIC_TEMP_DIR, "output.mp4")
    
    # Build filter complex for video overlays
    filter_parts = []
    
    # 1. Base video grading & subtitles with upgrades
    camera_shake = getattr(config, "CAMERA_SHAKE", False)
    offsets = getattr(config, "TRANSITION_OFFSETS", [])
    
    color_filter = getattr(config, "COLOR_FILTER", None)
    if color_filter == "horror":
        v_filters = ["eq=contrast=1.3:brightness=-0.1:saturation=0.5,colorbalance=rs=-0.2:bs=0.2"]
    elif color_filter == "cyberpunk":
        v_filters = ["eq=contrast=1.2:saturation=1.5,colorbalance=rs=0.2:bs=0.3"]
    elif color_filter == "vintage":
        v_filters = ["eq=contrast=1.1:saturation=0.7,colorbalance=rs=0.1:bs=-0.1:gs=0.05"]
    elif color_filter == "documentary":
        v_filters = ["eq=contrast=1.2:saturation=0.9"]
    else:
        v_filters = ["eq=contrast=1.15:brightness=-0.15:saturation=1.2"]
    
    if camera_shake and offsets:
        in_trans_parts = [f"between(t,{off-0.12:.3f},{off+0.12:.3f})" for off in offsets]
        in_trans = "+".join(in_trans_parts)
        v_filters.append(f"crop=w=iw-24:h=ih-24:x='12+12*sin(2*PI*t*16)*({in_trans})':y='12+12*cos(2*PI*t*16)*({in_trans})'")
        v_filters.append(f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}")
        
    use_grain = getattr(config, "CINEMATIC_GRAIN", False)
    if use_grain:
        v_filters.append("noise=alls=8:allf=t+u")
        
    v_filters.append(f"fade=t=in:st=0:d=0.3")
    v_filters.append(f"fade=t=out:st={voice_dur-0.5:.3f}:d=0.5")
    
    wm_text = getattr(config, "WATERMARK_TEXT", "")
    if wm_text:
        safe_text = wm_text.replace("'", "'\\\\''")
        safe_text = safe_text.replace(":", "\\\\:")
        safe_text = safe_text.replace(";", "\\\\;")
        font_clean = config.FONT_PATH.replace("\\", "/").replace(":", "\\:")
        font_arg = f":fontfile='{font_clean}'" if os.path.exists(config.FONT_PATH) else ""
        v_filters.append(f"drawtext=text='{safe_text}':fontsize=22:fontcolor=white@0.6{font_arg}:x=(w-tw)/2:y=h-70")
        
    ass_path_clean = os.path.join(config.TOPIC_TEMP_DIR, "subtitles.ass").replace("\\", "/").replace(":", "\\:")
    font_dir_clean = os.path.dirname(os.path.abspath(config.FONT_PATH)).replace("\\", "/").replace(":", "\\:")
    v_filters.append(f"subtitles='{ass_path_clean}':fontsdir='{font_dir_clean}'")
    
    base_v_filter = ",".join(v_filters)
    filter_parts.append(f"[0:v]{base_v_filter}[v_graded]")
    last_v_label = "[v_graded]"
    
    # 2. Progress Bar Overlay
    show_bar = getattr(config, "SHOW_PROGRESS_BAR", True)
    bar_color = getattr(config, "PROGRESS_BAR_COLOR", "gold").lower()
    bar_height = getattr(config, "PROGRESS_BAR_HEIGHT", 8)
    if show_bar:
        safe_voice_dur = max(0.1, voice_dur)
        filter_parts.append(f"color=c={bar_color}:s={config.VIDEO_WIDTH}x{bar_height}:d={voice_dur:.3f}[bar]")
        filter_parts.append(f"{last_v_label}[bar]overlay=-w+(w/{safe_voice_dur:.3f})*t:main_h-overlay_h[v_bar]")
        last_v_label = "[v_bar]"
        
    # 3. Watermark Logo Overlay
    show_logo = getattr(config, "SHOW_WATERMARK", False)
    logo_path = os.path.join(config.OUTPUT_DIR, "watermark.png")
    has_logo = show_logo and os.path.exists(logo_path)
    
    if has_logo:
        logo_size = getattr(config, "WATERMARK_SIZE", 100)
        logo_opacity = getattr(config, "WATERMARK_OPACITY", 0.5)
        logo_pos = getattr(config, "WATERMARK_POSITION", "main_w-overlay_w-20:20")
        
        # Scale logo and apply opacity
        filter_parts.append(f"[2:v]scale={logo_size}:-1,format=yuva420p,colorchannelmixer=aa={logo_opacity:.2f}[logo]")
        filter_parts.append(f"{last_v_label}[logo]overlay={logo_pos}[v_final]")
        last_v_label = "[v_final]"
        
    filter_complex = ";".join(filter_parts)
    
    cmd_merge = ["ffmpeg", "-y", "-i", "silent_temp.mp4", "-i", "drone.wav"]
    if has_logo:
        cmd_merge.extend(["-i", logo_path])
        
    cmd_merge.extend([
        "-filter_complex", filter_complex,
        "-map", last_v_label,
        "-map", "1:a",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "output.mp4"
    ])
    subprocess.run(cmd_merge, check=True, cwd=config.TOPIC_TEMP_DIR, stdin=subprocess.DEVNULL)

