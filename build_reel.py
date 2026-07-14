import os
import sys
import shutil
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import argparse
import json
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Directories
HOME = os.path.expanduser("~")
TEMP_DIR = os.path.join(HOME, "Downloads", "history_reels_tmp")
TOPIC_TEMP_DIR = TEMP_DIR
OUTPUT_DIR = os.path.join(HOME, "Pictures", "history videos")
FONT_PATH = os.path.join(OUTPUT_DIR, "fonts", "NotoNastaliqUrdu-Bold.ttf")
MUSIC_DIR = os.path.join(OUTPUT_DIR, "bg_music")

# Content Configuration
TOPIC_TITLE = "The Baghdad Battery"
TOPIC_YEAR = "250 BCE"
OUTPUT_NAME = "Baghdad Battery Qadeem Tech 250 BCE Asad Voice"

# Vibe selection for background music (options: mystery, epic, sad, ancient)
BG_MUSIC_VIBE = "mystery"
BG_MUSIC_TRACK_INDEX = 2

# 4 Slides of Urdu Script captions (using Noto Nastaliq Urdu)
CAPTION_TEXT_1 = """کِیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری
**دو ہزار سال پہلے** بنائی گئی تھی؟

1936 میں، بغداد کے قریب سے ایک قدیم مٹی کا برتن ملا،
جسے **بغداد بیٹری** (Baghdad Battery) کہا جاتا ہے۔"""

CAPTION_TEXT_2 = """اس برتن کے اندر **تانبے (copper) کا سلنڈر**
اور لوہے کی راڈ موجود تھی۔"""

CAPTION_TEXT_3 = """جب اس میں سرکہ یا لیموں کا رس ڈالا گیا،
تو اس نے **بجلی پیدا کی**!"""

CAPTION_TEXT_4 = """کِیا دو ہزار سال پہلے کے انسانوں کے پاس
**بجلی کی ٹیکنالوجی** موجود تھی؟

کمنٹس میں اپنی رائے کا اظہار کریں۔"""

# Urdu script for narrator (Edge-TTS)
FULL_SPEECH_TEXT = (
    "کِیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری دو ہزار سال پہلے بنائی گئی تھی؟ "
    "1936 میں، بغداد کے قریب سے ایک قدیم مٹی کا برتن ملا، جسے بغداد بیٹری کہا جاتا ہے۔ "
    "اس برتن کے اندر تانبے کا سلنڈر اور لوہے کی راڈ موجود تھی۔ "
    "جب اس میں سرکہ یا لیموں کا رس ڈالا گیا، تو اس نے بجلی پیدا کی! "
    "کِیا دو ہزار سال پہلے کے انسانوں کے پاس بجلی کی ٹیکنالوجی موجود تھی؟ کمنٹس میں اپنی رائے کا اظہار کریں۔"
)

# Default SEO Configuration (Fallback for Baghdad Battery)
SEO_TITLE = "The Baghdad Battery — The 2,000-Year-Old Battery 🏺⚡"
SEO_DESCRIPTION = """1936 mein, Baghdad ke qareeb se ek qadeem mitti ka bartan mila, jise Baghdad Battery kaha jata hai.

کیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری دو ہزار سال پہلے بنائی گئی تھی؟ اس برتن کے اندر تانبے کا سلنڈر اور لوہے کی راڈ موجود تھی۔ 

جب اس میں سرکہ یا لیموں کا رس ڈالا گیا، تو اس نے بجلی پیدا کی! کیا دو ہزار سال پہلے کے انسانوں کے پاس بجلی کی ٹیکنالوجی موجود تھی؟ یا یہ محض ایک اتفاق تھا؟

Comments mein apni rai ka izhaar karein!"""
SEO_HASHTAGS = "#History #BaghdadBattery #UrduHistory #Mysteries #Unsolved #HistoricalFacts #ReelsPakistan #HistoryBuff #AncientTechnology #ScienceMysteries #UrduScript"
SEO_SHORT_CAPTION = "Baghdad Battery 2000 saal purani hai aur isne sach mein electricity generate ki thi. Qadeem technology ya ittefaq? #History #Urdu #Mysteries"

