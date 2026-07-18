import os
from history_reels.jobs import GenerationJob
from history_reels.subtitles import write_ass_subtitles
from history_reels.ffmpeg_runner import (
    AUDIO_TIMEOUT_SECONDS,
    CLIP_TIMEOUT_SECONDS,
    MERGE_TIMEOUT_SECONDS,
    get_media_dimensions,
    run_command,
    write_fontconfig_file,
)


def get_video_dimensions(path):
    return get_media_dimensions(path)


def _job_id(job: GenerationJob) -> str | None:
    return str(getattr(job, "job_id", "") or "") or None


def build_video_frames(job: GenerationJob, voice_dur):
    print("Extracting clips from source videos...")
    
    target_clip_dur = getattr(job, "CLIP_DURATION_TARGET", 5.0)
    divisor = max(0.1, target_clip_dur - job.CROSSFADE_DUR)
    estimated_clips = max(1, int(round((voice_dur - job.CROSSFADE_DUR) / divisor)))
    
    repeats = 2 if target_clip_dur < 4.0 else 1
    available_media = len(job.QUERIES)
    if available_media < 1:
        raise RuntimeError("No usable media assets are available for frame generation.")
    max_available = max(4, available_media * repeats)
    num_clips = min(max(4, estimated_clips), max_available)
    
    job.NUM_CLIPS = num_clips
    
    total_visual_dur = voice_dur + (job.NUM_CLIPS - 1) * job.CROSSFADE_DUR
    clip_dur = total_visual_dur / job.NUM_CLIPS
    print(f"Dynamic clip duration: {clip_dur:.2f}s (Target: {target_clip_dur:.2f}s, Cuts: {job.NUM_CLIPS}) (Total video duration: {voice_dur:.2f}s)")
    
    clips = []
    for i in range(1, job.NUM_CLIPS + 1):
        source_index = ((i - 1) % available_media) + 1
        raw_path_mp4 = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{source_index}.mp4")
        raw_path_jpg = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{source_index}.jpg")
        raw_path_png = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{source_index}.png")
        
        clip_path = os.path.join(job.TOPIC_TEMP_DIR, f"clip{i}.mp4")
        clips.append(clip_path)
        
        if os.path.exists(raw_path_mp4):
            # Process Video Clip
            w, h = get_video_dimensions(raw_path_mp4)
            if w <= 0 or h <= 0:
                raise RuntimeError(
                    f"Downloaded media clip {source_index} has invalid dimensions ({w}x{h}); "
                    "a blank placeholder will not be used. Retry to download fresh media."
                )
            target_aspect = job.VIDEO_WIDTH / job.VIDEO_HEIGHT
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
                
            vf = f"crop={crop_w}:{crop_h}:{offset_x}:{offset_y},scale={job.VIDEO_WIDTH}:{job.VIDEO_HEIGHT}"
            cmd = [
                "ffmpeg", "-y", "-ss", "0.0", "-stream_loop", "-1", "-i", raw_path_mp4, "-t", f"{clip_dur:.3f}",
                "-vf", vf, "-an", "-r", str(job.FPS), "-pix_fmt", "yuv420p", clip_path
            ]
            run_command(cmd, timeout=CLIP_TIMEOUT_SECONDS, job_id=_job_id(job), label="clip extract")
            
        else:
            # Process Image Clip (Convert to video using Ken Burns zoom effect)
            img_path = raw_path_jpg if os.path.exists(raw_path_jpg) else raw_path_png
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"Error: No video or image clip found for index {i}")
                
            scale_w = int(job.VIDEO_WIDTH * 2)
            scale_h = int(job.VIDEO_HEIGHT * 2)
            vf_zoom = f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=decrease,pad={scale_w}:{scale_h}:(ow-iw)/2:(oh-ih)/2,zoompan=z='zoom+0.0005':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(job.FPS * clip_dur)}:s={job.VIDEO_WIDTH}x{job.VIDEO_HEIGHT},fps={job.FPS}"
            cmd = [
                "ffmpeg", "-y", "-i", img_path, "-t", f"{clip_dur:.3f}",
                "-vf", vf_zoom, "-an", "-r", str(job.FPS), "-pix_fmt", "yuv420p", clip_path
            ]
            run_command(cmd, timeout=CLIP_TIMEOUT_SECONDS, job_id=_job_id(job), label="image ken-burns")
        
    print("Crossfading clips...")
    silent_temp = os.path.join(job.TOPIC_TEMP_DIR, "silent_temp.mp4")
    
    if job.NUM_CLIPS <= 1:
        import shutil
        if clips:
            shutil.copy2(clips[0], silent_temp)
        return
        
    filter_parts = []
    last_label = "0:v"
    curr_offset = max(0, clip_dur - job.CROSSFADE_DUR)
    job.TRANSITION_OFFSETS = []
    
    transition_style = str(getattr(job, "VIDEO_TRANSITION", "fade")).lower()
    allowed_transitions = ["fade", "slideleft", "slideright", "slideup", "slidedown", "wipeleft", "wiperight", "zoomin", "dissolve", "pixelize", "radial"]
    
    for i in range(1, job.NUM_CLIPS):
        job.TRANSITION_OFFSETS.append(curr_offset)
        out_label = f"v{i}"
        t_style = transition_style
        if t_style == "random":
            import random
            t_style = random.choice(allowed_transitions)
        elif t_style not in allowed_transitions:
            t_style = "fade"
            
        filter_parts.append(f"[{last_label}][{i}:v]xfade=transition={t_style}:duration={job.CROSSFADE_DUR}:offset={curr_offset:.3f}[{out_label}]")
        last_label = out_label
        curr_offset += max(0.1, clip_dur - job.CROSSFADE_DUR)
        
    filter_complex = ";".join(filter_parts)
    
    cmd_fade = ["ffmpeg", "-y"]
    for c in clips:
        cmd_fade.extend(["-i", c])
    cmd_fade.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]", "-r", str(job.FPS), silent_temp
    ])
    run_command(cmd_fade, timeout=MERGE_TIMEOUT_SECONDS, job_id=_job_id(job), label="clip crossfade")

