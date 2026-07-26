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

def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# API Keys
PEXELS_API_KEY = _sanitize_key(os.environ.get("PEXELS_API_KEY"))
PIXABAY_API_KEY = _sanitize_key(os.environ.get("PIXABAY_API_KEY"))
UNSPLASH_API_KEY = _sanitize_key(os.environ.get("UNSPLASH_API_KEY"))
GOOGLE_SEARCH_API_KEY = _sanitize_key(os.environ.get("GOOGLE_SEARCH_API_KEY"))
GOOGLE_SEARCH_CX = _sanitize_key(os.environ.get("GOOGLE_SEARCH_CX"))
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
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
ASSETS_DIR = os.environ.get(
    "HISTORY_REELS_ASSETS_DIR",
    SOURCE_ASSETS_DIR if os.path.isdir(SOURCE_ASSETS_DIR) else os.path.join(HOME, ".history_reels", "assets"),
)
URDU_FONT_NAME = "Jameel Noori Nastaleeq"
FONT_PATH = os.path.join(ASSETS_DIR, f"{URDU_FONT_NAME}.ttf")
CAPTION_FONT_PRESET = "Jameel Noori Nastaleeq"
CAPTION_FONT_FAMILY = "Jameel Noori Nastaleeq"
CAPTION_FONT_BOLD = False
CUSTOM_FONT_PATH = ""
CUSTOM_FONT_FAMILY = ""
CUSTOM_FONT_BOLD = False
CAPTION_FONT_SIZE = 52
MUSIC_DIR = os.path.join(OUTPUT_DIR, "bg_music")
MEDIA_QUALITY_PROFILE = "balanced"
MIN_MEDIA_DIMENSION = 480
MIN_MEDIA_RELEVANCE_SCORE = 6

# Global Generation Variables
TOPIC_TITLE = "Your Next Reel"
TOPIC_YEAR = "Demo"
OUTPUT_NAME = "Your Next Reel Demo"
BG_MUSIC_VIBE = "mystery"
BG_MUSIC_TRACK_INDEX = 1

# Creative brief defaults. The dashboard snapshots these values into every job
# so queued/retried renders keep the user's selected language and tone.
CONTENT_LANGUAGE = "Urdu"
CONTENT_TONE = "Engaging & Clear"

# Neutral Urdu demo captions.
CAPTION_TEXT_1 = """اپنے خیال کو ایک مختصر
اور دلچسپ ویڈیو میں بدلیں۔"""

CAPTION_TEXT_2 = """ایک واضح ہک، مفید معلومات
اور مضبوط بصری انداز منتخب کریں۔"""

CAPTION_TEXT_3 = """اپنے موضوع کے مطابق کلپس،
آواز اور موسیقی شامل کریں۔"""

CAPTION_TEXT_4 = """اپنی اگلی ریل بنائیں
اور اپنی آڈینس سے جڑیں۔"""

# Narrations
NARRATION_TEXT_1 = "اپنے خیال کو ایک مختصر اور دلچسپ ویڈیو میں بدلیں۔"
NARRATION_TEXT_2 = "ایک واضح ہک، مفید معلومات اور مضبوط بصری انداز منتخب کریں۔"
NARRATION_TEXT_3 = "اپنے موضوع کے مطابق کلپس، آواز اور موسیقی شامل کریں۔"
NARRATION_TEXT_4 = "اپنی اگلی ریل بنائیں اور اپنی آڈینس سے جڑیں۔"

FULL_SPEECH_TEXT = f"{NARRATION_TEXT_1} {NARRATION_TEXT_2} {NARRATION_TEXT_3} {NARRATION_TEXT_4}"

# Default SEO
SEO_TITLE = "Your Next Reel — Make Your Idea Stand Out ✨"
SEO_DESCRIPTION = """اپنے خیال کو واضح، مختصر اور دلچسپ ریل میں بدلیں۔

ایک مضبوط ہک، موزوں بصری کلپس اور واضح پیغام آپ کے موضوع کو بہتر انداز میں پیش کرتے ہیں۔

اپنی رائے کمنٹس میں ضرور بتائیں!"""
SEO_HASHTAGS = "#Reels #ShortVideos #ContentCreator #VideoContent #CreativeIdeas #SocialMedia #UrduContent #DigitalCreator"
SEO_SHORT_CAPTION = "اپنے خیال کو ایک دلچسپ ریل میں بدلیں۔ #Reels #ShortVideos #ContentCreator"

QUERIES = [
    "creative workspace",
    "smartphone video creation",
    "social media content",
    "ideas notebook",
    "studio lights",
    "editing timeline",
    "audience engagement",
    "creator success"
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
MAX_JOB_ATTEMPTS = 2
JOB_WORKER_MODE = os.environ.get("JOB_WORKER_MODE", "thread").strip().lower()
DASHBOARD_REQUIRE_AUTH = _env_flag("DASHBOARD_REQUIRE_AUTH")
DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE = _env_flag("DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE")
SHOW_WATERMARK = False
WATERMARK_PATH = ""
WATERMARK_SIZE = 100
WATERMARK_OPACITY = 0.5
WATERMARK_POSITION = "main_w-overlay_w-20:20"
OLLAMA_MODEL = "qwen2.5:7b"
AUDIO_NORMALIZATION = True
AUDIO_TARGET_LUFS = -16.0
AUDIO_TRUE_PEAK_DB = -1.5
AUDIO_LOUDNESS_RANGE = 11.0
LAST_ERROR_MESSAGE = ""
COLOR_FILTER = None
# Pinterest search results often contain unrelated decorative graphics rather
# than usable editorial media. Keep it out of normal reel generation.
ALLOWED_SOURCES = ["pexels", "pixabay", "google", "wikimedia_image"]
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
