import os
import sys
import glob
import random
import contextlib
import importlib
import streamlit as st

from history_reels import config
from history_reels.cli import generate_video_for_topic

def detect_ollama_models() -> list[str]:
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []

@st.cache_data
def get_edge_tts_voices():
    flag_map = {
        "ur-PK": "🇵🇰 Urdu (Pakistan)",
        "ur-IN": "🇮🇳 Urdu (India)",
        "en-US": "🇺🇸 English (US)",
        "en-GB": "🇬🇧 English (UK)",
        "en-AU": "🇦🇺 English (Australia)",
        "en-CA": "🇨🇦 English (Canada)",
        "en-IN": "🇮🇳 English (India)",
        "hi-IN": "🇮🇳 Hindi (India)",
    }
    lang_codes = {
        "ar": "Arabic", "es": "Spanish", "fr": "French", "de": "German", 
        "it": "Italian", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", 
        "ru": "Russian", "tr": "Turkish", "zh": "Chinese", "vi": "Vietnamese",
        "th": "Thai", "sv": "Swedish", "nl": "Dutch", "pl": "Polish"
    }
    recommended_voices = {
        "ur-PK-AsadNeural", "ur-PK-UzmaNeural",
        "en-US-GuyNeural", "en-US-AriaNeural", "en-US-JennyNeural",
        "en-GB-RyanNeural", "en-GB-SoniaNeural"
    }

    def format_display_name(voice_name, gender):
        prefix = "-".join(voice_name.split("-")[:2])
        raw_name = voice_name.split("-")[-1].replace("Neural", "")
        display = ""
        if prefix in flag_map:
            display = f"{flag_map[prefix]} - {raw_name} ({gender})"
        else:
            lang_prefix = voice_name.split("-")[0]
            lang_name = lang_codes.get(lang_prefix, lang_prefix.upper())
            display = f"🌍 {lang_name} ({prefix}) - {raw_name} ({gender})"
            
        if voice_name in recommended_voices:
            display += " (Recommended) ★"
        return display

    try:
        import subprocess
        res = subprocess.run(["edge-tts", "--list-voices"], capture_output=True, text=True, check=True)
        lines = res.stdout.strip().split("\n")
        voices = []
        for line in lines:
            parts = line.split()
            if parts and ("Neural" in parts[0] or "-" in parts[0]):
                voice_name = parts[0]
                gender = parts[1] if len(parts) > 1 else "Unknown"
                voices.append((voice_name, gender))
    except Exception as e:
        print(f"Error fetching edge-tts voices: {e}")
        voices = [
            ("ur-PK-AsadNeural", "Male"),
            ("ur-PK-UzmaNeural", "Female"),
            ("ur-IN-SalmanNeural", "Male"),
            ("ur-IN-GulNeural", "Female"),
            ("en-US-GuyNeural", "Male"),
            ("en-US-AriaNeural", "Female"),
            ("en-GB-SoniaNeural", "Female"),
            ("en-GB-RyanNeural", "Male")
        ]

    structured_voices = []
    for v_id, gender in voices:
        display_str = format_display_name(v_id, gender)
        structured_voices.append({
            "id": v_id,
            "display": display_str
        })

    def get_sort_key(v):
        v_id = v["id"]
        if "ur-" in v_id:
            if v_id in recommended_voices:
                return (0, 0, v_id)
            return (0, 1, v_id)
        elif "en-" in v_id:
            if v_id in recommended_voices:
                return (1, 0, v_id)
            return (1, 1, v_id)
        return (2, 0, v_id)

    structured_voices.sort(key=get_sort_key)
    return structured_voices

