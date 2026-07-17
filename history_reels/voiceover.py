import os
import subprocess
from history_reels.jobs import GenerationJob

def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        duration = float(res.stdout.strip())
        if duration <= 0:
            raise ValueError(f"Invalid duration {duration} for {path}")
        return duration
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Please install FFmpeg (includes ffprobe).")
    except (subprocess.CalledProcessError, ValueError) as e:
        raise RuntimeError(f"Failed to get audio duration for '{path}': {e}")

def generate_voiceover(job: GenerationJob):
    """Generates segmented voiceovers using edge-tts or ElevenLabs and concatenates them."""
    provider = getattr(job, "VOICE_PROVIDER", "edge-tts").lower()
    print(f"Generating voiceover segments using {provider}...")
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
    
    narrations = getattr(job, "NARRATIONS", [])
    if not narrations:
        narrations = [getattr(job, f"NARRATION_TEXT_{i}", "") for i in range(1, 5)]
    narrations = [n for n in narrations if str(n).strip()]
    voice_segments = []
    durations = []
    
    for idx, text in enumerate(narrations, 1):
        seg_path = os.path.join(job.TOPIC_TEMP_DIR, f"voice_{idx}.mp3")
        if provider == "elevenlabs":
            if not getattr(job, "ELEVENLABS_API_KEY", None):
                raise ValueError("Error: ELEVENLABS_API_KEY environment variable is not set. Please set it in your .env file.")
            
            voice_id = getattr(job, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") or "21m00Tcm4TlvDq8ikWAM"
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": job.ELEVENLABS_API_KEY,
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
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=45)
                response.raise_for_status()
                with open(seg_path, "wb") as f:
                    f.write(response.content)
            except Exception:
                if os.path.exists(seg_path):
                    try: os.remove(seg_path)
                    except: pass
                raise
        else:
            temp_txt_path = os.path.join(job.TOPIC_TEMP_DIR, f"voice_text_{idx}.txt")
            with open(temp_txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            cmd_tts = [
                "edge-tts", "--file", temp_txt_path, "--voice", job.VOICE_ID,
                "--write-media", seg_path
            ]
            voice_pitch = getattr(job, "VOICE_PITCH", "default")
            if voice_pitch and voice_pitch != "default":
                cmd_tts.extend(["--pitch", voice_pitch])
            try:
                subprocess.run(cmd_tts, check=True, stdin=subprocess.DEVNULL)
            except Exception:
                if os.path.exists(seg_path):
                    try: os.remove(seg_path)
                    except: pass
                raise
            finally:
                if os.path.exists(temp_txt_path):
                    try: os.remove(temp_txt_path)
                    except: pass
        voice_segments.append(seg_path)
        
        dur = get_audio_duration(seg_path)
        durations.append(dur)
        print(f"Segment {idx} duration: {dur:.2f} seconds.")
        
    # Check if target duration preset is specified, and pad the last slide if narration is shorter
    target_dur = getattr(job, "TARGET_DURATION", None)
    needed_pad = 0
    if target_dur:
        voice_dur = sum(durations)
        if voice_dur < target_dur and durations:
            needed_pad = target_dur - voice_dur
            durations[-1] += needed_pad

    # Timings stay with this job and never leak into another render.
    timing = 0
    job.SLIDE_TIMINGS = []
    for d in durations:
        timing += d
        job.SLIDE_TIMINGS.append(timing)
    
    # Concatenate audio segments using FFmpeg
    voice_mp3 = os.path.join(job.TOPIC_TEMP_DIR, "voice.mp3")
    n = len(voice_segments)
    inputs_str = "".join([f"[{i}:a]" for i in range(n)])
    cmd_concat = ["ffmpeg", "-y"]
    for seg in voice_segments:
        cmd_concat.extend(["-i", seg])
    cmd_concat.extend(["-filter_complex", f"{inputs_str}concat=n={n}:v=0:a=1[out]", "-map", "[out]", voice_mp3])
    subprocess.run(cmd_concat, check=True, stdin=subprocess.DEVNULL)
    
    if needed_pad > 0:
        padded_path = os.path.join(job.TOPIC_TEMP_DIR, "voice_padded.mp3")
        pad_cmd = [
            "ffmpeg", "-y", "-i", voice_mp3,
            "-af", f"apad=pad_dur={needed_pad:.3f}",
            padded_path
        ]
        subprocess.run(pad_cmd, check=True, stdin=subprocess.DEVNULL)
        os.replace(padded_path, voice_mp3)
        print(f"Padded final audio by {needed_pad:.2f}s to reach target {target_dur:.2f}s")
    
    voice_dur = sum(durations)
    print(f"Total concatenated voice duration: {voice_dur:.2f} seconds.")
    return voice_dur
