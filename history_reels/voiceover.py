import os
import sys
from history_reels.jobs import GenerationJob
from history_reels.ffmpeg_runner import (
    PROBE_TIMEOUT_SECONDS,
    TTS_TIMEOUT_SECONDS,
    AUDIO_TIMEOUT_SECONDS,
    RenderError,
    run_command,
)


VOICE_LANGUAGE_PREFIXES = {
    "Urdu": ("ur-",),
    "English": ("en-",),
    "Hindi": ("hi-",),
    "Arabic": ("ar-",),
    "Roman Urdu": ("ur-", "en-IN-"),
}


def filter_voices_for_language(voices, language):
    """Keep Edge voices compatible with the selected content language."""
    prefixes = VOICE_LANGUAGE_PREFIXES.get(str(language), ())
    if not prefixes:
        return list(voices)
    matching = [voice for voice in voices if str(voice.get("id", "")).startswith(prefixes)]
    return matching or list(voices)

def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        res = run_command(cmd, timeout=PROBE_TIMEOUT_SECONDS, label="ffprobe duration")
        duration = float(str(res.stdout or "").strip())
        if duration <= 0:
            raise ValueError(f"Invalid duration {duration} for {path}")
        return duration
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Please install FFmpeg (includes ffprobe).")
    except (RenderError, ValueError) as e:
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
            target_voice = getattr(job, "VOICE_ID", None) or "ur-PK-AsadNeural"
            if target_voice == "default_voice":
                target_voice = "ur-PK-AsadNeural"
            cmd_tts = [
                sys.executable, "-m", "edge_tts", "--file", temp_txt_path, "--voice", target_voice,
                "--write-media", seg_path
            ]
            job_id = str(getattr(job, "job_id", "") or "") or None
            try:
                run_command(cmd_tts, timeout=TTS_TIMEOUT_SECONDS, job_id=job_id, label="edge-tts")
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
        
    # TARGET_DURATION guides script generation; it must never create a long
    # silent tail or assign all missing time to the final visual.
    target_dur = getattr(job, "TARGET_DURATION", None)
    voice_dur = sum(durations)
    shortfall = 0.0
    if target_dur and voice_dur < float(target_dur):
        shortfall = float(target_dur) - voice_dur
        print(
            f"Narration is {shortfall:.2f}s shorter than the requested target; "
            "using the natural narration duration instead of adding silence."
        )
    job.ACTUAL_NARRATION_DURATION = voice_dur
    job.DURATION_SHORTFALL = shortfall

    # Timings stay with this job and never leak into another render.
    timing = 0
    job.SLIDE_TIMINGS = []
    for d in durations:
        timing += d
        job.SLIDE_TIMINGS.append(timing)
    
    # Concatenate audio segments using FFmpeg
    voice_mp3 = os.path.join(job.TOPIC_TEMP_DIR, "voice.mp3")
    job_id = str(getattr(job, "job_id", "") or "") or None
    if not voice_segments:
        job.SLIDE_TIMINGS = [1.0]
        run_command(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1.0", "-q:a", "9", "-acodec", "libmp3lame", voice_mp3],
            timeout=30,
            job_id=job_id,
            label="silent voice pad",
        )
        return 1.0
    
    cmd_concat = ["ffmpeg", "-y"]
    inputs_str = ""
    for i, seg in enumerate(voice_segments):
        cmd_concat.extend(["-i", seg])
        inputs_str += f"[{i}:a]"
    n = len(voice_segments)
    
    cmd_concat.extend(["-filter_complex", f"{inputs_str}concat=n={n}:v=0:a=1[out]", "-map", "[out]", voice_mp3])
    run_command(cmd_concat, timeout=AUDIO_TIMEOUT_SECONDS, job_id=job_id, label="voice concat")
    
    print(f"Total concatenated voice duration: {voice_dur:.2f} seconds.")
    return voice_dur