def setup_fontconfig(job: GenerationJob):
    """Write a job-local fonts.conf and return its path (no global FONTCONFIG_FILE mutation)."""
    return write_fontconfig_file(job)

def generate_whoosh_sound(job: GenerationJob):
    whoosh_path = os.path.join(job.TOPIC_TEMP_DIR, "whoosh.wav")
    if os.path.exists(whoosh_path):
        return whoosh_path
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "aevalsrc=sin(2*PI*(180+500*sin(PI*t/0.5))*t):d=0.5",
        "-af", "volume='sin(PI*t/0.5)':eval=frame",
        whoosh_path
    ]
    run_command(cmd, timeout=30, job_id=_job_id(job), label="whoosh sfx")
    return whoosh_path

def run_ffmpeg(job: GenerationJob, voice_dur):
    print("Mixing background music and voiceover...")
    drone_wav = os.path.join(job.TOPIC_TEMP_DIR, "drone.wav")
    music_mp3 = os.path.join(job.MUSIC_DIR, f"{job.BG_MUSIC_VIBE}_{job.BG_MUSIC_TRACK_INDEX}.mp3")
    voice_mp3 = os.path.join(job.TOPIC_TEMP_DIR, "voice.mp3")
    
    # Mix audio with dynamic filters
    ducking = getattr(job, "AUDIO_DUCKING", True)
    mastering = getattr(job, "VOICE_MASTERING", True)
    trans_sfx = getattr(job, "TRANSITION_SFX", False)
    
    # 1. Voice processing chain
    voice_filter = f"[1:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS"
    if mastering:
        voice_filter += ",equalizer=f=100:width_type=h:width=100:g=4,equalizer=f=3500:width_type=h:width=2000:g=2,acompressor=threshold=0.08:ratio=3:attack=20:release=150"
    voice_filter += ",volume=1.8"
    
    # 2. Filter complex composition.
    filter_parts = []
    use_whooshes = trans_sfx and bool(getattr(job, "TRANSITION_OFFSETS", []))
    whoosh_input_index = 2
    
    music_vol = 0.25 if ducking else 0.15
    fade_out_st = max(0.0, voice_dur - 0.8)
    music_filter = f"[0:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={fade_out_st:.3f}:d=0.8,volume={music_vol}"
    if ducking:
        filter_parts.append(f"{voice_filter}[voice_full]")
        filter_parts.append("[voice_full]asplit=2[sc][voice]")
        filter_parts.append(f"{music_filter}[music_raw]")
        filter_parts.append("[music_raw][sc]sidechaincompress=threshold=0.1:ratio=5:attack=80:release=350[music]")
    else:
        filter_parts.append(f"{voice_filter}[voice]")
        filter_parts.append(f"{music_filter}[music]")
        
    if use_whooshes:
        offsets = job.TRANSITION_OFFSETS
        num_t = len(offsets)
        if num_t == 1:
            filter_parts.append(f"[{whoosh_input_index}:a]anull[w0]")
        else:
            filter_parts.append(f"[{whoosh_input_index}:a]asplit={num_t}" + "".join(f"[w{j}]" for j in range(num_t)))
        for j, off in enumerate(offsets):
            offset_ms = int(off * 1000)
            filter_parts.append(f"[w{j}]adelay={offset_ms}|{offset_ms},volume=0.45[whoosh{j}]")
        if num_t == 1:
            filter_parts.append("[whoosh0]acopy[whoosh_mix]")
        else:
            filter_parts.append("".join(f"[whoosh{j}]" for j in range(num_t)) + f"amix=inputs={num_t}:duration=longest[whoosh_mix]")
        filter_parts.append("[music][voice][whoosh_mix]amix=inputs=3:duration=longest:dropout_transition=2[pre_out]")
    else:
        filter_parts.append("[music][voice]amix=inputs=2:duration=longest:dropout_transition=2[pre_out]")
        
    ambient_sound = getattr(job, "AMBIENT_SOUND", None)
    if ambient_sound:
        if ambient_sound == "rain":
            filter_parts.append(f"anoisesrc=a=0.15:c=pink:d={voice_dur:.3f},lowpass=f=1200[amb];[pre_out][amb]amix=inputs=2:duration=longest:dropout_transition=2[out]")
        elif ambient_sound == "wind":
            filter_parts.append(f"anoisesrc=a=0.3:c=brown:d={voice_dur:.3f},lowpass=f=500[amb];[pre_out][amb]amix=inputs=2:duration=longest:dropout_transition=2[out]")
        elif ambient_sound == "rumble":
            filter_parts.append(f"anoisesrc=a=0.4:c=brown:d={voice_dur:.3f},lowpass=f=80[amb];[pre_out][amb]amix=inputs=2:duration=longest:dropout_transition=2[out]")
        else:
            filter_parts.append("[pre_out]acopy[out]")
    else:
        filter_parts.append("[pre_out]acopy[out]")

    # Keep every export at a consistent listening level after voice, music,
    # ambient audio, and transition effects have been mixed together.
    audio_output_label = "[out]"
    if getattr(job, "AUDIO_NORMALIZATION", True):
        target_lufs = float(getattr(job, "AUDIO_TARGET_LUFS", -16.0))
        true_peak = float(getattr(job, "AUDIO_TRUE_PEAK_DB", -1.5))
        loudness_range = float(getattr(job, "AUDIO_LOUDNESS_RANGE", 11.0))
        filter_parts.append(
            f"[out]loudnorm=I={target_lufs:.1f}:TP={true_peak:.1f}:LRA={loudness_range:.1f}[normalized]"
        )
        audio_output_label = "[normalized]"
        
    filter_complex = ";".join(filter_parts)
    
    cmd_audio = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", music_mp3, "-i", voice_mp3]
    if use_whooshes:
        whoosh_wav = generate_whoosh_sound(job)
        cmd_audio.extend(["-i", whoosh_wav])
        
    cmd_audio.extend([
        "-filter_complex", filter_complex,
        "-map", audio_output_label, drone_wav
    ])
    run_command(cmd_audio, timeout=AUDIO_TIMEOUT_SECONDS, job_id=_job_id(job), label="audio mix")
    
    # Write ASS captions using the selected sidebar font configuration.
    ass_path = os.path.join(job.TOPIC_TEMP_DIR, "subtitles.ass")
    write_ass_subtitles(ass_path, job)
    fonts_conf_path = setup_fontconfig(job)
    
    print("Merging audio and video with color grading, fades, ASS subtitles, and custom overlays...")
    output_mp4 = os.path.join(job.TOPIC_TEMP_DIR, "output.mp4")
    
    # Build filter complex for video overlays
    filter_parts = []
    
    # 1. Base video grading & subtitles with upgrades
    camera_shake = getattr(job, "CAMERA_SHAKE", False)
    offsets = getattr(job, "TRANSITION_OFFSETS", [])
    
    color_filter = getattr(job, "COLOR_FILTER", None)
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
        v_filters.append(f"scale={job.VIDEO_WIDTH}:{job.VIDEO_HEIGHT}")
        
    use_grain = getattr(job, "CINEMATIC_GRAIN", False)
    if use_grain:
        v_filters.append("noise=alls=8:allf=t+u")
        
    v_filters.append(f"fade=t=in:st=0:d=0.3")
    v_filters.append(f"fade=t=out:st={voice_dur-0.5:.3f}:d=0.5")
    
    wm_text = getattr(job, "WATERMARK_TEXT", "")
    if wm_text:
        safe_text = wm_text.replace("'", "'\\''")
        safe_text = safe_text.replace(";", "\\;")
        font_clean = job.FONT_PATH.replace("\\", "/")
        font_arg = f":fontfile='{font_clean}'" if os.path.exists(job.FONT_PATH) else ""
        v_filters.append(f"drawtext=text='{safe_text}':fontsize=22:fontcolor=white@0.6{font_arg}:x=(w-tw)/2:y=h-70")
        
    ass_path_clean = ass_path.replace("\\", "/")
    font_dir_clean = os.path.dirname(os.path.abspath(job.FONT_PATH)).replace("\\", "/")
    v_filters.append(f"subtitles='{ass_path_clean}':fontsdir='{font_dir_clean}'")
    
    v_filter_str = ",".join(v_filters)
    filter_parts.append(f"[0:v]{v_filter_str}[v_base]")
    last_v_label = "[v_base]"
    # 2. Progress Bar Overlay
    show_bar = getattr(job, "SHOW_PROGRESS_BAR", True)
    bar_color = getattr(job, "PROGRESS_BAR_COLOR", "gold").lower()
    bar_height = getattr(job, "PROGRESS_BAR_HEIGHT", 8)
    if show_bar:
        safe_voice_dur = max(0.1, voice_dur)
        filter_parts.append(f"color=c={bar_color}:s={job.VIDEO_WIDTH}x{bar_height}:d={voice_dur:.3f}[bar]")
        filter_parts.append(f"{last_v_label}[bar]overlay=-w+(w/{safe_voice_dur:.3f})*t:main_h-overlay_h[v_bar]")
        last_v_label = "[v_bar]"
        
    # 3. Watermark Logo Overlay
    show_logo = getattr(job, "SHOW_WATERMARK", False)
    configured_logo = str(getattr(job, "WATERMARK_PATH", "") or "").strip()
    logo_path = configured_logo or os.path.join(job.OUTPUT_DIR, "watermark.png")
    has_logo = show_logo and bool(logo_path) and os.path.exists(logo_path)
    
    if has_logo:
        logo_size = getattr(job, "WATERMARK_SIZE", 100)
        logo_opacity = getattr(job, "WATERMARK_OPACITY", 0.5)
        logo_pos = getattr(job, "WATERMARK_POSITION", "main_w-overlay_w-20:20")
        
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
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "output.mp4"
    ])
    # Pass FONTCONFIG_FILE only into this subprocess — never mutate global os.environ.
    run_command(
        cmd_merge,
        timeout=MERGE_TIMEOUT_SECONDS,
        cwd=job.TOPIC_TEMP_DIR,
        env={"FONTCONFIG_FILE": fonts_conf_path},
        job_id=_job_id(job),
        label="final merge",
    )