# Search queries for the 8 shots (closely matching the script sentences)
QUERIES = [
    "clay jar",
    "iraq desert",
    "copper cylinder",
    "iron rod",
    "pouring liquid",
    "voltmeter electricity",
    "ancient science",
    "thinking man"
]

FPS = 25
CROSSFADE_DUR = 0.5
NUM_CLIPS = len(QUERIES)
VOICE_ID = "ur-PK-AsadNeural"  # Male Urdu narrator

def download_file(url, path):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def download_clip_for_query(query, index):
    save_path = os.path.join(TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")
    if os.path.exists(save_path):
        print(f"Clip {index} already exists. Skipping download.")
        return True

    # Pexels Search
    print(f"Searching Pexels for '{query}'...")
    url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page=5&orientation=portrait"
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            videos = data.get("videos", [])
            if videos:
                video = videos[0]
                video_files = video.get("video_files", [])
                link = None
                for vf in video_files:
                    if vf.get("width") == 720 or vf.get("width") == 1080:
                        link = vf.get("link")
                        break
                if not link and video_files:
                    link = video_files[0].get("link")
                if link:
                    print(f"Downloading Pexels link: {link[:60]}...")
                    download_file(link, save_path)
                    return True
    except Exception as e:
        print(f"Pexels query failed: {e}")

    # Pixabay Fallback
    print(f"Searching Pixabay for '{query}'...")
    url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={requests.utils.quote(query)}&per_page=5"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            hits = data.get("hits", [])
            if hits:
                hit = hits[0]
                videos = hit.get("videos", {})
                link = videos.get("medium", {}).get("url") or videos.get("large", {}).get("url")
                if link:
                    print(f"Downloading Pixabay link: {link[:60]}...")
                    download_file(link, save_path)
                    return True
    except Exception as e:
        print(f"Pixabay query failed: {e}")

    # Ultimate fallback
    if query != "astrology":
        return download_clip_for_query("astrology", index)

    return False

def fetch_ai_script(topic, provider="gemini"):
    system_prompt = (
        "You are an expert history documentary scriptwriter. Generate script configuration for Urdu short reels in JSON format. "
        "The output must strictly follow this JSON schema:\n"
        "{\n"
        "  \"title\": \"Short English Title (e.g., Giza Pyramids)\",\n"
        "  \"year\": \"Historical Era/Year (e.g., 2560 BCE)\",\n"
        "  \"bg_music_vibe\": \"One of: mystery, epic, sad, ancient\",\n"
        "  \"caption_text_1\": \"Urdu Nastaliq formatted text for Slide 1 (max 3 lines, use bold markdown **word** for key terms, use Zer diacritic like 'کِیا' for the word kiya)\",\n"
        "  \"caption_text_2\": \"Urdu Nastaliq formatted text for Slide 2 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"caption_text_3\": \"Urdu Nastaliq formatted text for Slide 3 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"caption_text_4\": \"Urdu Nastaliq formatted text for Slide 4 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"full_speech_text\": \"The complete Urdu narration text to be spoken. Keep it around 30-40 seconds long, highly engaging. Make sure to use 'کِیا' (with Zer diacritic) instead of standard 'کیا' to ensure perfect pronunciation.\",\n"
        "  \"queries\": [\n"
        "    \"8 specific search queries (only list exactly 8 queries) for Pexels stock video matching the script flow, e.g. ['giza plateau', 'desert pyramids', 'ancient stone blocks', 'workers building', 'pharaoh statue', 'camel walking', 'ancient map', 'sunset pyramids']\"\n"
        "  ],\n"
        "  \"seo_title\": \"Hook/Title for social media (e.g., Pyramids of Giza — Secrets of the Pharaohs 🏺✨)\",\n"
        "  \"seo_description\": \"Detailed social media caption containing Roman Urdu narrative summary and Urdu script summary\",\n"
        "  \"seo_hashtags\": \"Space-separated string of 8-12 relevant hashtags (e.g., '#History #GizaPyramids #Egypt #UrduMysteries')\",\n"
        "  \"seo_short_caption\": \"A short punchy caption for quick copy-paste\"\n"
        "}"
    )

    if provider == "gemini":
        print(f"Calling Google Gemini 1.5 Flash to auto-generate script for topic: '{topic}'...")
        if not GEMINI_API_KEY:
            raise ValueError("Error: GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        prompt_text = f"{system_prompt}\n\nGenerate script configuration in valid JSON format for topic: {topic}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        try:
            raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to parse Gemini API JSON response: {e}. Raw response: {result}")
            
    else:
        print(f"Calling OpenAI GPT-4o-mini to auto-generate script for topic: '{topic}'...")
        if not OPENAI_API_KEY:
            raise ValueError("Error: OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "response_format": { "type": "json_object" },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Topic: {topic}"}
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)

def ensure_assets():
    # Make sure target directories exist
    os.makedirs(os.path.dirname(FONT_PATH), exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    
    # 1. Ensure Urdu Font exists
    if not os.path.exists(FONT_PATH):
        print(f"Urdu Font not found at {FONT_PATH}. Auto-downloading...")
        font_url = "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoNastaliqUrdu/NotoNastaliqUrdu-Bold.ttf"
        try:
            download_file(font_url, FONT_PATH)
            print("Successfully downloaded Urdu Nastaliq Font!")
        except Exception as e:
            print(f"Failed to download font: {e}")
            
    # 2. Ensure Background Music track exists
    track_name = f"{BG_MUSIC_VIBE}_{BG_MUSIC_TRACK_INDEX}"
    target_music_path = os.path.join(MUSIC_DIR, f"{track_name}.mp3")
    
    if not os.path.exists(target_music_path):
        print(f"Background music track '{track_name}.mp3' not found. Auto-downloading...")
        
        # Download URLs mapping
        music_urls = {
            f"{vibe}_{i}": f"https://archive.org/download/ambient-cinematic-music-royalty-free/Cinematic_Ambient_Music_{i}.mp3"
            for vibe in ["mystery", "epic", "sad", "ancient"] for i in range(1, 6)
        }
        
        download_url = music_urls.get(track_name)
        if download_url:
            try:
                download_file(download_url, target_music_path)
                print(f"Successfully downloaded background music: {track_name}.mp3")
            except Exception as e:
                print(f"Failed to download music track: {e}")

def check_inputs():
    os.makedirs(TOPIC_TEMP_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    ensure_assets()
    
    if not os.path.exists(FONT_PATH):
        print(f"Error: Urdu Font not found at {FONT_PATH}")
        return False
        
    # Check selected background music track from local pool
    music_mp3 = os.path.join(MUSIC_DIR, f"{BG_MUSIC_VIBE}_{BG_MUSIC_TRACK_INDEX}.mp3")
    if not os.path.exists(music_mp3):
        # Fallback to any existing .mp3 in MUSIC_DIR
        existing_tracks = [f for f in os.listdir(MUSIC_DIR) if f.endswith(".mp3")]
        if existing_tracks:
            fallback_track = os.path.join(MUSIC_DIR, existing_tracks[0])
            print(f"Warning: Selected music track not found. Using fallback: {existing_tracks[0]}")
            shutil.copy2(fallback_track, music_mp3)
        else:
            print(f"Error: Music file {music_mp3} not found and no fallbacks available!")
            return False

    # Download raw clips
    for i, q in enumerate(QUERIES, start=1):
        if not download_clip_for_query(q, i):
            print(f"Error: Could not retrieve video clip for query '{q}'")
            return False
            
    return True

def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())

def get_video_dimensions(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    parts = res.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])

def grade_image(img):
    img = ImageEnhance.Contrast(img).enhance(1.1)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Brightness(img).enhance(0.95)
    return img

def measure_parsed_line(draw, line, font):
    parts = line.split("**")
    total_w = 0
    max_h = 0
    for i, part in enumerate(parts):
        if part == "":
            continue
        bbox = draw.textbbox((0, 0), part, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        total_w += w
        if h > max_h:
            max_h = h
    return total_w, max_h

def draw_parsed_line(draw, line, x, y, font, normal_color=(255, 255, 255, 255), highlight_color=(255, 215, 0, 255), outline_color=(15, 15, 15, 220)):
    parts = line.split("**")
    curr_x = x
    for i, part in enumerate(parts):
        if part == "":
            continue
        color = highlight_color if i % 2 == 1 else normal_color
        draw.text((curr_x, y), part, font=font, fill=color,
                  stroke_width=1, stroke_fill=outline_color)
        bbox = draw.textbbox((0, 0), part, font=font)
        w = bbox[2] - bbox[0]
        curr_x += w

def draw_caption(img, text, font_path, font_size=28, y_offset=180):
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.truetype(font_path, font_size)
    
    lines = text.split("\n")
    line_heights = []
    line_widths = []
    
    for line in lines:
        if line.strip() == "":
            line_widths.append(0)
            line_heights.append(font_size)
        else:
            w, h = measure_parsed_line(draw, line, font)
            line_widths.append(w)
            line_heights.append(h)
            
    total_width = max(line_widths)
    spacing = 15
    total_height = sum(line_heights) + spacing * (len(lines) - 1)
    
    W_img, H_img = img.size
    box_center_x = W_img / 2
    y = (H_img - total_height) / 2 + y_offset
    
    pad_x = 24
    pad_y = 20
    box_left = box_center_x - (total_width / 2) - pad_x
    box_top = y - pad_y
    box_right = box_center_x + (total_width / 2) + pad_x
    box_bottom = y + total_height + pad_y
    
    try:
        draw.rounded_rectangle([box_left, box_top, box_right, box_bottom], radius=12, fill=(0, 0, 0, 160))
    except AttributeError:
        draw.rectangle([box_left, box_top, box_right, box_bottom], fill=(0, 0, 0, 160))
        
    curr_y = y
    for i, line in enumerate(lines):
        if line.strip() != "":
            line_w = line_widths[i]
            line_x = box_center_x - (line_w / 2)
            draw_parsed_line(draw, line, line_x, curr_y, font)
        curr_y += line_heights[i] + spacing

def build_video_frames(voice_dur):
    print("Extracting clips from source videos...")
    
    total_visual_dur = voice_dur + (NUM_CLIPS - 1) * CROSSFADE_DUR
    clip_dur = total_visual_dur / NUM_CLIPS
    print(f"Dynamic clip duration: {clip_dur:.2f}s (Total video duration: {voice_dur:.2f}s)")
    
    clips = []
    for i in range(1, NUM_CLIPS + 1):
        raw_path = os.path.join(TOPIC_TEMP_DIR, f"raw_clip{i}.mp4")
        clip_path = os.path.join(TOPIC_TEMP_DIR, f"clip{i}.mp4")
        clips.append(clip_path)
        
        w, h = get_video_dimensions(raw_path)
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
            "ffmpeg", "-y", "-ss", "0.0", "-i", raw_path, "-t", f"{clip_dur:.3f}",
            "-vf", vf, "-an", "-r", str(FPS), clip_path
        ]
        subprocess.run(cmd, check=True)
        
    print("Crossfading clips...")
    silent_temp = os.path.join(TOPIC_TEMP_DIR, "silent_temp.mp4")
    
    filter_parts = []
    last_label = "0:v"
    curr_offset = clip_dur - CROSSFADE_DUR
    
    for i in range(1, NUM_CLIPS):
        out_label = f"v{i}"
        filter_parts.append(f"[{last_label}][{i}:v]xfade=transition=fade:duration={CROSSFADE_DUR}:offset={curr_offset:.3f}[{out_label}]")
        last_label = out_label
        curr_offset += clip_dur - CROSSFADE_DUR
        
    filter_complex = ";".join(filter_parts)
    
    cmd_fade = ["ffmpeg", "-y"]
    for c in clips:
        cmd_fade.extend(["-i", c])
    cmd_fade.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]", "-r", str(FPS), silent_temp
    ])
    subprocess.run(cmd_fade, check=True)
    
    print("Extracting frames for caption burning...")
    frames_dir = os.path.join(TOPIC_TEMP_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    cmd_extract = [
        "ffmpeg", "-y", "-i", silent_temp,
        os.path.join(frames_dir, "frame_%04d.jpg")
    ]
    subprocess.run(cmd_extract, check=True)
    
    print("Applying captions and black fades...")
    total_frames = int(voice_dur * FPS)
    black_img = Image.new("RGB", (720, 1280), (0, 0, 0))
    
    for i in range(1, total_frames + 1):
        frame_path = os.path.join(frames_dir, f"frame_{i:04d}.jpg")
        if not os.path.exists(frame_path):
            continue
            
        frame = Image.open(frame_path).convert("RGB")
        frame = grade_image(frame)
        
        # Decide which caption slide to draw dynamically by percentage (4 slides)
        p = i / total_frames
        if p <= 0.25:
            current_text = CAPTION_TEXT_1
        elif p <= 0.50:
            current_text = CAPTION_TEXT_2
        elif p <= 0.75:
            current_text = CAPTION_TEXT_3
        else:
            current_text = CAPTION_TEXT_4
            
        draw_caption(frame, current_text, FONT_PATH)
        
        # Start Fade-In (0.3s -> 8 frames)
        if i <= 8:
            fade_alpha = 1.0 - ((i - 1) / 8.0)
            frame = Image.blend(frame, black_img, fade_alpha)
        # End Fade-Out (0.5s -> 13 frames)
        elif i >= (total_frames - 12):
            fade_alpha = (i - (total_frames - 12)) / 12.0
            frame = Image.blend(frame, black_img, fade_alpha)
            
        frame.save(frame_path, "JPEG", quality=95)
        
    print("Finished processing all frames.")

def run_ffmpeg(voice_dur):
    print("Stitching video...")
    silent_mp4 = os.path.join(TOPIC_TEMP_DIR, "silent.mp4")
    frames_pattern = os.path.join(TOPIC_TEMP_DIR, "frames", "frame_%04d.jpg")
    
    cmd_video = [
        "ffmpeg", "-y", "-r", str(FPS), "-i", frames_pattern,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-level:v", "4.0", "-crf", "18", "-preset", "slow", silent_mp4
    ]
    subprocess.run(cmd_video, check=True)
    
    print("Processing audio track (mixing music and voiceover only)...")
    drone_wav = os.path.join(TOPIC_TEMP_DIR, "drone.wav")
    
    # Use selected track from local bg_music folder
    music_mp3 = os.path.join(MUSIC_DIR, f"{BG_MUSIC_VIBE}_{BG_MUSIC_TRACK_INDEX}.mp3")
    voice_mp3 = os.path.join(TOPIC_TEMP_DIR, "voice.mp3")
    
    # Mix background music and voiceover (no whoosh sound effects overlay)
    cmd_audio = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", music_mp3, "-i", voice_mp3,
        "-filter_complex",
        f"[0:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={voice_dur-0.8:.3f}:d=0.8,volume=0.15[music];"
        f"[1:a]atrim=0:{voice_dur:.3f},asetpts=PTS-STARTPTS,volume=1.8[voice];"
        "[music][voice]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]", drone_wav
    ]
    subprocess.run(cmd_audio, check=True)
    
    print("Merging audio and video...")
    output_mp4 = os.path.join(TOPIC_TEMP_DIR, "output.mp4")
    cmd_merge = [
        "ffmpeg", "-y", "-i", silent_mp4, "-i", drone_wav,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_mp4
    ]
    subprocess.run(cmd_merge, check=True)

