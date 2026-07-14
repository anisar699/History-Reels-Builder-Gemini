import os
import subprocess
from history_reels import config

def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())

def generate_voiceover():
    """Generates segmented voiceovers using edge-tts and concatenates them."""
    print(f"Generating voiceover segments using edge-tts with voice {config.VOICE_ID}...")
    os.makedirs(config.TOPIC_TEMP_DIR, exist_ok=True)
    
    narrations = [
        config.NARRATION_TEXT_1,
        config.NARRATION_TEXT_2,
        config.NARRATION_TEXT_3,
        config.NARRATION_TEXT_4
    ]
    voice_segments = []
    durations = []
    
    for idx, text in enumerate(narrations, 1):
        seg_path = os.path.join(config.TOPIC_TEMP_DIR, f"voice_{idx}.mp3")
        cmd_tts = [
            "edge-tts", "--text", text, "--voice", config.VOICE_ID,
            "--write-media", seg_path
        ]
        subprocess.run(cmd_tts, check=True)
        voice_segments.append(seg_path)
        
        dur = get_audio_duration(seg_path)
        durations.append(dur)
        print(f"Segment {idx} duration: {dur:.2f} seconds.")
        
    # Update global timings
    config.SLIDE_TIMINGS = [
        durations[0],
        durations[0] + durations[1],
        durations[0] + durations[1] + durations[2],
        durations[0] + durations[1] + durations[2] + durations[3]
    ]
    
    # Concatenate audio segments using FFmpeg
    voice_mp3 = os.path.join(config.TOPIC_TEMP_DIR, "voice.mp3")
    cmd_concat = [
        "ffmpeg", "-y",
        "-i", voice_segments[0],
        "-i", voice_segments[1],
        "-i", voice_segments[2],
        "-i", voice_segments[3],
        "-filter_complex", "[0:a][1:a][2:a][3:a]concat=n=4:v=0:a=1[out]",
        "-map", "[out]", voice_mp3
    ]
    subprocess.run(cmd_concat, check=True)
    
    voice_dur = sum(durations)
    print(f"Total concatenated voice duration: {voice_dur:.2f} seconds.")
    return voice_dur
