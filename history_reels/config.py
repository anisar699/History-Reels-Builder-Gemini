import os
import shutil
from dotenv import load_dotenv

# Load environment variables
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