# Streamlit Page Config
st.set_page_config(
    page_title="AI CONTENT ENGINE",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark theme premium styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap');

    /* Main app setup */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #080a0f !important;
        background-image: radial-gradient(circle at 10% 20%, rgba(255, 215, 0, 0.02) 0%, transparent 40%),
                          radial-gradient(circle at 90% 80%, rgba(255, 165, 0, 0.01) 0%, transparent 45%) !important;
        color: #c5c6c7;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0e121b !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    /* Header styling */
    @keyframes gradient-flow {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    @keyframes title-glow {
        0% { filter: drop-shadow(0 0 8px rgba(255, 215, 0, 0.3)); }
        50% { filter: drop-shadow(0 0 25px rgba(255, 94, 98, 0.6)); }
        100% { filter: drop-shadow(0 0 8px rgba(255, 215, 0, 0.3)); }
    }

    .main-title {
        font-family: 'Outfit', sans-serif !important;
        font-size: 3.8rem !important;
        font-weight: 900 !important;
        background: linear-gradient(270deg, #FFD700, #ff5e62, #ff9966, #FFD700) !important;
        background-size: 300% 300% !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        text-align: center !important;
        margin-bottom: 0.1rem !important;
        letter-spacing: -2px;
        animation: gradient-flow 8s ease infinite, title-glow 4s ease-in-out infinite !important;
    }

    .subtitle {
        font-family: 'Inter', sans-serif;
        text-align: center !important;
        font-size: 1.05rem !important;
        color: #8E9BB0 !important;
        margin-bottom: 2.5rem !important;
    }

    /* Widget Header design */
    .widget-title {
        font-family: 'Outfit', sans-serif !important;
        font-size: 0.95rem !important;
        font-weight: 700 !important;
        color: #FFD700 !important;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 1.5rem !important;
        margin-bottom: 0.8rem !important;
        border-left: 3px solid #FFA500;
        padding-left: 8px;
    }

    /* Premium Cards styling */
    div.stCard, .premium-card, [data-testid="stForm"] {
        background: rgba(20, 26, 38, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 215, 0, 0.12) !important;
        border-radius: 16px !important;
        padding: 1.5rem !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
        margin-bottom: 1.5rem !important;
        transition: all 0.3s ease !important;
    }

    div.stCard:hover, .premium-card:hover {
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
        box-shadow: 0 12px 40px 0 rgba(255, 215, 0, 0.05), 0 8px 32px 0 rgba(0, 0, 0, 0.4) !important;
    }

    /* Custom button styling overrides */
    .stButton > button, div[data-testid="stFormSubmitButton"] button {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%) !important;
        color: #080a0f !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.6rem 2rem !important;
        box-shadow: 0 4px 15px rgba(255, 165, 0, 0.2) !important;
        transition: all 0.25s ease !important;
        width: 100% !important;
    }

    .stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover {
        background: linear-gradient(135deg, #FFE4B5 0%, #FF8C00 100%) !important;
        box-shadow: 0 6px 20px rgba(255, 165, 0, 0.4) !important;
    }

    /* Secondary Button styling */
    [data-testid="stSidebar"] .stButton > button {
        background: rgba(255, 255, 255, 0.05) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: none !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 215, 0, 0.4) !important;
    }

    /* Style Selectboxes and Inputs */
    div[data-baseweb="select"] > div {
        background-color: #11141e !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
        color: #FFFFFF !important;
    }

    div[data-baseweb="input"] > div {
        background-color: #11141e !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
        color: #FFFFFF !important;
    }

    /* Text area input styling */
    textarea {
        background-color: #11141e !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 12px !important;
    }

    /* Expander styling */
    details {
        background-color: #0f131c !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255, 215, 0, 0.08) !important;
        margin-bottom: 1rem !important;
    }

    /* Tabs styling */
    div[data-testid="stTabBar"] button {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        color: #8E9BB0 !important;
        transition: all 0.3s ease !important;
    }

    div[data-testid="stTabBar"] button[aria-selected="true"] {
        color: #FFD700 !important;
        border-bottom-color: #FFD700 !important;
    }
</style>
""", unsafe_allow_html=True)

# Context manager to redirect stdout/stderr to a Streamlit code block
@contextlib.contextmanager
def redirect_stdout_to_streamlit(placeholder, progress_bar=None, status_text=None):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    class WebConsoleWriter:
        def __init__(self, placeholder, progress_bar, status_text):
            self.placeholder = placeholder
            self.progress_bar = progress_bar
            self.status_text = status_text
            self.buffer = ""
            self.current_progress = 0

        def update_progress(self, percent, msg):
            if percent > self.current_progress:
                self.current_progress = percent
                if self.progress_bar:
                    self.progress_bar.progress(self.current_progress)
                if self.status_text:
                    self.status_text.markdown(f"**{msg} ({self.current_progress}%)**")

        def write(self, text):
            self.buffer += text
            self.buffer = self.buffer[-5000:]
            sys.__stdout__.write(text) # Also write to real console
            
            # Real-time Progress Parsing
            lower_text = text.lower()
            if "generating ai script" in lower_text or "structuring raw script" in lower_text:
                self.update_progress(10, "✍️ Generating AI script...")
            elif "searching for" in lower_text or "downloading" in lower_text:
                self.update_progress(30, "🔍 Fetching stock media...")
            elif "generating voiceover" in lower_text or "edge-tts" in lower_text or "elevenlabs" in lower_text:
                self.update_progress(50, "🎙️ Synthesizing voiceover...")
            elif "extracting clips" in lower_text or "processing video" in lower_text:
                self.update_progress(70, "✂️ Preparing video clips...")
            elif "crossfading clips" in lower_text or "merging final" in lower_text:
                self.update_progress(85, "🎞️ Rendering final video...")
            elif "success! created video" in lower_text or "deliverables copied" in lower_text:
                self.update_progress(100, "✅ Done!")

            if "\n" in text:
                # Only update UI when a line is complete to reduce lag
                # Keep only the last 2000 characters to prevent huge UI slow downs
                display_text = self.buffer[-2000:] if len(self.buffer) > 2000 else self.buffer
                self.placeholder.code(display_text, language="bash")

        def flush(self):
            sys.__stdout__.flush()
            
    writer = WebConsoleWriter(placeholder, progress_bar, status_text)
    sys.stdout = writer
    sys.stderr = writer
    try:
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

# Main Layout
st.markdown("<h1 class='main-title'>🎥 AI CONTENT ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Deploy premium short-form viral AI reels with multi-lingual scripts & advanced TTS engines in a single click.</p>", unsafe_allow_html=True)

# Initialize Session State
if "uploaded_df" not in st.session_state:
    st.session_state["uploaded_df"] = None
if "fetched_articles" not in st.session_state:
    st.session_state["fetched_articles"] = []
if "feed_url_cache" not in st.session_state:
    st.session_state["feed_url_cache"] = ""
if "selected_article_data" not in st.session_state:
    st.session_state["selected_article_data"] = None

# Sidebar Control Panel
with st.sidebar:

    with st.expander("🤖 AI Models & Base Settings", expanded=True):
        provider = st.selectbox(
            "AI Content Provider",
            options=["auto", "gemini", "openai", "groq", "ollama", "openrouter"],
            format_func=lambda x: "Auto" if x == "auto" else (x.upper() if x in ["openai", "ollama", "groq"] else x.capitalize()),
            index=0,
            help="Select 'Auto' for the ultimate fail-proof fallback chain."
        )
    
        if provider == "ollama":
            local_models = detect_ollama_models()
            if local_models:
                default_model = getattr(config, "OLLAMA_MODEL", "qwen2.5:3b")
                default_idx = 0
                if default_model in local_models:
                    default_idx = local_models.index(default_model)
                selected_ollama = st.selectbox(
                    "Ollama Model",
                    options=local_models,
                    index=default_idx,
                    help="Select the local model running on your Ollama service."
                )
                config.OLLAMA_MODEL = selected_ollama
            else:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                is_running = sock.connect_ex(("127.0.0.1", 11434)) == 0
                sock.close()
            
                if is_running:
                    st.warning("⚠️ Ollama is running, but no models were found.")
                    st.info("💡 Download a model by running: `ollama pull qwen2.5:3b` in your terminal.")
                else:
                    st.error("❌ Ollama service not detected on localhost:11434.")
                    st.info("💡 Please start the Ollama desktop app or service on your PC.")
                
                manual_model = st.text_input(
                    "Ollama Model Name (Manual)",
                    value=getattr(config, "OLLAMA_MODEL", "qwen2.5:3b"),
                    help="Specify model name manually."
                )
                config.OLLAMA_MODEL = manual_model
        
        duration_preset = st.selectbox(
            "Video Duration Preset",
            options=["Free (Auto)", "10 seconds", "20 seconds", "30 seconds", "45 seconds", "60 seconds", "2 minutes", "3 minutes", "5 minutes", "10 minutes"],
            index=0,
            help="Specify the target duration preset for the final compiled video reel."
        )
        preset_map = {
            "Free (Auto)": None,
            "10 seconds": 10,
            "20 seconds": 20,
            "30 seconds": 30,
            "45 seconds": 45,
            "60 seconds": 60,
            "2 minutes": 120,
            "3 minutes": 180,
            "5 minutes": 300,
            "10 minutes": 600
        }
        config.TARGET_DURATION = preset_map[duration_preset]
    
        media_selection = st.selectbox(
            "Media Type Preference",
            options=["Mixed (Videos + Images)", "Videos Only", "Images Only"],
            index=0,
            help="Select preference for source assets: Mixed (videos first, images fallback), Videos Only, or Images Only (useful for vintage photos)."
        )
    
        pref_mapping = {
            "Mixed (Videos + Images)": "mixed",
            "Videos Only": "videos",
            "Images Only": "images"
        }
        config.MEDIA_PREFERENCE = pref_mapping[media_selection]
    
        allowed_sources = st.multiselect(
            "Allowed Media Sources",
            options=["Pexels (Videos)", "Pixabay (Videos)", "Storyblocks (Videos)", "Google/Bing (Images)", "Pinterest (Images)", "Wikimedia Commons (Images)", "NASA (Images)", "Internet Archive (Videos)", "Unsplash (Images)"],
            default=["Pexels (Videos)", "Pixabay (Videos)", "Google/Bing (Images)", "Pinterest (Images)", "Wikimedia Commons (Images)"],
            help="Check the stock sites you want to fetch media from. Uncheck to block a site."
        )
    
        source_mapping = {
            "Pexels (Videos)": "pexels",
            "Pixabay (Videos)": "pixabay",
            "Storyblocks (Videos)": "storyblocks",
            "Google/Bing (Images)": "google",
            "Pinterest (Images)": "pinterest",
            "Wikimedia Commons (Images)": "wikimedia_image",
            "NASA (Images)": "nasa_image",
            "Internet Archive (Videos)": "archive",
            "Unsplash (Images)": "unsplash"
        }
        config.ALLOWED_SOURCES = [source_mapping[s] for s in allowed_sources]
    
        size_preset = st.selectbox(
            "Video Size / Aspect Ratio",
            options=["Vertical (9:16) - Reels/TikTok", "Landscape (16:9) - YouTube", "Square (1:1) - Post"],
            index=0,
            help="Select the aspect ratio and frame size preset for compiled videos."
        )
        size_map = {
            "Vertical (9:16) - Reels/TikTok": (720, 1280),
            "Landscape (16:9) - YouTube": (1280, 720),
            "Square (1:1) - Post": (1080, 1080)
        }
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT = size_map[size_preset]

    with st.expander("🎧 Audio & Voice", expanded=False):
        voice_provider = st.selectbox(
            "Voice Narrator Provider",
            options=["Edge-TTS (Free)", "ElevenLabs (Realistic)"],
            index=0,
            help="Select the TTS voice synthesizer engine."
        )
    
        voice_pitch = st.selectbox(
            "Voice Emotion / Pitch",
            options=["Default", "Deep & Serious (Horror)", "High & Excited (Tech/News)"],
            index=0,
            help="Adjust the vocal pitch to match the video's mood."
        )
        pitch_map = {"Default": "default", "Deep & Serious (Horror)": "-15Hz", "High & Excited (Tech/News)": "+15Hz"}
        config.VOICE_PITCH = pitch_map[voice_pitch]
    
        if voice_provider == "ElevenLabs (Realistic)":
            config.VOICE_PROVIDER = "elevenlabs"
            config.ELEVENLABS_VOICE_ID = st.text_input(
                "ElevenLabs Voice ID", 
                value=getattr(config, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") or "21m00Tcm4TlvDq8ikWAM"
            )
        else:
            config.VOICE_PROVIDER = "edge-tts"
            voices_list = get_edge_tts_voices()
            voice_options = [v["display"] for v in voices_list]
            default_voice = getattr(config, "VOICE_ID", "ur-PK-AsadNeural")
            default_index = 0
            for idx, v in enumerate(voices_list):
                if v["id"] == default_voice:
                    default_index = idx
                    break
            selected_display = st.selectbox(
                "Microsoft Edge Voice Narrator",
                options=voice_options,
                index=default_index,
                help="Select the Microsoft Edge narrator voice for voiceovers."
            )
            selected_voice_id = next((v["id"] for v in voices_list if v["display"] == selected_display), voices_list[0]["id"] if voices_list else "ur-PK-AsadNeural")
            config.VOICE_ID = selected_voice_id
        
        vibe_selection = st.selectbox(
            "Background Music Vibe",
            options=["random", "mystery", "epic", "sad", "ancient", "modern", "intense"],
            index=0,
            help="Custom soundtrack feel. 'random' will choose a random vibe."
        )
    
        ambient_sound = st.selectbox(
            "Ambient Soundscape",
            options=["None", "Rain & Thunder", "Wind & Forest", "Intense Rumble (Horror)"],
            index=0,
            help="Automatically mixes dynamic ambient noise into the background."
        )
        ambient_map = {"None": None, "Rain & Thunder": "rain", "Wind & Forest": "wind", "Intense Rumble (Horror)": "rumble"}
        config.AMBIENT_SOUND = ambient_map[ambient_sound]
    
        audio_ducking = st.checkbox("Smart Audio Ducking", value=True, help="Automatically lowers background music when the narrator speaks, and raises it during pauses.")
        config.AUDIO_DUCKING = audio_ducking
    
        voice_mastering = st.checkbox("Voice Mastering (EQ & Compression)", value=True, help="Applies equalizer (bass boost) and compression to make the voice sound rich and professional.")
        config.VOICE_MASTERING = voice_mastering

    with st.expander("🎬 Visuals & Transitions", expanded=False):
        visual_pacing = st.selectbox(
            "Visual Clip Pacing",
            options=["Fast (approx. 3s per cut)", "Medium (approx. 5s per cut)", "Slow (approx. 7s per cut)"],
            index=1,
            help="Select the target pacing. Faster pacing keeps viewers more engaged by cutting between clips frequently."
        )
        pacing_map = {
            "Fast (approx. 3s per cut)": 3.0,
            "Medium (approx. 5s per cut)": 5.0,
            "Slow (approx. 7s per cut)": 7.0
        }
        config.CLIP_DURATION_TARGET = pacing_map[visual_pacing]
    
        transition_selection = st.selectbox(
            "Slide Transition Effect",
            options=["Fade (Crossfade)", "Slide Left", "Slide Right", "Slide Up", "Slide Down", "Wipe Left", "Wipe Right", "Zoom In", "Dissolve", "Pixelize (Mosaic)", "Radial", "Random (Mix)"],
            index=0,
            help="Select the visual transition style between clips."
        )
        trans_map = {
            "Fade (Crossfade)": "fade",
            "Slide Left": "slideleft",
            "Slide Right": "slideright",
            "Slide Up": "slideup",
            "Slide Down": "slidedown",
            "Wipe Left": "wipeleft",
            "Wipe Right": "wiperight",
            "Zoom In": "zoomin",
            "Dissolve": "dissolve",
            "Pixelize (Mosaic)": "pixelize",
            "Radial": "radial",
            "Random (Mix)": "random"
        }
        config.VIDEO_TRANSITION = trans_map[transition_selection]
    
        camera_shake = st.checkbox(
            "Transition Camera Shake",
            value=False,
            help="Adds a dynamic high-energy camera rumble vibration effect during clip transitions."
        )
        config.CAMERA_SHAKE = camera_shake
    
        trans_sfx = st.checkbox("Transition WHOOSH Sound Effect", value=False, help="Synthesizes and injects high-energy whoosh sound effects at every transition point.")
        config.TRANSITION_SFX = trans_sfx
    
        color_lut = st.selectbox(
            "Cinematic Color Grading (LUTs)",
            options=["None", "Horror Dark", "Cyberpunk Neon", "Vintage 1980s", "Documentary High Contrast"],
            index=0,
            help="Applies a global color grading filter to all clips."
        )
        lut_map = {
            "None": None, 
            "Horror Dark": "horror", 
            "Cyberpunk Neon": "cyberpunk", 
            "Vintage 1980s": "vintage", 
            "Documentary High Contrast": "documentary"
        }
        config.COLOR_FILTER = lut_map[color_lut]
    
        cinematic_grain = st.checkbox("Cinematic Noise/Film Grain", value=False, help="Adds vintage moving film grain/noise to background footage.")
        config.CINEMATIC_GRAIN = cinematic_grain

    with st.expander("🏷️ Branding & Overlays", expanded=False):
        # Font Settings
        urdu_font_choice = st.selectbox(
            "Caption Font (Urdu)",
            options=["Jameel Noori Nastaleeq", "Noto Nastaliq Urdu"],
            index=0,
            help="Select the Urdu font for video captions."
        )
        config.URDU_FONT_NAME = urdu_font_choice
        
        custom_font = st.file_uploader("Upload Custom Urdu/English Font (.ttf)", type=["ttf", "otf"])
        if custom_font:
            os.makedirs(os.path.join(config.OUTPUT_DIR, "fonts"), exist_ok=True)
            font_save_path = os.path.join(config.OUTPUT_DIR, "fonts", "custom.ttf")
            with open(font_save_path, "wb") as f:
                f.write(custom_font.getbuffer())
            config.FONT_PATH = font_save_path
            st.success("Custom font loaded successfully!")
    
        # Bumper Settings
        col_intro, col_outro = st.columns(2)
        with col_intro:
            intro_vid = st.file_uploader("Upload Intro Bumper (.mp4)", type=["mp4"])
            if intro_vid:
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                intro_path = os.path.join(config.OUTPUT_DIR, "intro_bumper.mp4")
                with open(intro_path, "wb") as f:
                    f.write(intro_vid.getbuffer())
                config.INTRO_BUMPER = intro_path
            else:
                config.INTRO_BUMPER = None
            
        with col_outro:
            outro_vid = st.file_uploader("Upload Outro Bumper (.mp4)", type=["mp4"])
            if outro_vid:
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                outro_path = os.path.join(config.OUTPUT_DIR, "outro_bumper.mp4")
                with open(outro_path, "wb") as f:
                    f.write(outro_vid.getbuffer())
                config.OUTRO_BUMPER = outro_path
            else:
                config.OUTRO_BUMPER = None
            
        # Progress Bar Settings
        show_bar = st.checkbox("Show Video Progress Bar", value=True, help="Draws an animated growing timeline line at the bottom of the video.")
        config.SHOW_PROGRESS_BAR = show_bar
        if show_bar:
            bar_color = st.selectbox(
                "Progress Bar Color",
                options=["Gold", "Red", "Blue", "Green", "White", "Purple"],
                index=0
            )
            config.PROGRESS_BAR_COLOR = bar_color.lower()
            bar_height = st.slider("Progress Bar Height (px)", min_value=2, max_value=20, value=8)
            config.PROGRESS_BAR_HEIGHT = bar_height
        
        # Text Watermark & Grain
        watermark_text = st.text_input("Text Watermark Handle", value="", placeholder="e.g., @UrduHistory_AI", help="Draws a translucent text brand handle bottom-center of the video.")
        config.WATERMARK_TEXT = watermark_text
    
        # Brand Watermark Settings
        show_logo = st.checkbox("Show Brand Watermark Logo", value=False, help="Overlay a custom translucent brand logo image.")
        config.SHOW_WATERMARK = show_logo
        if show_logo:
            logo_file = st.file_uploader("Upload Logo Image (PNG only)", type=["png"])
            if logo_file:
                # Save to history videos folder
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                logo_path = os.path.join(config.OUTPUT_DIR, "watermark.png")
                with open(logo_path, "wb") as f:
                    f.write(logo_file.getbuffer())
                st.success("Logo uploaded successfully!")
            
            # Check if logo exists to enable size/opacity settings
            logo_path = os.path.join(config.OUTPUT_DIR, "watermark.png")
            if os.path.exists(logo_path):
                st.image(logo_path, caption="Active Watermark Logo", width=100)
                logo_size = st.slider("Logo Size (width in px)", min_value=40, max_value=250, value=100)
                config.WATERMARK_SIZE = logo_size
                logo_opacity = st.slider("Logo Opacity", min_value=0.1, max_value=1.0, value=0.5, step=0.05)
                config.WATERMARK_OPACITY = logo_opacity
            
                pos_selection = st.selectbox(
                    "Logo Position",
                    options=["Top-Right", "Top-Left", "Bottom-Right", "Bottom-Left"],
                    index=0
                )
                pos_map = {
                    "Top-Right": "main_w-overlay_w-20:20",
                    "Top-Left": "20:20",
                    "Bottom-Right": "main_w-overlay_w-20:main_h-overlay_h-20",
                    "Bottom-Left": "20:main_h-overlay_h-20"
                }
                config.WATERMARK_POSITION = pos_map[pos_selection]
            else:
                st.warning("⚠️ Please upload a PNG logo to see settings.")

    with st.expander("🔑 API Keys Configuration", expanded=False):
        new_gemini = st.text_input("Gemini API Key", value=config.GEMINI_API_KEY or "", type="password")
        new_openai = st.text_input("OpenAI API Key", value=config.OPENAI_API_KEY or "", type="password")
        new_groq = st.text_input("Groq API Key", value=config.GROQ_API_KEY or "", type="password")
        new_openrouter = st.text_input("OpenRouter API Key", value=getattr(config, "OPENROUTER_API_KEY", "") or "", type="password")
        new_elevenlabs = st.text_input("ElevenLabs API Key", value=getattr(config, "ELEVENLABS_API_KEY", "") or "", type="password")
        new_pexels = st.text_input("Pexels API Key", value=config.PEXELS_API_KEY or "", type="password")
        new_pixabay = st.text_input("Pixabay API Key", value=config.PIXABAY_API_KEY or "", type="password")
        new_story_pub = st.text_input("Storyblocks Public Key", value=getattr(config, "STORYBLOCKS_PUBLIC_KEY", "") or "", type="password")
        new_story_priv = st.text_input("Storyblocks Private Key", value=getattr(config, "STORYBLOCKS_PRIVATE_KEY", "") or "", type="password")
    
        if st.button("Save & Reload Keys 💾", use_container_width=True):
            # Update local .env file in the workspace root
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            env_content = f"""PEXELS_API_KEY={new_pexels.strip()}
PIXABAY_API_KEY={new_pixabay.strip()}
OPENAI_API_KEY={new_openai.strip()}
GEMINI_API_KEY={new_gemini.strip()}
GROQ_API_KEY={new_groq.strip()}
OPENROUTER_API_KEY={new_openrouter.strip()}
ELEVENLABS_API_KEY={new_elevenlabs.strip()}
ELEVENLABS_VOICE_ID={getattr(config, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()}
VOICE_PROVIDER={getattr(config, "VOICE_PROVIDER", "edge-tts").strip()}
STORYBLOCKS_PUBLIC_KEY={new_story_pub.strip()}
STORYBLOCKS_PRIVATE_KEY={new_story_priv.strip()}
"""
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)
                
            # Update config singleton attributes instantly
            config.GEMINI_API_KEY = new_gemini.strip()
            config.OPENAI_API_KEY = new_openai.strip()
            config.GROQ_API_KEY = new_groq.strip()
            config.OPENROUTER_API_KEY = new_openrouter.strip()
            config.ELEVENLABS_API_KEY = new_elevenlabs.strip()
            config.PEXELS_API_KEY = new_pexels.strip()
            config.PIXABAY_API_KEY = new_pixabay.strip()
            config.STORYBLOCKS_PUBLIC_KEY = new_story_pub.strip()
            config.STORYBLOCKS_PRIVATE_KEY = new_story_priv.strip()
            
            # Update os.environ
            os.environ["GEMINI_API_KEY"] = new_gemini.strip()
            os.environ["OPENAI_API_KEY"] = new_openai.strip()
            os.environ["GROQ_API_KEY"] = new_groq.strip()
            os.environ["OPENROUTER_API_KEY"] = new_openrouter.strip()
            os.environ["ELEVENLABS_API_KEY"] = new_elevenlabs.strip()
            os.environ["PEXELS_API_KEY"] = new_pexels.strip()
            os.environ["PIXABAY_API_KEY"] = new_pixabay.strip()
            os.environ["STORYBLOCKS_PUBLIC_KEY"] = new_story_pub.strip()
            os.environ["STORYBLOCKS_PRIVATE_KEY"] = new_story_priv.strip()
            
            st.toast("API Keys saved to .env & reloaded!", icon="💾")
            st.rerun()

tabs = st.tabs(["🚀 Generate Videos", "📂 View Gallery Output", "ℹ️ Tool Help/Guide"])

# Tab 1: Video Generator
with tabs[0]:
    col_input, col_action = st.columns([2, 1])
    
    with col_input:
        st.markdown("<div class='widget-title'>📝 STEP 1: DEFINE GENERATION PARAMETERS</div>", unsafe_allow_html=True)
        
        mode = st.radio(
            "Generation Mode",
            options=["Single Topic Generation", "Batch Topic Generation", "Live News & RSS Scraping", "CSV/Excel Batch Upload", "AI Script Formatter (Paste Raw Text)", "Fully Custom Script (Manual Override)", "System Benchmark (Fallback Demo)"],
            index=0
        )
        
        topic_input = ""
        batch_input = ""
        news_url = ""
        raw_script_input = ""
        manual_script_data = None
        
        if mode == "Single Topic Generation":
            topic_input = st.text_input("Enter Video Topic", placeholder="e.g. Future of AI, Titanic, Top 5 Horror Stories, Quantum Physics")
        elif mode == "Batch Topic Generation":
            batch_input = st.text_area(
                "Enter Multiple Topics (Comma Separated)",
                placeholder="e.g. AI Revolution, Taj Mahal, Cyber Security, Elon Musk, Space Exploration",
                height=150
            )
        elif mode == "CSV/Excel Batch Upload":
            st.markdown("### 📊 CSV/Excel Batch Upload")
            uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])
            if uploaded_file:
                import pandas as pd
                try:
                    if uploaded_file.name.endswith(".csv"):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    st.success(f"Successfully loaded {len(df)} rows!")
                    st.write(df.head(5))
                    st.session_state["uploaded_df"] = df
                except Exception as e:
                    st.error(f"Error reading file: {e}")
                    st.session_state["uploaded_df"] = None
            else:
                st.session_state["uploaded_df"] = None
        elif mode == "Live News & RSS Scraping":
            st.markdown("### 📰 Automated News Scraping")
            news_url = st.text_input("Enter RSS Feed or Article Web Page URL", value="https://feeds.bbci.co.uk/urdu/rss.xml")
            
            # Setup session state for news articles
            col_fetch, col_clear = st.columns([1, 1])
            with col_fetch:
                if st.button("🔍 Fetch Articles", use_container_width=True):
                    from history_reels.news_scraper import fetch_rss_feed
                    with st.spinner("Fetching and parsing RSS feed..."):
                        articles = fetch_rss_feed(news_url)
                        if articles:
                            st.session_state["fetched_articles"] = articles
                            st.session_state["feed_url_cache"] = news_url
                            st.success(f"Successfully fetched {len(articles)} articles!")
                        else:
                            st.session_state["fetched_articles"] = []
                            st.info("Direct web page URL or empty feed detected. It will be scraped directly when pipeline starts.")
            with col_clear:
                if st.button("🧹 Clear Fetched", use_container_width=True):
                    st.session_state["fetched_articles"] = []
                    st.session_state["feed_url_cache"] = ""
                    st.rerun()
                    
            if st.session_state["fetched_articles"]:
                options_dict = {a["title"]: a for a in st.session_state["fetched_articles"][:10]}
                selected_title = st.selectbox("Select Article/Headline to build Reel", options=list(options_dict.keys()))
                st.session_state["selected_article_data"] = options_dict[selected_title]
                st.markdown(f"**Description:** *{options_dict[selected_title]['description']}*")
            else:
                st.session_state["selected_article_data"] = None
        elif mode == "AI Script Formatter (Paste Raw Text)":
            raw_script_input = st.text_area(
                "Paste Your Raw Script (Multi-Lingual Supported)",
                placeholder="Paste your raw script text here. The selected AI provider will automatically split it into 4 slides, format captions, match queries, and build the video.",
                height=250
            )
        elif mode == "Fully Custom Script (Manual Override)":
            st.markdown("### 📝 Custom Script Configuration")
            title = st.text_input("Video Title", value="Future of AI")
            year = st.text_input("Context / Era / Year", value="Modern Day")
            music_vibe = st.selectbox("Soundtrack Vibe", options=["mystery", "epic", "sad", "ancient", "modern", "intense"], index=0)
            
            st.markdown("#### Subtitles (Urdu Nastaliq - Bold words with **double asterisks**)")
            captions_text = st.text_area("Captions (One per line)", value="کِیا آپ جانتے ہیں کہ **AI** دنیا کیسے بدلے گی؟\nہر طرف **اسمارٹ روبوٹس** کا قبضہ ہوگا۔\nیہ ہماری **زندگیوں** کو آسان بنا دے گا!\nکمنٹس میں اپنی **رائے** کا اظہار کریں۔")
            
            st.markdown("#### Spoken Speech Narration (Urdu Speech Text)")
            narrations_text = st.text_area("Narrations (One per line)", value="کیا آپ جانتے ہیں کہ آرٹیفیشل انٹیلیجنس دنیا کیسے بدلے گی؟\nہر طرف اسمارٹ روبوٹس کا قبضہ ہوگا۔\nیہ ہماری زندگیوں کو آسان بنا دے گا!\nکمنٹس میں اپنی رائے کا اظہار کریں۔")
            
            st.markdown("#### Media Search Queries (comma separated)")
            queries_str = st.text_area(
                "Image/Video Search Queries", 
                value="artificial intelligence, smart robot, futuristic city, cyber security, glowing circuit, neon lights, coding screen, digital brain"
            )
            
            # Parse lists
            captions_list = [c.strip() for c in captions_text.split("\n") if c.strip()]
            narrations_list = [n.strip() for n in narrations_text.split("\n") if n.strip()]
            queries_list = [q.strip() for q in queries_str.split(",") if q.strip()]
            
            # Assemble custom script dictionary structure
            manual_script_data = {
                "title": title.strip(),
                "year": year.strip(),
                "bg_music_vibe": music_vibe,
                "captions": captions_list,
                "narrations": narrations_list,
                "queries": queries_list,
                "seo_title": f"{title.strip()} — Mind Blowing Facts 🧠✨",
                "seo_description": f"{title.strip()} ({year.strip()}) custom script generated manually.",
                "seo_hashtags": "#Viral #Trending #Facts #UrduNarratives",
                "seo_short_caption": f"Mind blowing facts about {title.strip()}! #Viral #Urdu"
            }
            
    with col_action:
        st.markdown("<div class='widget-title'>🎬 STEP 2: COMPILE PIPELINE</div>", unsafe_allow_html=True)
        st.write("Click below to initialize the video generation engine. This will query the AI model, fetch relevant media assets, synthesize audio, and compile the final reel.")
        
        start_btn = st.button("🚀 Generate Video", use_container_width=True)

    # Output Console & Log Blocks
    if start_btn:
        topics_list = []
        if mode == "Single Topic Generation":
            if not topic_input.strip():
                st.error("Error: Please provide a video topic.")
            else:
                topics_list = [topic_input.strip()]
        elif mode == "Batch Topic Generation":
            if not batch_input.strip():
                st.error("Error: Please provide topics.")
            else:
                topics_list = [t.strip() for t in batch_input.split(",") if t.strip()]
        elif mode == "CSV/Excel Batch Upload":
            if "uploaded_df" not in st.session_state or st.session_state["uploaded_df"] is None or st.session_state["uploaded_df"].empty:
                st.error("Error: Please upload a valid CSV or Excel file first.")
            else:
                import pandas as pd
                df = st.session_state["uploaded_df"]
                cols = [c.lower() for c in df.columns]
                has_script_cols = ("title" in cols and "caption_text_1" in cols and "narration_text_1" in cols)
                
                for _, row in df.iterrows():
                    row_dict = {k.lower(): v for k, v in row.to_dict().items()}
                    if has_script_cols:
                        queries_val = row_dict.get("queries", "")
                        if pd.isna(queries_val):
                            queries_val = ""
                        queries_list = [q.strip() for q in str(queries_val).split(",") if q.strip()]
                        while len(queries_list) < 8:
                            queries_list.append("history")
                        queries_list = queries_list[:8]
                        
                        captions_list = []
                        narrations_list = []
                        for i in range(1, 21):
                            cap_val = str(row_dict.get(f"caption_text_{i}", "")).strip()
                            narr_val = str(row_dict.get(f"narration_text_{i}", "")).strip()
                            if cap_val: captions_list.append(cap_val)
                            if narr_val: narrations_list.append(narr_val)
                        
                        script_data = {
                            "title": str(row_dict.get("title", "")).strip(),
                            "year": str(row_dict.get("year", "Unknown")).strip(),
                            "bg_music_vibe": str(row_dict.get("bg_music_vibe", "mystery")).strip(),
                            "captions": captions_list,
                            "narrations": narrations_list,
                            "queries": queries_list,
                            "seo_title": str(row_dict.get("seo_title", f"{row_dict.get('title', '')} — Secrets of the Past 🏺✨")).strip(),
                            "seo_description": str(row_dict.get("seo_description", "")).strip(),
                            "seo_hashtags": str(row_dict.get("seo_hashtags", "#History #Urdu")).strip(),
                            "seo_short_caption": str(row_dict.get("seo_short_caption", "")).strip()
                        }
                        topics_list.append({"type": "manual_script", "data": script_data, "title": script_data["title"]})
                    else:
                        topic_col = None
                        for c in df.columns:
                            if c.lower() in ["topic", "topic_title", "title", "name"]:
                                topic_col = c.lower()
                                break
                        if not topic_col:
                            topic_col = df.columns[0].lower()
                        raw_val = row_dict[topic_col]
                        if pd.isna(raw_val):
                            continue
                        topic_val = str(raw_val).strip()
                        if not topic_val or topic_val.lower() == "nan":
                            continue
                        topics_list.append({"type": "topic", "data": topic_val, "title": topic_val})
        elif mode == "Live News & RSS Scraping":
            if st.session_state.get("selected_article_data"):
                art = st.session_state["selected_article_data"]
                topics_list = [{"type": "rss", "link": art["link"], "desc": art["description"], "title": art["title"]}]
            else:
                if not news_url.strip():
                    st.error("Error: Please provide a news RSS feed or web page URL.")
                else:
                    topics_list = [{"type": "direct", "link": news_url.strip(), "desc": "", "title": "Scraped Article"}]
        elif mode == "AI Script Formatter (Paste Raw Text)":
            if not raw_script_input.strip():
                st.error("Error: Please paste your raw script.")
            else:
                topics_list = [raw_script_input.strip()]
        elif mode == "Fully Custom Script (Manual Override)":
            if not manual_script_data:
                st.error("Please fill in all manual script fields before starting.")
                st.stop()
            topics_list = [manual_script_data["title"]]
        else:
            topics_list = [None] # Fallback mode triggers with None topic

        if topics_list:
            st.markdown("### 🖥️ Live Render Engine Console")
            
            for idx, t in enumerate(topics_list, 1):
                # Setup Modern Progress UI per video
                st.markdown(f"#### 🎬 Processing Video {idx} of {len(topics_list)}")
                status_container = st.container()
                with status_container:
                    status_text = st.empty()
                    progress_bar = st.progress(0)
                    status_text.markdown("**⏳ Initializing Video Engine... (0%)**")
                    
                console_placeholder = st.empty()
                
                # Setup logs placeholder with injected progress states
                with redirect_stdout_to_streamlit(console_placeholder, progress_bar, status_text):
                    # Set custom vibe if selected (non-random)
                    if vibe_selection != "random":
                        config.BG_MUSIC_VIBE = vibe_selection
                    else:
                        import random
                        config.BG_MUSIC_VIBE = random.choice(["mystery", "epic", "sad", "ancient", "modern", "intense"])
                        
                    t_name = t
                    if isinstance(t, dict):
                        t_name = t.get("title", "Scraped Article")
                        
                    if t:
                        if mode == "AI Script Formatter (Paste Raw Text)":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Structuring Raw Script Input...")
                        elif mode == "Live News & RSS Scraping":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Scraping and Structuring from '{t_name}'...")
                        elif mode == "CSV/Excel Batch Upload":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Processing uploaded batch row '{t_name}'...")
                        else:
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Initiating Topic: '{t_name}'")
                    else:
                        print(f"\n[UI Run] Initiating Fallback Mode...")
                        
                    config.reset_per_run_state()
                    try:
                        if mode == "Fully Custom Script (Manual Override)":
                            success = generate_video_for_topic(None, provider=provider, manual_script_data=manual_script_data)
                        elif mode == "AI Script Formatter (Paste Raw Text)":
                            success = generate_video_for_topic(t, provider=provider, is_raw_script=True)
                        elif mode == "Live News & RSS Scraping":
                            from history_reels.news_scraper import scrape_article_text
                            print(f"Scraping clean text content from URL: {t['link']}...")
                            scraped_text = scrape_article_text(t["link"]) or t["desc"] or t["title"]
                            if not scraped_text or not scraped_text.strip():
                                print("Error: Failed to extract text from URL.")
                                success = False
                            else:
                                print(f"Scraped content successfully (Length: {len(scraped_text)} characters).")
                                success = generate_video_for_topic(scraped_text, provider=provider, is_raw_script=True)
                        elif mode == "CSV/Excel Batch Upload":
                            if t["type"] == "manual_script":
                                success = generate_video_for_topic(None, provider=provider, manual_script_data=t["data"])
                            else:
                                success = generate_video_for_topic(t["data"], provider=provider)
                        else:
                            success = generate_video_for_topic(t, provider=provider)
                    except Exception as e:
                        st.error(f"Error generating video for topic: {e}")
                        success = False
                    
                    if success:
                        st.balloons()
                        st.success(f"Successfully generated Video for Topic: '{t_name or 'Baghdad Battery'}'!")
                        
                        # Find and display the generated video + SEO package in UI
                        output_name = config.OUTPUT_NAME
                        
                        video_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.mp4")
                        txt_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.txt")
                        
                        # Render output column
                        st.markdown("### 🎯 Newly Created Deliverable")
                        col_vid, col_txt = st.columns([1, 1])
                        with col_vid:
                            if os.path.exists(video_path):
                                st.video(video_path)
                            else:
                                st.error("Generated video file path not resolved.")
                        with col_txt:
                            if os.path.exists(txt_path):
                                with open(txt_path, "r", encoding="utf-8") as f:
                                    st.text_area("SEO Metadata Package", value=f.read(), height=400)
                            else:
                                st.warning("SEO Package text file not resolved.")
                    else:
                        err_msg = getattr(config, "LAST_ERROR_MESSAGE", "Unknown build error.")
                        st.error(f"❌ Failed compilation for Topic: '{t_name or 'Baghdad Battery'}'\n\n**Reason:** {err_msg}")

# Tab 2: Gallery Output View
with tabs[1]:
    st.markdown("<div class='widget-title'>📂 PREVIEW GENERATED DELIVERABLES</div>", unsafe_allow_html=True)
    st.write(f"Scanned output directory: `{config.OUTPUT_DIR}`")
    
    # Scan directory
    mp4_files = glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4"))
    mp4_files.sort(key=os.path.getmtime, reverse=True)
    
    if not mp4_files:
        st.info("No compiled videos found in the deliverables folder yet. Go to Tab 1 to generate yours!")
    else:
        # Show in clean columns
        for vid_path in mp4_files:
            file_basename = os.path.basename(vid_path)
            file_title = file_basename.rsplit(".", 1)[0]
            
            with st.expander(f"🎬 {file_title}", expanded=False):
                col_g_vid, col_g_txt = st.columns([1, 1])
                
                with col_g_vid:
                    st.video(vid_path)
                    
                with col_g_txt:
                    txt_path = os.path.join(config.OUTPUT_DIR, f"{file_title}.txt")
                    if os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            st.text_area("SEO Package Details", value=f.read(), height=350, key=f"txt_{file_title}")
                    else:
                        st.write("No SEO description metadata txt file found for this video.")

# Tab 3: Tool Help/Guide
with tabs[2]:
    st.markdown("<div class='widget-title'>ℹ️ TOOL HELP / USAGE GUIDE</div>", unsafe_allow_html=True)
    st.write("Welcome to the complete documentation guide. Switch between sub-tabs below to learn how to configure API keys, generate videos, and adjust settings.")
    
    sub_tabs = st.tabs(["🔑 API Keys Setup Info", "🎥 Generation Modes Guide", "⚙️ Sidebar Settings Info"])
    
    with sub_tabs[0]:
        st.markdown("### 🔑 API Keys Setup Walkthrough (API Keys Banane Ka Tareeqa)")
        st.write("Aap apni generation requirements ke mutabiq niche diye gaye tareeqay se free API keys create kar sakte hain:")

        # 1. Google Gemini API Key
        with st.expander("🏺 1. Google Gemini API Key (Recommended)", expanded=True):
            st.markdown("""
            **Working (Kaam):** Auto-generation of documentary script config, Nastaliq captions, narratives, stock media search queries, and SEO metadata.
            
            **How to Get (Banane ka tareeqa):**
            1. Click on [Google AI Studio](https://aistudio.google.com/) website link.
            2. Apne Google (Gmail) Account se log in karein.
            3. Blue color ke **\"Get API Key\"** button par click karein.
            4. **\"Create API Key\"** button press karein aur generated key ko copy kar ke dashboard ke sidebar main paste kar dein.
            """)
            
        # 2. OpenRouter API Key
        with st.expander("🌐 2. OpenRouter API Key (Supports Llama 3.3 / DeepSeek)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Multiple LLM models (e.g. Llama 3.3 70B, DeepSeek R1/V3) ko single endpoint se run karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [OpenRouter.ai](https://openrouter.ai/).
            2. Apne Google account ya email address ke sath log in karein.
            3. Top-right side profile menu open kar ke **\"Keys\"** section par click karein.
            4. Click **\"Create Key\"**, us ka koi bhi name rakhein, aur copy kar ke sidebar main paste karein.
            """)

        # 3. Groq API Key
        with st.expander("⚡ 3. Groq API Key (Super Fast)", expanded=False):
            st.markdown("""
            **Working (Kaam):** High-speed script generation, formatting aur fast JSON returns.
            
            **How to Get (Banane ka tareeqa):**
            1. Open the [Groq Console](https://console.groq.com/).
            2. Apna account create/login karein.
            3. Left sidebar main **\"API Keys\"** section par jayein.
            4. **\"Create API Key\"** button click karein, key copy kar ke save kar lein.
            """)

        # 4. OpenAI API Key
        with st.expander("🧠 4. OpenAI API Key", expanded=False):
            st.markdown("""
            **Working (Kaam):** Alternatives script formatting options (GPT-4o-mini models).
            
            **How to Get (Banane ka tareeqa):**
            1. Visit [OpenAI Developer Platform](https://platform.openai.com/).
            2. Dashboard login kar ke left bar main **\"API Keys\"** par jayein.
            3. **\"Create new secret key\"** click karein aur key copy kar ke dashboard main paste karein.
            """)

        # 5. ElevenLabs API Key
        with st.expander("🗣️ 5. ElevenLabs API Key (Premium Realistic Voices)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Premium ultra-realistic AI voice synthesis generate karne ke liye use hota hai (supports Urdu and English).
            
            **How to Get (Banane ka tareeqa):**
            1. Visit [ElevenLabs.io](https://elevenlabs.io/).
            2. Sign up or log into your account.
            3. Go to **Profile Settings** (bottom left avatar menu) and select **"Profile + API Keys"**.
            4. Copy your **API Key** and paste it in the dashboard.
            """)

        # 6. Pexels Stock Media API Key
        with st.expander("📹 6. Pexels API Key (Free High-Quality Footage)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Script ke flow ke mutabiq free 9:16 vertical stock videos aur images search and download karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [Pexels Developer Portal](https://www.pexels.com/api/).
            2. Sign up / login kar ke apna developer account settings page open karein.
            3. **\"Your API Key\"** section main request submission (simple form entry) karte hi instant aur free API key show ho jayegi, use copy kar ke dashboard sidebar main paste kar dein.
            """)

        # 7. Pixabay Stock Media API Key
        with st.expander("🖼️ 7. Pixabay API Key (Backup Stock Media)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Pexels ke limits lagne par backup images aur videos download karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [Pixabay API Documentation](https://pixabay.com/api/docs/).
            2. Apne Pixabay account main login / register karein.
            3. Documentation page ko refresh/scroll down karein, aur **\"Parameters\"** key description section main check karein, aapka personal **`key`** parameter block visible ho jayega (e.g. `key: 12345678-abcdef...`).
            4. Wo key copy kar ke sidebar main paste kar dein.
            """)

        # 8. Storyblocks Stock Media API Key
        with st.expander("📼 8. Storyblocks API Keys (Premium Footage)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Premium stock videos and footage download karne ke liye direct search integration.
            
            **How to Get (Banane ka tareeqa):**
            1. Visit [Storyblocks Member Portal](https://www.storyblocks.com/).
            2. Login and navigate to the developer/API integration portal.
            3. Generate your **Public API Key** and **Private API Key** and enter them in the dashboard sidebar.
            """)

        # 9. Local Offline Ollama (Offline Mode)
        with st.expander("💻 9. Local Offline Ollama Setup (Offline & Free)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Bina internet aur bina kisi API key ke completely offline script build aur translate karne ke liye local computer engine.
            
            **How to Setup (Setup karne ka tareeqa):**
            1. Visit [Ollama.com](https://ollama.com/) and download application for Windows.
            2. Setup client install karein aur open command prompt (CMD) main run karein:
               `ollama run qwen2.5:3b`
            3. Background main Ollama service ko active rakhein.
            """)

    with sub_tabs[1]:
        st.markdown("### 🎥 Video Generation Modes (Video Banane Ke Tareeqay)")
        st.write("Aap niche diye gaye alag alag modes main se koi bhi choose kar ke video generate kar sakte hain:")

        with st.expander("📝 Mode 1: Single Video (Standard)", expanded=True):
            st.markdown("""
            **Working (Kaam):** Aap is option main bas koi bhi historical or standard video topic likhte hain (e.g. *Taj Mahal* or *Titanic*), aur system AI model ke through automatic voice, script, clips matching aur final compilation process handle karta hai.
            """)

        with st.expander("🗂️ Mode 2: Batch Videos (Multiple)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Agar aapko ek se zyada videos ek sath line-by-line generate karni hain, to topics ko comma (`,`) se separate kar ke enter karein. System har topic par automatic sequence main one-by-one reels ready karega.
            """)

        with st.expander("📰 Mode 3: Automated News Scraping (Live RSS/Web)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Kisi bhi Urdu/English live news website (jaise BBC, Dawn News) ka XML RSS URL ya normal web page link paste karein. System live article contents scrape karega aur automatic reel format main generate kar dega.
            """)

        with st.expander("📊 Mode 4: CSV/Excel Batch Upload", expanded=False):
            st.markdown("""
            **Working (Kaam):** Excel sheet ya CSV file upload karein.
            1. Agar file main sirf simple topics list hai, to AI providers se batch generation hogi.
            2. Agar script pre-defined columns (jaise `caption_text_1`, `narration_text_1`) ke sath hai, to zero-cost manually pre-written videos generate ho jayengi.
            """)

        with st.expander("✍️ Mode 5: Manual AI Script (Paste & Struct)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Aapke paas pre-written Roman Urdu/Urdu paragraph script text hai? Use paste karein, AI automatic use divide karega, timing adjust karega, subtitles layout format karega, aur perfect footage find kar ke video compile kar dega.
            """)

        with st.expander("🎨 Mode 6: Manual Script Input (Free & Custom)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Completely custom manual form. Aap slides ke dynamic text, spoken voice transcripts line by line, custom search keywords aur music vibe khud manually type or edit karte hain. Kisi AI API key consumption ki zaroorat nahi hai (Absolutely Free!).
            """)

        with st.expander("⚙️ Mode 7: Run Fallback Demo (Baghdad Battery)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Local demo run jo local resources (cached media) use kar ke 'Baghdad Battery' short documentary reel compile karta hai, taaki testing main APIs or stock key limits consume na hon.
            """)

    with sub_tabs[2]:
        st.markdown("### ⚙️ Sidebar Controls & Customizations (Extra Settings)")
        st.write("Apni content priority, size ratio, aur video duration customize karne ke liye settings panels configure karein:")

        with st.expander("📐 Video Size / Aspect Ratio Selector", expanded=True):
            st.markdown("""
            **Description:** Video ke visual shape aur dimensions ko select karne ke liye:
            * `Vertical (9:16) - Reels/TikTok`: **720x1280** resolution. Subtitles vertical screens ke center region main clean align hote hain.
            * `Landscape (16:9) - YouTube`: **1280x720** resolution. Subtitles screen ke bottom lower-third main properly adjust ho jate hain.
            * `Square (1:1) - Post`: **1080x1080** resolution. Subtitles standard post size lower-third main render hote hain.
            """)

        with st.expander("⏱️ Video Duration Preset Selector", expanded=False):
            st.markdown("""
            **Description:** Target compiled video duration define karne ke liye presets:
            * Options list main **10s / 20s / 30s / 45s / 60s** (Shorts/Reels) aur **2m / 3m / 5m / 10m** (Longer videos) ke presets shamil hain.
            * **Prompt Scale:** AI script generator target seconds ke according details aur word limits automatic write-up main use karega.
            * **Safety Pad Protection:** Agar spoken audio duration selected preset se thodi kam reh jaye, to system automatically Slide 4 (last call-to-action) ki duration pad kar ke complete preset time video ensure karega bina kisi crash ya glitch ke.
            """)

        with st.expander("🤖 AI Content Provider Selector", expanded=False):
            st.markdown("""
            **Description:** Chunain ke script generation or parsing ka logic kaun handle karega.
            * `gemini`: Google Gemini 2.0 Flash (Fast & reliable).
            * `openai`: OpenAI models.
            * `groq`: Fast Llama 3.3.
            * `ollama`: Offline execution (no key needed).
            * `openrouter`: Advanced Llama 3.3 / DeepSeek.
            """)

        with st.expander("🎶 Background Music Vibe Selector", expanded=False):
            st.markdown("""
            **Description:** Background audio soundtrack vibe selection:
            * `random`: automatic mix.
            * `mystery`: suspenseful, dramatic history.
            * `epic`: loud heroic battle soundscapes.
            * `sad`: tragic emotional sound themes (e.g. Titanic).
            * `ancient`: retro acoustic traditional instruments.
            """)

        with st.expander("🎥 Media Type Preference Selector", expanded=False):
            st.markdown("""
            **Description:** Visual footage filtering preference:
            * `Mixed (Videos + Images)`: videos first, image falls back.
            * `Videos Only`: downloads only vertical video stock loops.
            * `Images Only`: loads static vintage/retro pictures, and compiles them using a smooth dynamic Ken Burns panning-and-zoom motion filter graph (cinematic vertical scale zoom!).
            """)

