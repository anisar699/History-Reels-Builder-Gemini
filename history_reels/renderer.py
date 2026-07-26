import os
from history_reels.jobs import GenerationJob
from history_reels.subtitles import (
    render_caption_overlays,
    uses_rasterized_captions,
    write_ass_subtitles,
)
from history_reels.ffmpeg_runner import (
    AUDIO_TIMEOUT_SECONDS,
    CLIP_TIMEOUT_SECONDS,
    MERGE_TIMEOUT_SECONDS,
    get_media_dimensions,
    run_command,
    write_fontconfig_file,
)
from history_reels.visual_quality import find_raw_media_path


def get_video_dimensions(path):
    return get_media_dimensions(path)


def _job_id(job: GenerationJob) -> str | None:
    return str(getattr(job, "job_id", "") or "") or None


def crop_window(
    width: int,
    height: int,
    target_ratio: float,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> tuple[int, int, int, int]:
    """Return an even crop centred as closely as possible on visual saliency."""
    width, height = max(2, int(width)), max(2, int(height))
    target_ratio = max(0.01, float(target_ratio))
    if width / height > target_ratio:
        crop_height = height - (height % 2)
        crop_width = min(width, int(crop_height * target_ratio))
    else:
        crop_width = width - (width % 2)
        crop_height = min(height, int(crop_width / target_ratio))
    crop_width = max(2, crop_width - (crop_width % 2))
    crop_height = max(2, crop_height - (crop_height % 2))
    centre_x = min(1.0, max(0.0, float(focus_x))) * width
    centre_y = min(1.0, max(0.0, float(focus_y))) * height
    offset_x = int(round(centre_x - crop_width / 2))
    offset_y = int(round(centre_y - crop_height / 2))
    offset_x = min(max(0, offset_x), width - crop_width)
    offset_y = min(max(0, offset_y), height - crop_height)
    offset_x -= offset_x % 2
    offset_y -= offset_y % 2
    return crop_width, crop_height, offset_x, offset_y


def _slide_durations(job: GenerationJob, voice_dur: float) -> list[float]:
    timings = list(getattr(job, "SLIDE_TIMINGS", []) or [])
    if not timings:
        return []
    durations = []
    previous = 0.0
    for raw_end in timings:
        try:
            end = min(float(voice_dur), max(previous, float(raw_end)))
        except (TypeError, ValueError):
            return []
        durations.append(max(0.1, end - previous))
        previous = end
    if durations and previous < voice_dur:
        durations[-1] += voice_dur - previous
    return durations


def _visual_focus(job: GenerationJob, source_index: int) -> tuple[float, float]:
    reports = getattr(job, "MEDIA_QA_BY_INDEX", {}) or {}
    report = reports.get(source_index) or reports.get(str(source_index)) or {}
    return float(report.get("focus_x", 0.5)), float(report.get("focus_y", 0.5))


def build_video_frames(job: GenerationJob, voice_dur):
    print("Extracting clips from source videos...")
    
    target_clip_dur = getattr(job, "CLIP_DURATION_TARGET", 5.0)
    available_media = len(job.QUERIES)
    if available_media < 1:
        raise RuntimeError("No usable media assets are available for frame generation.")

    narration_durations = _slide_durations(job, voice_dur)
    if narration_durations and len(narration_durations) <= available_media:
        job.NUM_CLIPS = len(narration_durations)
        clip_durations = [
            duration + (job.CROSSFADE_DUR if index < len(narration_durations) - 1 else 0.0)
            for index, duration in enumerate(narration_durations)
        ]
        timing_mode = "narration slides"
    else:
        divisor = max(0.1, target_clip_dur - job.CROSSFADE_DUR)
        estimated_clips = max(1, int(round((voice_dur - job.CROSSFADE_DUR) / divisor)))
        repeats = 2 if target_clip_dur < 4.0 else 1
        max_available = max(4, available_media * repeats)
        job.NUM_CLIPS = min(max(4, estimated_clips), max_available)
        total_visual_dur = voice_dur + (job.NUM_CLIPS - 1) * job.CROSSFADE_DUR
        clip_durations = [total_visual_dur / job.NUM_CLIPS] * job.NUM_CLIPS
        timing_mode = "pacing fallback"
    job.CLIP_DURATIONS = clip_durations
    print(
        f"Visual timing: {timing_mode}, {job.NUM_CLIPS} cuts "
        f"(durations: {', '.join(f'{value:.2f}s' for value in clip_durations)})"
    )
    
    clips = []
    for i in range(1, job.NUM_CLIPS + 1):
        source_index = ((i - 1) % available_media) + 1
        raw_media_path = find_raw_media_path(job.TOPIC_TEMP_DIR, source_index)
        clip_dur = clip_durations[i - 1]
        focus_x, focus_y = _visual_focus(job, source_index)
        
        clip_path = os.path.join(job.TOPIC_TEMP_DIR, f"clip{i}.mp4")
        clips.append(clip_path)
        
        if raw_media_path and os.path.splitext(raw_media_path)[1].lower() == ".mp4":
            # Process Video Clip
            w, h = get_video_dimensions(raw_media_path)
            if w <= 0 or h <= 0:
                raise RuntimeError(
                    f"Downloaded media clip {source_index} has invalid dimensions ({w}x{h}); "
                    "a blank placeholder will not be used. Retry to download fresh media."
                )
            target_aspect = job.VIDEO_WIDTH / job.VIDEO_HEIGHT
            crop_w, crop_h, offset_x, offset_y = crop_window(
                w, h, target_aspect, focus_x, focus_y
            )
                
            vf = f"crop={crop_w}:{crop_h}:{offset_x}:{offset_y},scale={job.VIDEO_WIDTH}:{job.VIDEO_HEIGHT}"
            cmd = [
                "ffmpeg", "-y", "-threads", "0", "-ss", "0.0", "-stream_loop", "-1", "-i", raw_media_path, "-t", f"{clip_dur:.3f}",
                "-vf", vf, "-an", "-r", str(job.FPS), "-pix_fmt", "yuv420p", clip_path
            ]
            run_command(cmd, timeout=CLIP_TIMEOUT_SECONDS, job_id=_job_id(job), label="clip extract")
            
        else:
            # Process Image Clip (Convert to video using Dynamic Ken Burns Motion)
            img_path = raw_media_path
            if not img_path or not os.path.exists(img_path):
                raise FileNotFoundError(f"Error: No video or image clip found for index {i}")

            image_w, image_h = get_video_dimensions(img_path)
            if image_w <= 0 or image_h <= 0:
                # Download-time QA normally supplies real dimensions. Retain a
                # safe centred filter for legacy/prevalidated workspaces where
                # metadata probing is unavailable.
                image_w, image_h = job.VIDEO_WIDTH, job.VIDEO_HEIGHT
            crop_w, crop_h, offset_x, offset_y = crop_window(
                image_w,
                image_h,
                job.VIDEO_WIDTH / job.VIDEO_HEIGHT,
                focus_x,
                focus_y,
            )
            scale_w = int(job.VIDEO_WIDTH * 1.35)
            scale_h = int(job.VIDEO_HEIGHT * 1.35)
            frames_count = max(1, int(job.FPS * clip_dur))
            motion_type = (i - 1) % 4
            if motion_type == 0:
                z_expr = "min(zoom+0.0012,1.3)"
                x_expr = "iw/2-(iw/zoom/2)"
                y_expr = "ih/2-(ih/zoom/2)"
            elif motion_type == 1:
                z_expr = "1.2"
                x_expr = "if(lte(on,1),(iw-iw/zoom),(x-1.2))"
                y_expr = "ih/2-(ih/zoom/2)"
            elif motion_type == 2:
                z_expr = "max(1.3-0.0012*on,1.0)"
                x_expr = "iw/2-(iw/zoom/2)"
                y_expr = "ih/2-(ih/zoom/2)"
            else:
                z_expr = "1.2"
                x_expr = "iw/2-(iw/zoom/2)"
                y_expr = "if(lte(on,1),(ih-ih/zoom),(y-1.2))"

            vf_zoom = (
                f"crop={crop_w}:{crop_h}:{offset_x}:{offset_y},"
                f"scale={scale_w}:{scale_h},"
                f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames_count}:s={job.VIDEO_WIDTH}x{job.VIDEO_HEIGHT},"
                f"fps={job.FPS}"
            )
            cmd = [
                "ffmpeg", "-y", "-threads", "0", "-i", img_path, "-t", f"{clip_dur:.3f}",
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
    curr_offset = max(0, clip_durations[0] - job.CROSSFADE_DUR)
    
    for i in range(1, job.NUM_CLIPS):
        out_label = f"v{i}"
        filter_parts.append(f"[{last_label}][{i}:v]xfade=transition=fade:duration={job.CROSSFADE_DUR}:offset={curr_offset:.3f}[{out_label}]")
        last_label = out_label
        curr_offset += max(0.1, clip_durations[i] - job.CROSSFADE_DUR)
        
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

def run_ffmpeg(job: GenerationJob, voice_dur):
    print("Mixing background music and voiceover...")
    drone_wav = os.path.join(job.TOPIC_TEMP_DIR, "drone.wav")
    music_mp3 = str(
        getattr(job, "MUSIC_PATH", "")
        or os.path.join(job.MUSIC_DIR, f"{job.BG_MUSIC_VIBE}_{job.BG_MUSIC_TRACK_INDEX}.mp3")
    )
    voice_mp3 = os.path.join(job.TOPIC_TEMP_DIR, "voice.mp3")
    
    # Voice mastering and music ducking are fixed quality safeguards.
    voice_filter = (
        f"[1:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,"
        "equalizer=f=100:width_type=h:width=100:g=4,"
        "equalizer=f=3500:width_type=h:width=2000:g=2,"
        "acompressor=threshold=0.08:ratio=3:attack=20:release=150,"
        "volume=1.8"
    )
    
    # 2. Filter complex composition.
    filter_parts = []
    
    music_vol = 0.25
    fade_out_st = max(0.0, voice_dur - 0.8)
    music_filter = f"[0:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={fade_out_st:.3f}:d=0.8,volume={music_vol}"
    filter_parts.append(f"{voice_filter}[voice_full]")
    filter_parts.append("[voice_full]asplit=2[sc][voice]")
    filter_parts.append(f"{music_filter}[music_raw]")
    filter_parts.append("[music_raw][sc]sidechaincompress=threshold=0.1:ratio=5:attack=80:release=350[music]")
        
    filter_parts.append("[music][voice]amix=inputs=2:duration=longest:dropout_transition=2[out]")

    # Keep every export at a consistent listening level after voice and music
    # have been mixed together.
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
    cmd_audio.extend([
        "-filter_complex", filter_complex,
        "-map", audio_output_label, drone_wav
    ])
    run_command(cmd_audio, timeout=AUDIO_TIMEOUT_SECONDS, job_id=_job_id(job), label="audio mix")
    
    # libass can silently drop Nastaliq glyphs on Windows even when the font is
    # found. Pillow/RAQM produces shaped transparent overlays for RTL scripts.
    raster_captions = uses_rasterized_captions(job)
    caption_overlays = []
    ass_path = None
    fonts_conf_path = None
    if raster_captions:
        caption_overlays = render_caption_overlays(job)
    else:
        ass_path = os.path.join(job.TOPIC_TEMP_DIR, "subtitles.ass")
        write_ass_subtitles(ass_path, job)
        fonts_conf_path = setup_fontconfig(job)
    
    caption_mode = "RAQM caption overlays" if raster_captions else "ASS subtitles"
    print(f"Merging audio and video with color grading, fades, {caption_mode}, and custom overlays...")
    output_mp4 = os.path.join(job.TOPIC_TEMP_DIR, "output.mp4")
    
    # Build filter complex for video overlays
    filter_parts = []
    
    # 1. Base video grading & subtitles with upgrades
    color_filter = getattr(job, "COLOR_FILTER", None)
    if color_filter == "documentary":
        v_filters = ["eq=contrast=1.10:brightness=-0.02:saturation=0.92"]
    else:
        # Preserve source exposure. The previous -0.15 brightness crushed
        # already-dark stock footage after the crop.
        v_filters = ["eq=contrast=1.07:brightness=-0.04:saturation=1.08"]
        
    v_filters.append(f"fade=t=in:st=0:d=0.3")
    v_filters.append(f"fade=t=out:st={voice_dur-0.5:.3f}:d=0.5")
        
    if ass_path:
        ass_path_clean = ass_path.replace("\\", "/").replace(":", "\\:")
        font_dir_clean = os.path.dirname(os.path.abspath(job.FONT_PATH)).replace("\\", "/").replace(":", "\\:")
        v_filters.append(f"subtitles=f='{ass_path_clean}':fontsdir='{font_dir_clean}'")
    
    v_filter_str = ",".join(v_filters)
    filter_parts.append(f"[0:v]{v_filter_str}[v_base]")
    last_v_label = "[v_base]"

    # 2. Timed, pre-shaped Urdu/Arabic caption overlays.
    for overlay_number, overlay in enumerate(caption_overlays):
        input_index = 2 + overlay_number
        output_label = f"[v_caption_{overlay_number}]"
        filter_parts.append(
            f"{last_v_label}[{input_index}:v]overlay=0:{int(overlay['y'])}:"
            f"enable='between(t,{overlay['start']:.3f},{overlay['end']:.3f})':"
            f"eof_action=repeat:shortest=0{output_label}"
        )
        last_v_label = output_label

    # 3. Progress Bar Overlay
    show_bar = getattr(job, "SHOW_PROGRESS_BAR", True)
    if show_bar:
        bar_color = "gold"
        bar_height = 8
        safe_voice_dur = max(0.1, voice_dur)
        filter_parts.append(f"color=c={bar_color}:s={job.VIDEO_WIDTH}x{bar_height}:d={voice_dur:.3f}[bar]")
        filter_parts.append(f"{last_v_label}[bar]overlay=-w+(w/{safe_voice_dur:.3f})*t:main_h-overlay_h[v_bar]")
        last_v_label = "[v_bar]"
        
    # 4. Watermark Logo Overlay
    show_logo = getattr(job, "SHOW_WATERMARK", False)
    configured_logo = str(getattr(job, "WATERMARK_PATH", "") or "").strip()
    logo_path = configured_logo or os.path.join(job.OUTPUT_DIR, "watermark.png")
    has_logo = show_logo and bool(logo_path) and os.path.exists(logo_path)
    
    if has_logo:
        logo_size = getattr(job, "WATERMARK_SIZE", 100)
        logo_opacity = getattr(job, "WATERMARK_OPACITY", 0.5)
        logo_pos = getattr(job, "WATERMARK_POSITION", "main_w-overlay_w-20:20")
        
        # Scale logo and apply opacity
        logo_input_index = 2 + len(caption_overlays)
        filter_parts.append(f"[{logo_input_index}:v]scale={logo_size}:-1,format=yuva420p,colorchannelmixer=aa={logo_opacity:.2f}[logo]")
        filter_parts.append(f"{last_v_label}[logo]overlay={logo_pos}[v_final]")
        last_v_label = "[v_final]"
        
    filter_complex = ";".join(filter_parts)
    
    cmd_merge = ["ffmpeg", "-y", "-threads", "0", "-i", "silent_temp.mp4", "-i", "drone.wav"]
    for overlay in caption_overlays:
        cmd_merge.extend(["-loop", "1", "-framerate", str(job.FPS), "-i", overlay["path"]])
    if has_logo:
        cmd_merge.extend(["-i", logo_path])
        
    cmd_merge.extend([
        "-filter_complex", filter_complex,
        "-map", last_v_label,
        "-map", "1:a",
        "-shortest",
        # Infinite-loop caption image inputs can make FFmpeg's framesync emit
        # extra video frames after the 12/30/60s narration has ended. Enforce
        # the narration duration explicitly so audio, captions, and video end
        # on the same timeline.
        "-t", f"{voice_dur:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "output.mp4"
    ])
    # Pass FONTCONFIG_FILE only for ASS renders — never mutate global os.environ.
    merge_env = {"FONTCONFIG_FILE": fonts_conf_path} if fonts_conf_path else None
    run_command(
        cmd_merge,
        timeout=MERGE_TIMEOUT_SECONDS,
        cwd=job.TOPIC_TEMP_DIR,
        env=merge_env,
        job_id=_job_id(job),
        label="final merge",
    )
