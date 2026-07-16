import os
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def _sanitize_key(val):
    if not val:
        return ""
    val_strip = val.strip()
    if "api_key_here" in val_strip or "your_" in val_strip:
        return ""
    return val_strip

# API Keys
PEXELS_API_KEY = _sanitize_key(os.environ.get("PEXELS_API_KEY"))
PIXABAY_API_KEY = _sanitize_key(os.environ.get("PIXABAY_API_KEY"))
OPENAI_API_KEY = _sanitize_key(os.environ.get("OPENAI_API_KEY"))
GEMINI_API_KEY = _sanitize_key(os.environ.get("GEMINI_API_KEY"))
GROQ_API_KEY = _sanitize_key(os.environ.get("GROQ_API_KEY"))
OPENROUTER_API_KEY = _sanitize_key(os.environ.get("OPENROUTER_API_KEY"))
ELEVENLABS_API_KEY = _sanitize_key(os.environ.get("ELEVENLABS_API_KEY"))
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
VOICE_PROVIDER = os.environ.get("VOICE_PROVIDER", "edge-tts")
STORYBLOCKS_PUBLIC_KEY = _sanitize_key(os.environ.get("STORYBLOCKS_PUBLIC_KEY"))
STORYBLOCKS_PRIVATE_KEY = _sanitize_key(os.environ.get("STORYBLOCKS_PRIVATE_KEY"))

# Directories
HOME = os.path.expanduser("~")
TEMP_DIR = os.path.join(HOME, "Downloads", "history_reels_tmp")
TOPIC_TEMP_DIR = TEMP_DIR
OUTPUT_DIR = os.path.join(HOME, "Pictures", "history videos")
ASSETS_DIR = os.path.join(os.getcwd(), "assets")
URDU_FONT_NAME = "Jameel Noori Nastaleeq"
FONT_PATH = os.path.join(ASSETS_DIR, f"{URDU_FONT_NAME}.ttf")
MUSIC_DIR = os.path.join(OUTPUT_DIR, "bg_music")

# Global Generation Variables
TOPIC_TITLE = "The Baghdad Battery"
TOPIC_YEAR = "250 BCE"
OUTPUT_NAME = "Baghdad Battery 250 BCE Asad Voice"
BG_MUSIC_VIBE = "mystery"
BG_MUSIC_TRACK_INDEX = 1

# Captions (using Noto Nastaliq Urdu)
CAPTION_TEXT_1 = """کِیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری
**دو ہزار سال پہلے** بنائی گئی تھی؟

1936 میں، بغداد کے قریب سے ایک قدیم مٹی کا برتن ملا،
जिसे Baghdad Battery (Baghdad Battery) कहा जाता है।"""

CAPTION_TEXT_2 = """اس برتن کے اندر **تانبے (copper) کا سلنڈر**
اور لوہے کی راڈ موجود تھی۔"""

CAPTION_TEXT_3 = """جب اس میں سرکہ یا لیموں کا رس ڈالا گیا،
تو اس نے **بجلی پیدا کی**!"""

CAPTION_TEXT_4 = """کِیا دو ہزار سال پہلے کے انسانوں کے پاس
**بجلی کی ٹیکنالوجی** موجود تھی؟

کمنٹس میں اپنی رائے کا اظہار کریں۔"""

# Narrations
NARRATION_TEXT_1 = "کِیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری دو ہزار سال پہلے بنائی گئی تھی؟ 1936 میں، بغداد کے قریب سے ایک قدیم مٹی کا برتن ملا، جسے بغداد بیٹری کہا جاتا ہے۔"
NARRATION_TEXT_2 = "اس برتن کے اندر تانبے کا سلنڈر اور لوہے کی راڈ موجود تھی۔"
NARRATION_TEXT_3 = "جب اس میں سرکہ یا لیموں کا رس ڈالا گیا، تو اس نے بجلی پیدا کی!"
NARRATION_TEXT_4 = "کِیا دو ہزار سال پہلے کے انسانوں کے پاس بجلی کی ٹیکنالوجی موجود تھی؟ کمنٹس میں اپنی رائے کا اظہار کریں۔"