def write_seo_package():
    seo_content = f"""================================================================================
SEO PACKAGE — Facebook + Instagram (Urdu Script + Custom Music)
================================================================================

TITLE / HOOK:
{SEO_TITLE}

--------------------------------------------------------------------------------
PRIMARY CAPTION (for Instagram/Facebook feed)
--------------------------------------------------------------------------------
{SEO_DESCRIPTION}

HASHTAGS:
{SEO_HASHTAGS}

--------------------------------------------------------------------------------
QUICK CAPTION (copy-paste short version)
--------------------------------------------------------------------------------
{SEO_SHORT_CAPTION}

--------------------------------------------------------------------------------
MEDIA + MUSIC NOTES
--------------------------------------------------------------------------------
Media: 8 dynamic video clips downloaded via Pexels/Pixabay API.
Music: Custom Pool Music - Vibe: {BG_MUSIC_VIBE} (Track {BG_MUSIC_TRACK_INDEX}) - Royalty Free.
================================================================================
"""
    seo_path = os.path.join(TOPIC_TEMP_DIR, "output.txt")
    with open(seo_path, "w", encoding="utf-8") as f:
        f.write(seo_content)

def copy_deliverables():
    final_video = os.path.join(OUTPUT_DIR, f"{OUTPUT_NAME}.mp4")
    final_txt = os.path.join(OUTPUT_DIR, f"{OUTPUT_NAME}.txt")
    
    print(f"Copying final files to {OUTPUT_DIR}...")
    shutil.copy2(os.path.join(TOPIC_TEMP_DIR, "output.mp4"), final_video)
    shutil.copy2(os.path.join(TOPIC_TEMP_DIR, "output.txt"), final_txt)
    print("Deliverables copied.")

