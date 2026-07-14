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
    """Generates segmented voiceovers using edge-tts or ElevenLabs and concatenates them."""
    provider = getattr(config, "VOICE_PROVIDER", "edge-tts").lower()
    print(f"Generating voiceover segments using {provider}...")
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
        if provider == "elevenlabs":
            if not getattr(config, "ELEVENLABS_API_KEY", None):
                raise ValueError("Error: ELEVENLABS_API_KEY environment variable is not set. Please set it in your .env file.")
            
            voice_id = getattr(config, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") or "21m00Tcm4TlvDq8ikWAM"
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": config.ELEVENLABS_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            import requests
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            response.raise_for_status()
            with open(seg_path, "wb") as f:
                f.write(response.content)
        else:
            temp_txt_path = os.path.join(config.TOPIC_TEMP_DIR, f"voice_text_{idx}.txt")
            with open(temp_txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            cmd_tts = [
                "edge-tts", "--file", temp_txt_path, "--voice", config.VOICE_ID,
                "--write-media", seg_path
            ]
            subprocess.run(cmd_tts, check=True)
        voice_segments.append(seg_path)
        
        dur = get_audio_duration(seg_path)
        durations.append(dur)
        print(f"Segment {idx} duration: {dur:.2f} seconds.")
        
    # Check if target duration preset is specified, and pad the last slide if narration is shorter
    target_dur = getattr(config, "TARGET_DURATION", None)
    if target_dur:
        voice_dur = sum(durations)
        if voice_dur < target_dur:
            needed_pad = target_dur - voice_dur
            durations[3] += needed_pad
            print(f"Padding slide 4 duration by {needed_pad:.2f}s to meet the {target_dur}s preset.")

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