FULL_SPEECH_TEXT = f"{NARRATION_TEXT_1} {NARRATION_TEXT_2} {NARRATION_TEXT_3} {NARRATION_TEXT_4}"

# Default SEO
SEO_TITLE = "The Baghdad Battery — The 2,000-Year-Old Battery 🏺⚡"
SEO_DESCRIPTION = """1936 mein, Baghdad ke qareeb se ek qadeem mitti ka bartan mila, jise Baghdad Battery kaha jata hai.

کیا آپ جانتے ہیں کہ دنیا کی پہلی بیٹری دو ہزار سال پہلے بنائی گئی تھی؟ اس برتن کے اندر تانبے کا سلنڈر اور لوہے کی راڈ موجود تھی۔ 

جب اس میں سرکہ یا لیموں کا رس ڈالا گیا، تو اس نے بجلی پیدا کی! کیا دو ہزار سال پہلے کے انسانوں کے پاس بجلی کی ٹیکنالوجی موجود تھی؟ یا یہ محض ایک اتفاق تھا؟

Comments mein apni rai ka izhaar karein!"""
SEO_HASHTAGS = "#History #BaghdadBattery #UrduHistory #Mysteries #Unsolved #HistoricalFacts #ReelsPakistan #HistoryBuff #AncientTechnology #ScienceMysteries #UrduScript"
SEO_SHORT_CAPTION = "Baghdad Battery 2000 saal purani hai aur isne sach mein electricity generate ki thi. Qadeem technology ya ittefaq? #History #Urdu #Mysteries"

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
VOICE_ID = "ur-PK-AsadNeural"

# Timings and Attributions tracking
SLIDE_TIMINGS = []
DOWNLOADED_VIDEO_IDS = set()
VIDEO_ATTRIBUTIONS = []
MEDIA_PREFERENCE = "mixed"
TARGET_DURATION = None
CLIP_DURATION_TARGET = 5.0
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280

SHOW_PROGRESS_BAR = True
PROGRESS_BAR_COLOR = "gold"
PROGRESS_BAR_HEIGHT = 8
SHOW_WATERMARK = False
WATERMARK_SIZE = 100
WATERMARK_OPACITY = 0.5
WATERMARK_POSITION = "main_w-overlay_w-20:20"
VIDEO_TRANSITION = "fade"
OLLAMA_MODEL = "qwen2.5:3b"
AUDIO_DUCKING = True
VOICE_MASTERING = True
LAST_ERROR_MESSAGE = ""
CINEMATIC_GRAIN = False
CAMERA_SHAKE = False
TRANSITION_SFX = False
WATERMARK_TEXT = ""
TRANSITION_OFFSETS = []
VOICE_PITCH = "default"
AMBIENT_SOUND = None
COLOR_FILTER = None
ALLOWED_SOURCES = ["pexels", "pixabay", "google", "pinterest", "wikimedia_image"]
INTRO_BUMPER = None
OUTRO_BUMPER = None
UNSPLASH_API_KEY = _sanitize_key(os.environ.get("UNSPLASH_API_KEY"))
VOICE_PROVIDER = "edge-tts"

def check_system_dependencies():
    """Verify that FFmpeg and edge-tts are available in PATH."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("edge-tts"):
        missing.append("edge-tts")
    if missing:
        print("\n" + "="*80)
        print("MISSING SYSTEM DEPENDENCIES DETECTED:")
        print("="*80)
        for m in missing:
            if m == "ffmpeg":
                print("- ffmpeg: Required for video slicing, transitions, color grading, and subtitle burning.")
                print("  Download & Install: https://ffmpeg.org/download.html")
                print("  Ensure 'ffmpeg' is added to your system environment variables PATH.")
            elif m == "edge-tts":
                print("- edge-tts: Required to generate Urdu AI narration voiceover.")
                print("  Install via pip: pip install edge-tts")
                print("  Ensure Python Scripts folder is added to system PATH.")
        print("="*80 + "\n")
        return False
    return True

def reset_per_run_state():
    global SLIDE_TIMINGS, DOWNLOADED_VIDEO_IDS
    SLIDE_TIMINGS = []
    DOWNLOADED_VIDEO_IDS = set()