def cleanup():
    print("Cleaning up temporary topic files...")
    if os.path.exists(TOPIC_TEMP_DIR):
        try:
            shutil.rmtree(TOPIC_TEMP_DIR)
            print("Cleanup complete.")
        except Exception as e:
            print(f"Cleanup warning: {e}")

def generate_video_for_topic(topic, provider="gemini"):
    global TOPIC_TITLE, TOPIC_YEAR, OUTPUT_NAME, BG_MUSIC_VIBE, BG_MUSIC_TRACK_INDEX
    global CAPTION_TEXT_1, CAPTION_TEXT_2, CAPTION_TEXT_3, CAPTION_TEXT_4
    global FULL_SPEECH_TEXT, QUERIES, NUM_CLIPS
    global SEO_TITLE, SEO_DESCRIPTION, SEO_HASHTAGS, SEO_SHORT_CAPTION
    global TOPIC_TEMP_DIR

    if topic and topic.strip() != "":
        print(f"\n--- Generating Video for Topic: '{topic}' ({provider.upper()}) ---")
        try:
            ai_data = fetch_ai_script(topic, provider=provider)
            
            # Override global configuration variables
            TOPIC_TITLE = ai_data["title"]
            TOPIC_YEAR = ai_data["year"]
            BG_MUSIC_VIBE = ai_data["bg_music_vibe"]
            BG_MUSIC_TRACK_INDEX = random.randint(1, 5)
            
            # Format clean safe output name
            clean_title = "".join(c for c in TOPIC_TITLE if c.isalnum() or c in (' ', '_', '-')).strip()
            clean_year = "".join(c for c in TOPIC_YEAR if c.isalnum() or c in (' ', '_', '-')).strip()
            OUTPUT_NAME = f"{clean_title} {clean_year} Asad Voice"
            
            # Create a unique topic slug and set dynamic TOPIC_TEMP_DIR
            topic_slug = "".join(c if c.isalnum() else "_" for c in clean_title.lower()).strip("_")
            TOPIC_TEMP_DIR = os.path.join(TEMP_DIR, topic_slug)
            
            CAPTION_TEXT_1 = ai_data["caption_text_1"]
            CAPTION_TEXT_2 = ai_data["caption_text_2"]
            CAPTION_TEXT_3 = ai_data["caption_text_3"]
            CAPTION_TEXT_4 = ai_data["caption_text_4"]
            FULL_SPEECH_TEXT = ai_data["full_speech_text"]
            QUERIES = ai_data["queries"]
            NUM_CLIPS = len(QUERIES)
            
            # Override SEO variables dynamically
            SEO_TITLE = ai_data.get("seo_title", f"{TOPIC_TITLE} ({TOPIC_YEAR})")
            SEO_DESCRIPTION = ai_data.get("seo_description", FULL_SPEECH_TEXT)
            SEO_HASHTAGS = ai_data.get("seo_hashtags", "#History #UrduMysteries")
            SEO_SHORT_CAPTION = ai_data.get("seo_short_caption", FULL_SPEECH_TEXT[:100])
            
            print("\n=== AI Generated Script & Config ===")
            print(f"Title: {TOPIC_TITLE} ({TOPIC_YEAR})")
            print(f"Music Vibe: {BG_MUSIC_VIBE} (Track #{BG_MUSIC_TRACK_INDEX})")
            print(f"Voiceover Text: {FULL_SPEECH_TEXT}")
            print(f"Video Search Queries: {QUERIES}")
            print("====================================\n")
        except Exception as e:
            print(f"Error fetching AI script, skipping topic '{topic}'. Error: {e}")
            return False
    else:
        print("\n--- Running Fallback Mode (Baghdad Battery) ---")
        TOPIC_TEMP_DIR = os.path.join(TEMP_DIR, "baghdad_battery")
        
    # Run the generation pipeline
    try:
        if not check_inputs():
            print("check_inputs failed. Skipping.")
            return False
            
        print(f"Generating voiceover using edge-tts with voice {VOICE_ID}...")
        voice_mp3 = os.path.join(TOPIC_TEMP_DIR, "voice.mp3")
        cmd_tts = [
            "edge-tts", "--text", FULL_SPEECH_TEXT, "--voice", VOICE_ID,
            "--write-media", voice_mp3
        ]
        subprocess.run(cmd_tts, check=True)
        
        voice_dur = get_audio_duration(voice_mp3)
        print(f"Narrator audio duration: {voice_dur:.2f} seconds.")
        
        build_video_frames(voice_dur)
        run_ffmpeg(voice_dur)
        write_seo_package()
        copy_deliverables()
        cleanup()
        print(f"SUCCESS! Created video: {OUTPUT_NAME}.mp4")
        return True
    except Exception as e:
        print(f"Failed to generate video for topic. Error: {e}")
        try:
            cleanup()
        except Exception:
            pass
        return False

