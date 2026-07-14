import os
import subprocess
from history_reels import config
from history_reels.subtitles import write_ass_subtitles

def get_video_dimensions(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    parts = res.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])

def build_video_frames(voice_dur):
    print("Extracting clips from source videos...")
    
    total_visual_dur = voice_dur + (config.NUM_CLIPS - 1) * config.CROSSFADE_DUR
    clip_dur = total_visual_dur / config.NUM_CLIPS
    print(f"Dynamic clip duration: {clip_dur:.2f}s (Total video duration: {voice_dur:.2f}s)")
    
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
            if (w / h) > (9 / 16):
                crop_h = h
                crop_w = int(h * 9 / 16)
                if crop_w % 2 != 0:
                    crop_w += 1
                offset_x = (w - crop_w) // 2
                offset_y = 0
            else:
                crop_w = w
                crop_h = int(w * 16 / 9)
                if crop_h % 2 != 0:
                    crop_h += 1
                offset_x = 0
                offset_y = (h - crop_h) // 2
                
            vf = f"crop={crop_w}:{crop_h}:{offset_x}:{offset_y},scale=720:1280"
            cmd = [
                "ffmpeg", "-y", "-ss", "0.0", "-i", raw_path_mp4, "-t", f"{clip_dur:.3f}",
                "-vf", vf, "-an", "-r", str(config.FPS), clip_path
            ]
            subprocess.run(cmd, check=True)
            
        else:
            # Process Image Clip (Convert to video using Ken Burns zoom effect)
            img_path = raw_path_jpg if os.path.exists(raw_path_jpg) else raw_path_png
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"Error: No video or image clip found for index {i}")
                
            # Scale up to 1440:2560 before zoompan to ensure crisp resolution during slow zoom
            dur_frames = int(clip_dur * config.FPS)
            vf_zoom = f"scale=1440:2560,zoompan=z='zoom+0.0005':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={dur_frames}:s=720x1280"
            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", img_path, "-t", f"{clip_dur:.3f}",
                "-vf", vf_zoom, "-an", "-r", str(config.FPS), clip_path
            ]
            subprocess.run(cmd, check=True)
        
    print("Crossfading clips...")
    silent_temp = os.path.join(config.TOPIC_TEMP_DIR, "silent_temp.mp4")
    
    filter_parts = []
    last_label = "0:v"
    curr_offset = clip_dur - config.CROSSFADE_DUR
    
    for i in range(1, config.NUM_CLIPS):
        out_label = f"v{i}"
        filter_parts.append(f"[{last_label}][{i}:v]xfade=transition=fade:duration={config.CROSSFADE_DUR}:offset={curr_offset:.3f}[{out_label}]")
        last_label = out_label
        curr_offset += clip_dur - config.CROSSFADE_DUR
        
    filter_complex = ";".join(filter_parts)
    
    cmd_fade = ["ffmpeg", "-y"]
    for c in clips:
        cmd_fade.extend(["-i", c])
    cmd_fade.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]", "-r", str(config.FPS), silent_temp
    ])
    subprocess.run(cmd_fade, check=True)

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

def run_ffmpeg(voice_dur):
    print("Mixing background music and voiceover...")
    drone_wav = os.path.join(config.TOPIC_TEMP_DIR, "drone.wav")
    music_mp3 = os.path.join(config.MUSIC_DIR, f"{config.BG_MUSIC_VIBE}_{config.BG_MUSIC_TRACK_INDEX}.mp3")
    voice_mp3 = os.path.join(config.TOPIC_TEMP_DIR, "voice.mp3")
    
    # Mix audio
    cmd_audio = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", music_mp3, "-i", voice_mp3,
        "-filter_complex",
        f"[0:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={voice_dur-0.8:.3f}:d=0.8,volume=0.15[music];"
        f"[1:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,volume=1.8[voice];"
        "[music][voice]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]", drone_wav
    ]
    subprocess.run(cmd_audio, check=True)
    
    # Write ASS subtitle file
    ass_filename = "subtitles.ass"
    ass_path = os.path.join(config.TOPIC_TEMP_DIR, ass_filename)
    write_ass_subtitles(ass_path)
    
    # Configure Fontconfig
    setup_fontconfig()
    
    print("Merging audio and video with color grading, fades, and ASS subtitles...")
    output_mp4 = os.path.join(config.TOPIC_TEMP_DIR, "output.mp4")
    
    # Single-pass FFmpeg command executing filters: eq (color grade), fade (fade-in/out), subtitles (RTL Nastaliq)
    cmd_merge = [
        "ffmpeg", "-y",
        "-i", "silent_temp.mp4",
        "-i", "drone.wav",
        "-vf", f"eq=contrast=1.15:brightness=-0.15:saturation=1.2,fade=t=in:st=0:d=0.3,fade=t=out:st={voice_dur-0.5:.3f}:d=0.5,subtitles={ass_filename}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "output.mp4"
    ]
    subprocess.run(cmd_merge, check=True, cwd=config.TOPIC_TEMP_DIR)