if __name__ == "__main__":
    # Fix Windows console encoding for Urdu characters
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    # Get topic from arguments or prompt
    parser = argparse.ArgumentParser(description="AI Short Reel Generator")
    parser.add_argument("--topic", type=str, help="Single topic for the video")
    parser.add_argument("--batch", type=str, help="Path to batch topics txt file")
    parser.add_argument("--provider", type=str, choices=["openai", "gemini"], default="gemini", help="AI provider (openai or gemini)")
    args = parser.parse_args()

    # 1. Populate topics list
    if not args.topic and not args.batch:
        print("\n=== HISTORY REELS GENERATOR ===")
        print("1. Single Video Generation")
        print("2. Batch Video Generation (Input multiple topics)")
        try:
            choice = input("Select option (1 or 2): ").strip()
        except Exception:
            choice = "1"
            
        if choice == "2":
            try:
                topics_input = input("Enter topics separated by commas (e.g. Pyramids of Giza, Titanic, Sutton Hoo): ").strip()
                if topics_input:
                    topics = [t.strip() for t in topics_input.split(",") if t.strip() != ""]
                else:
                    print("No topics entered. Falling back to single video mode.")
                    choice = "1"
            except Exception:
                choice = "1"
                
        if choice == "1":
            try:
                topic = input("Enter video topic (e.g. Pyramids of Giza) or press Enter for default: ").strip()
            except Exception:
                topic = ""
            topics = [topic]
    else:
        if args.topic:
            topics = [args.topic]
        elif args.batch:
            print(f"Reading topics from {args.batch}...")
            try:
                with open(args.batch, "r", encoding="utf-8") as f:
                    for line in f:
                        t = line.strip()
                        if t and not t.startswith("#"):
                            topics.append(t)
                print(f"Loaded {len(topics)} topics from batch file.")
            except Exception as e:
                print(f"Error reading batch file: {e}")
                sys.exit(1)
        
    # 3. Generate videos in loop
    success_count = 0
    fail_count = 0
    failed_topics = []
    
    for i, t in enumerate(topics, start=1):
        if len(topics) > 1:
            print(f"\n========================================")
            print(f" PROCESSING TOPIC {i}/{len(topics)}: {t}")
            print(f"========================================")
            
        res = generate_video_for_topic(t, provider=args.provider)
        if res:
            success_count += 1
        else:
            fail_count += 1
            if t:
                failed_topics.append(t)
                
    if len(topics) > 1:
        print(f"\n=== BATCH SUMMARY ===")
        print(f"Total Topics: {len(topics)}")
        print(f"Successfully Created: {success_count}")
        print(f"Failed: {fail_count}")
        if failed_topics:
            print(f"Failed Topics: {failed_topics}")
        print(f"=====================\n")
