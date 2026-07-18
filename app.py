import os
import glob
import hashlib
import random
import uuid
from datetime import datetime
import streamlit as st

from history_reels import config
from history_reels.font_manager import font_family_from_file, font_options_for_language, get_font_preset
from history_reels.jobs import create_generation_job
from history_reels.job_manager import get_job_manager
from history_reels.job_store import JobStore
from history_reels.input_validation import validate_external_url, validate_uploaded_file
from history_reels.security import require_dashboard_auth, save_local_env_values
from history_reels.voiceover import filter_voices_for_language

config.check_system_dependencies()

WORKFLOW_STAGES = [
    ("queued", "Queued"),
    ("starting", "Starting"),
    ("script", "Script"),
    ("validation", "Validation"),
    ("voice", "Voice"),
    ("media", "Media"),
    ("frames", "Frames"),
    ("render", "Render"),
    ("seo", "SEO"),
    ("deliver", "Deliver"),
    ("verify", "Verify"),
    ("completed", "Complete"),
]


def _workflow_label(stage: str) -> str:
    normalized = str(stage or "queued").lower()
    return dict(WORKFLOW_STAGES).get(normalized, normalized.replace("_", " ").title())


def _format_file_size(size_bytes: int) -> str:
    """Return a compact, friendly file-size label for deliverables."""
    size = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return "—"


def _status_badge(status: str) -> str:
    status = str(status or "queued").lower()
    labels = {
        "queued": "🟡 Queued",
        "running": "🔵 Rendering",
        "succeeded": "🟢 Ready",
        "failed": "🔴 Needs attention",
        "cancelled": "⚪ Cancelled",
    }
    return labels.get(status, f"⚪ {status.title()}")


@st.fragment(run_every=2)
def render_live_generation_status(output_dir: str) -> None:
    """Show durable render progress and its live event terminal on the Generate tab."""
    try:
        job_store = JobStore(output_dir)
        recent_jobs = job_store.list_jobs(limit=25)
    except OSError:
        st.warning("Job history could not be read.")
        return
    live_jobs = [
        record for record in recent_jobs
        if record.get("status") in {"queued", "running"}
    ]

    st.markdown("### Studio render status")
    status_tab, terminal_tab = st.tabs(["Live progress", "Terminal"])

    with status_tab:
        if not live_jobs:
            st.info("No active render right now. Start a video to see its live progress here.")
        else:
            st.caption("Your video keeps rendering in the background. You can safely continue configuring the dashboard.")
            for record in live_jobs:
                stage = str(record.get("current_stage") or "queued").lower()
                progress = max(0, min(100, int(record.get("progress") or 0)))
                events = job_store.list_events(record["job_id"], limit=1)
                message = events[0]["message"] if events else "Waiting for the next pipeline step."
                st.markdown(f"**{record.get('topic', 'Untitled reel')}** · {_status_badge(record.get('status'))}")
                st.progress(progress, text=f"{_workflow_label(stage)} — {progress}% · {message}")

                current_index = next((index for index, (name, _) in enumerate(WORKFLOW_STAGES) if name == stage), 0)
                workflow = []
                for index, (_, label) in enumerate(WORKFLOW_STAGES):
                    icon = "✅" if index < current_index else "🔄" if index == current_index else "○"
                    workflow.append(f"{icon} {label}")
                st.caption(" → ".join(workflow))

    with terminal_tab:
        terminal_jobs = live_jobs or recent_jobs[:1]
        if not terminal_jobs:
            st.caption("The live terminal will show every generation step after you start a video.")
        else:
            job_by_id = {record["job_id"]: record for record in terminal_jobs}
            selected_job_id = st.selectbox(
                "Render job",
                options=list(job_by_id),
                format_func=lambda job_id: (
                    f"{job_by_id[job_id].get('topic', 'Untitled video')} · "
                    f"{_status_badge(job_by_id[job_id].get('status'))}"
                ),
                key="live_render_terminal_job",
            )
            events = job_store.list_events(selected_job_id, limit=100)
            if not events:
                st.caption("Waiting for the worker to write its first event…")
            else:
                terminal_lines = []
                for event in events:
                    timestamp = str(event.get("created_at") or "").replace("T", " ")[:19]
                    progress = event.get("progress")
                    progress_label = f" {int(progress):03d}%" if progress is not None else ""
                    stage = str(event.get("stage") or "system").upper()
                    terminal_lines.append(f"[{timestamp}]{progress_label} {stage:<10} {event.get('message', '')}")
                st.caption("Live pipeline events refresh every 2 seconds. Provider/API secrets are never shown here.")
                st.code("\n".join(terminal_lines), language="text", wrap_lines=True)


def reconcile_interrupted_thread_jobs(output_dir: str) -> int:
    """Clear misleading queued records left behind after a dashboard restart."""
    manager = get_job_manager(config.JOB_WORKER_MODE)
    return manager.reconcile_orphaned_thread_jobs(output_dir)


def completed_deliverable_records(records: list[dict]) -> list[dict]:
    """Return completed jobs whose recorded MP4 still exists locally."""
    return [
        record
        for record in records
        if record.get("status") == "succeeded"
        and record.get("output_video_path")
        and os.path.isfile(record["output_video_path"])
    ]


def render_completed_deliverables(records: list[dict], *, key_prefix: str, heading: str | None = None) -> None:
    """Render verified MP4 and SEO deliverables from durable job records."""
    ready_records = completed_deliverable_records(records)
    if not ready_records:
        return
    if heading:
        st.markdown(heading)

    for record in ready_records:
        job_id = record["job_id"]
        video_path = record["output_video_path"]
        seo_path = record.get("output_seo_path") or os.path.splitext(video_path)[0] + ".txt"
        title = record.get("output_name") or os.path.splitext(os.path.basename(video_path))[0]
        created = str(record.get("updated_at") or record.get("created_at") or "").replace("T", " ")[:19]

        with st.container(border=True):
            st.markdown(f"<div class='gallery-card-title'>✅ {title}</div>", unsafe_allow_html=True)
            try:
                file_size = os.path.getsize(video_path)
            except FileNotFoundError:
                file_size = 0
            st.caption(f"Render complete · {created} · {_format_file_size(file_size)}")
            video_col, seo_col = st.columns([1.15, 0.85])
            with video_col:
                st.video(video_path)
                st.download_button(
                    "⬇️ Download MP4",
                    data=open(video_path, "rb"),
                    file_name=os.path.basename(video_path),
                    mime="video/mp4",
                    key=f"{key_prefix}_video_{job_id}",
                    width="stretch",
                )
            with seo_col:
                if os.path.isfile(seo_path):
                    with open(seo_path, "r", encoding="utf-8") as seo_file:
                        seo_content = seo_file.read()
                    st.text_area("SEO package", value=seo_content, height=250, key=f"{key_prefix}_seo_{job_id}")
                    st.download_button(
                        "⬇️ Download SEO package",
                        data=seo_content,
                        file_name=os.path.basename(seo_path),
                        mime="text/plain",
                        key=f"{key_prefix}_seo_download_{job_id}",
                        width="stretch",
                    )
                else:
                    st.warning("The MP4 is ready, but its SEO package is missing. Generate it again only if you need the SEO text.")

@st.cache_data(ttl=60)
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
            ("en-GB-RyanNeural", "Male"),
            ("en-IN-PrabhatNeural", "Male"),
            ("en-IN-NeerjaNeural", "Female"),
            ("hi-IN-MadhurNeural", "Male"),
            ("hi-IN-SwaraNeural", "Female"),
            ("ar-SA-HamedNeural", "Male"),
            ("ar-SA-ZariyahNeural", "Female")
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

require_dashboard_auth(st)

try:
    interrupted_queue_count = reconcile_interrupted_thread_jobs(config.OUTPUT_DIR)
except Exception:
    # Job history must never prevent the dashboard from opening.
    interrupted_queue_count = 0
if interrupted_queue_count:
    st.warning(
        f"{interrupted_queue_count} interrupted queued render(s) were marked as retryable. "
        "Open My Videos and use Retry to start a fresh worker."
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
    .main-title {
        font-family: 'Outfit', sans-serif !important;
        font-size: clamp(2.25rem, 5vw, 3.5rem) !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #ffe08a, #f5b942) !important;
        background-size: 100% 100% !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        text-align: center !important;
        margin-bottom: 0.1rem !important;
        letter-spacing: -1.5px;
    }

    .subtitle {
        font-family: 'Inter', sans-serif;
        text-align: center !important;
        font-size: 1.05rem !important;
        color: #8E9BB0 !important;
        margin-bottom: 2rem !important;
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

    div.st-key-generate_reel button {
        min-height: 3.65rem !important;
        font-size: 1.12rem !important;
        letter-spacing: 0.01em;
        box-shadow: 0 10px 28px rgba(255, 165, 0, 0.26) !important;
    }

    .studio-callout {
        background: linear-gradient(135deg, rgba(255, 215, 0, 0.10), rgba(22, 28, 42, 0.75));
        border: 1px solid rgba(255, 215, 0, 0.20);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 1rem;
        color: #d8dbe2;
    }

    .gallery-card-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.12rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 0.25rem;
    }

    .gallery-meta {
        color: #9da8ba;
        font-size: 0.88rem;
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

# Main Layout
st.markdown("<h1 class='main-title'>🎥 AI CONTENT ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Deploy premium short-form viral AI reels with multi-lingual scripts & advanced TTS engines in a single click.</p>", unsafe_allow_html=True)
st.warning("⚠️ Warning: Generating multiple reels at the same time is not officially supported and may lead to mixed results. Please wait for the current generation to finish.")

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
            format_func=lambda x: "Auto Fallback (Best Available)" if x == "auto" else (x.upper() if x in ["openai", "ollama", "groq"] else x.capitalize()),
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

        st.markdown("#### Content direction")
        niche_selection = st.selectbox(
            "Content Niche",
            options=["General", "Education & Learning", "Technology & AI", "Business & Finance", "Health & Fitness", "Food & Recipes", "Travel & Lifestyle", "Entertainment & Pop Culture", "Motivation & Self Improvement", "News & Current Affairs", "Gaming", "History & Culture", "Custom"],
            index=0,
            help="Guides the script structure, hook, stock-media queries, and SEO package."
        )
        if niche_selection == "Custom":
            custom_niche = st.text_input("Custom Niche", placeholder="e.g. Real estate for first-time buyers", max_chars=100)
            config.CONTENT_NICHE = custom_niche.strip() or "General"
        else:
            config.CONTENT_NICHE = niche_selection

        config.CONTENT_LANGUAGE = st.selectbox(
            "Content Language",
            options=["Urdu", "English", "Hindi", "Arabic", "Roman Urdu"],
            index=0,
            help="AI-generated captions and narration follow this language. Pasted raw scripts preserve their own wording."
        )
        config.CONTENT_TONE = st.selectbox(
            "Content Tone",
            options=["Engaging & Clear", "Educational", "Energetic & Viral", "Inspirational", "Professional", "Storytelling", "Funny & Casual", "Calm & Reflective", "Dramatic"],
            index=0,
            help="Sets the writing voice, hook, pacing, and call to action."
        )
        config.TARGET_PLATFORM = st.selectbox(
            "Target Platform",
            options=["Instagram Reels", "TikTok", "YouTube Shorts", "Facebook Reels", "LinkedIn", "X (Twitter)"],
            index=0,
            help="Tailors the hook and SEO copy. Frame size remains under Video Size / Aspect Ratio."
        )
        config.VISUAL_STYLE = st.selectbox(
            "Visual Style",
            options=["Cinematic", "Clean & Minimal", "Documentary", "Modern & Tech", "Warm & Lifestyle", "Fast-Paced Social", "Dark & Moody", "Bold & Colorful"],
            index=0,
            help="Guides stock-media search queries and the visual direction in the generated script."
        )
        st.caption("Language-aware caption fonts and custom font upload are supported for the selected content language.")

    
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
            voices_list = filter_voices_for_language(get_edge_tts_voices(), config.CONTENT_LANGUAGE)
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
                help=f"Voices compatible with {config.CONTENT_LANGUAGE} are shown first."
            )
            selected_voice_id = next((v["id"] for v in voices_list if v["display"] == selected_display), voices_list[0]["id"] if voices_list else "ur-PK-AsadNeural")
            config.VOICE_ID = selected_voice_id
        
        vibe_selection = st.selectbox(
            "Background Music Vibe",
            options=["random", "mystery", "epic", "sad", "ancient", "modern", "intense"],
            index=0,
            help="Local royalty-free soundtrack feel. A selected track is generated once and then reused offline."
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

        quality_selection = st.selectbox(
            "Media Quality Profile",
            options=["Balanced (recommended)", "High quality (slower, stricter)"],
            index=0,
            help="Filters out low-resolution source videos before download. High quality may return fewer results for niche topics."
        )
        config.MEDIA_QUALITY_PROFILE = "high" if quality_selection.startswith("High") else "balanced"
        config.MIN_MEDIA_DIMENSION = 720 if config.MEDIA_QUALITY_PROFILE == "high" else 480
    
        st.markdown("**Allowed Media Sources**", help="Check the stock sites you want to fetch media from.")
        sources_list = ["Pexels (Videos)", "Pixabay (Videos)", "Storyblocks (Videos)", "Google/Bing (Images)", "Wikimedia Commons (Images)", "NASA (Images)", "Internet Archive (Videos)", "Unsplash (Images)"]
        default_sources = ["Pexels (Videos)", "Pixabay (Videos)", "Google/Bing (Images)", "Wikimedia Commons (Images)"]
        allowed_sources = []
        
        cols = st.columns(2)
        for i, source in enumerate(sources_list):
            with cols[i % 2]:
                if st.checkbox(source, value=(source in default_sources)):
                    allowed_sources.append(source)
    
        source_mapping = {
            "Pexels (Videos)": "pexels",
            "Pixabay (Videos)": "pixabay",
            "Storyblocks (Videos)": "storyblocks",
            "Google/Bing (Images)": "google",
            "Wikimedia Commons (Images)": "wikimedia_image",
            "NASA (Images)": "nasa_image",
            "Internet Archive (Videos)": "archive",
            "Unsplash (Images)": "unsplash"
        }
        config.ALLOWED_SOURCES = [source_mapping[s] for s in allowed_sources]
        st.markdown('---')
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
        active_language = getattr(config, "CONTENT_LANGUAGE", "Urdu")
        font_options = font_options_for_language(active_language)
        caption_font_choice = st.selectbox(
            f"Caption Font ({active_language})",
            options=font_options,
            index=0,
            help="The selected font is downloaded once if missing and burned directly into video captions."
        )
        font_preset = get_font_preset(caption_font_choice)
        config.CAPTION_FONT_PRESET = caption_font_choice
        config.CAPTION_FONT_FAMILY = font_preset["family"]
        config.CAPTION_FONT_BOLD = bool(font_preset.get("bold", False))
        config.URDU_FONT_NAME = font_preset["family"]  # Backward-compatible setting name.
        config.FONT_PATH = os.path.join(config.ASSETS_DIR, font_preset["filename"])
        config.CUSTOM_FONT_PATH = ""
        config.CUSTOM_FONT_FAMILY = ""
        config.CUSTOM_FONT_BOLD = False
        config.CAPTION_FONT_SIZE = st.slider("Caption Font Size", min_value=28, max_value=84, value=52, step=1)
        
        custom_font = st.file_uploader("Upload Custom Caption Font (.ttf/.otf)", type=["ttf", "otf"])
        if custom_font:
            valid, reason = validate_uploaded_file(custom_font, "font")
            if not valid:
                st.error(f"Custom font rejected: {reason}")
            else:
                os.makedirs(os.path.join(config.OUTPUT_DIR, "fonts"), exist_ok=True)
                extension = os.path.splitext(custom_font.name)[1].lower() or ".ttf"
                font_bytes = bytes(custom_font.getbuffer())
                font_digest = hashlib.sha256(font_bytes).hexdigest()[:12]
                font_save_path = os.path.join(config.OUTPUT_DIR, "fonts", f"custom_caption_{font_digest}{extension}")
                with open(font_save_path, "wb") as f:
                    f.write(font_bytes)
                config.FONT_PATH = font_save_path
                config.CUSTOM_FONT_PATH = font_save_path
                config.CAPTION_FONT_PRESET = "Custom upload"
                config.CUSTOM_FONT_FAMILY = font_family_from_file(font_save_path, os.path.splitext(custom_font.name)[0])
                config.CUSTOM_FONT_BOLD = st.checkbox("Render custom font in bold weight", value=False)
                config.CAPTION_FONT_FAMILY = config.CUSTOM_FONT_FAMILY
                config.CAPTION_FONT_BOLD = config.CUSTOM_FONT_BOLD
                st.success(f"Custom font loaded and will be used for this job: {config.CUSTOM_FONT_FAMILY}")
    
        # Bumper Settings
        col_intro, col_outro = st.columns(2)
        with col_intro:
            intro_vid = st.file_uploader("Upload Intro Bumper (.mp4)", type=["mp4"])
            if intro_vid:
                valid, reason = validate_uploaded_file(intro_vid, "mp4")
                if not valid:
                    st.error(f"Intro video rejected: {reason}")
                else:
                    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                    intro_path = os.path.join(config.OUTPUT_DIR, f"intro_bumper_{uuid.uuid4().hex[:8]}.mp4")
                    with open(intro_path, "wb") as f:
                        f.write(intro_vid.getbuffer())
                    config.INTRO_BUMPER = intro_path
            else:
                config.INTRO_BUMPER = None
            
        with col_outro:
            outro_vid = st.file_uploader("Upload Outro Bumper (.mp4)", type=["mp4"])
            if outro_vid:
                valid, reason = validate_uploaded_file(outro_vid, "mp4")
                if not valid:
                    st.error(f"Outro video rejected: {reason}")
                else:
                    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                    outro_path = os.path.join(config.OUTPUT_DIR, f"outro_bumper_{uuid.uuid4().hex[:8]}.mp4")
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
        watermark_text = st.text_input("Text Watermark Handle", value="", placeholder="e.g., @YourBrand", help="Draws a translucent text brand handle bottom-center of the video.")
        config.WATERMARK_TEXT = watermark_text
    
        # Brand Watermark Settings
        show_logo = st.checkbox("Show Brand Watermark Logo", value=False, help="Overlay a custom translucent brand logo image.")
        config.SHOW_WATERMARK = show_logo
        if show_logo:
            logo_file = st.file_uploader("Upload Logo Image (PNG only)", type=["png"])
            if logo_file:
                valid, reason = validate_uploaded_file(logo_file, "png")
                if not valid:
                    st.error(f"Logo rejected: {reason}")
                else:
                    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
                    logo_path = os.path.join(config.OUTPUT_DIR, f"watermark_{uuid.uuid4().hex[:8]}.png")
                    with open(logo_path, "wb") as f:
                        f.write(logo_file.getbuffer())
                    st.session_state["watermark_logo_path"] = logo_path
                    st.success("Logo uploaded successfully!")
            
            # Check if logo exists to enable size/opacity settings
            logo_path = st.session_state.get("watermark_logo_path", os.path.join(config.OUTPUT_DIR, "watermark.png"))
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

    with st.expander("🔑 API Key Status", expanded=False):
        key_definitions = [
            ("Gemini API Key", "GEMINI_API_KEY"),
            ("OpenAI API Key", "OPENAI_API_KEY"),
            ("Groq API Key", "GROQ_API_KEY"),
            ("OpenRouter API Key", "OPENROUTER_API_KEY"),
            ("ElevenLabs API Key", "ELEVENLABS_API_KEY"),
            ("Pexels API Key", "PEXELS_API_KEY"),
            ("Pixabay API Key", "PIXABAY_API_KEY"),
            ("Storyblocks Public Key", "STORYBLOCKS_PUBLIC_KEY"),
            ("Storyblocks Private Key", "STORYBLOCKS_PRIVATE_KEY"),
        ]
        configured = [label for label, attribute in key_definitions if bool(getattr(config, attribute, ""))]
        st.caption(f"{len(configured)}/{len(key_definitions)} key(s) configured. Values remain hidden; leave a field blank to keep its existing value.")
        st.info("New values are saved only to this computer's local `.env` file and applied immediately. Do not enable this dashboard for untrusted public users.")
        updates = {}
        for label, attribute in key_definitions:
            status = "configured" if bool(getattr(config, attribute, "")) else "not configured"
            updates[attribute] = st.text_input(
                label,
                value="",
                type="password",
                placeholder=f"Currently {status}; enter a replacement to change it",
                key=f"saved_{attribute.lower()}",
            )
        if st.button("Save API keys locally", width="stretch"):
            try:
                saved = save_local_env_values(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                    updates,
                )
            except Exception as error:
                st.error(f"Could not save local API settings: {error}")
            else:
                for attribute in saved:
                    value = updates[attribute].strip()
                    setattr(config, attribute, value)
                if saved:
                    st.toast(f"Saved and applied {len(saved)} API key(s) locally.", icon="🔐")
                    st.rerun()
                st.info("No new key was entered; existing configuration was kept unchanged.")

tabs = st.tabs(["🚀 Create Reel", "🎞️ My Videos", "ℹ️ Tool Help/Guide"])

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
            topic_input = st.text_input("Enter Video Topic", placeholder="e.g. Future of AI, 5 healthy breakfast ideas, Quantum Physics")
        elif mode == "Batch Topic Generation":
            batch_input = st.text_area(
                "Enter Multiple Topics (Comma Separated)",
                placeholder="e.g. Study Tips, Home Workout, Cyber Security, Travel Guide, Space Exploration",
                height=150
            )
        elif mode == "CSV/Excel Batch Upload":
            st.markdown("### 📊 CSV/Excel Batch Upload")
            uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])
            if uploaded_file:
                import pandas as pd
                try:
                    expected_kind = "csv" if uploaded_file.name.lower().endswith(".csv") else "xlsx"
                    valid, reason = validate_uploaded_file(uploaded_file, expected_kind)
                    if not valid:
                        raise ValueError(reason)
                    if expected_kind == "csv":
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    if len(df) > 1_000 or len(df.columns) > 100:
                        raise ValueError("Batch files are limited to 1,000 rows and 100 columns.")
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
                if st.button("🔍 Fetch Articles", width="stretch"):
                    from history_reels.news_scraper import fetch_rss_feed
                    valid, reason = validate_external_url(news_url)
                    if not valid:
                        st.error(f"URL rejected: {reason}")
                        articles = []
                    else:
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
                if st.button("🧹 Clear Fetched", width="stretch"):
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
            
            manual_examples = {
                "Urdu": ("کیا آپ جانتے ہیں کہ **AI** دنیا کیسے بدل رہی ہے؟\nیہ کام کو زیادہ **تیز** بنا سکتی ہے۔", "کیا آپ جانتے ہیں کہ اے آئی دنیا کیسے بدل رہی ہے؟\nیہ کام کو زیادہ تیز بنا سکتی ہے۔"),
                "English": ("How is **AI** changing everyday work?\nIt can make routine tasks **faster**.", "How is AI changing everyday work?\nIt can make routine tasks faster."),
                "Hindi": ("**AI** रोज़मर्रा के काम को कैसे बदल रही है?\nयह सामान्य कार्यों को **तेज़** बना सकती है।", "एआई रोज़मर्रा के काम को कैसे बदल रही है?\nयह सामान्य कार्यों को तेज़ बना सकती है।"),
                "Arabic": ("كيف يغيّر **الذكاء الاصطناعي** العمل اليومي؟\nيمكنه جعل المهام **أسرع**.", "كيف يغيّر الذكاء الاصطناعي العمل اليومي؟\nيمكنه جعل المهام أسرع."),
                "Roman Urdu": ("**AI** rozmarra ka kaam kaise badal rahi hai?\nYeh routine tasks ko **tez** bana sakti hai.", "AI rozmarra ka kaam kaise badal rahi hai?\nYeh routine tasks ko tez bana sakti hai."),
            }
            example_captions, example_narrations = manual_examples.get(config.CONTENT_LANGUAGE, manual_examples["English"])
            st.markdown(f"#### Subtitles ({config.CONTENT_LANGUAGE}; bold words with **double asterisks**)")
            captions_text = st.text_area("Captions (One per line)", value=example_captions)
            
            st.markdown(f"#### Spoken Narration ({config.CONTENT_LANGUAGE})")
            narrations_text = st.text_area("Narrations (One per line)", value=example_narrations)
            
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
                "seo_title": f"{title.strip()} — Watch This ✨",
                "seo_description": f"{title.strip()} ({year.strip()}) custom script generated manually.",
                "seo_hashtags": "#Reels #ShortVideos #ContentCreator",
                "seo_short_caption": f"Watch this reel about {title.strip()}! #Reels #ShortVideos"
            }
            
    with col_action:
        st.markdown("<div class='widget-title'>🎬 STEP 2: GENERATE VIDEO</div>", unsafe_allow_html=True)
        st.caption("Your sidebar settings will be saved with this render.")
        
        start_btn = st.button("✨ Generate Video", key="generate_reel", width="stretch")

    # Output Console & Log Blocks
    if start_btn:
        topics_list = []
        if mode == "Single Topic Generation":
            if not topic_input.strip():
                st.error("Add a video topic to start. Example: “5 productivity tips for students”.")
            else:
                topics_list = [topic_input.strip()]
        elif mode == "Batch Topic Generation":
            if not batch_input.strip():
                st.error("Add at least one topic, separated by commas, to create a batch.")
            else:
                topics_list = [t.strip() for t in batch_input.split(",") if t.strip()]
        elif mode == "CSV/Excel Batch Upload":
            if "uploaded_df" not in st.session_state or st.session_state["uploaded_df"] is None or st.session_state["uploaded_df"].empty:
                st.error("Upload a valid CSV or Excel file before starting this batch.")
            else:
                import pandas as pd
                df = st.session_state["uploaded_df"]
                cols = [str(c).lower() for c in df.columns]
                has_script_cols = ("title" in cols and "caption_text_1" in cols and "narration_text_1" in cols)
                
                for _, row in df.iterrows():
                    row_dict = {k.lower(): v for k, v in row.to_dict().items()}
                    def cell_text(name, default=""):
                        value = row_dict.get(name, default)
                        return "" if pd.isna(value) else str(value).strip()

                    if has_script_cols:
                        queries_val = cell_text("queries")
                        queries_list = [q.strip() for q in str(queries_val).split(",") if q.strip()]
                        while len(queries_list) < 8:
                            queries_list.append("general visual storytelling")
                        queries_list = queries_list[:8]
                        
                        captions_list = []
                        narrations_list = []
                        for i in range(1, 21):
                            cap_val = cell_text(f"caption_text_{i}")
                            narr_val = cell_text(f"narration_text_{i}")
                            if cap_val:
                                captions_list.append(cap_val)
                            if narr_val:
                                narrations_list.append(narr_val)
                        
                        script_data = {
                            "title": cell_text("title"),
                            "year": cell_text("year", "Unknown"),
                            "bg_music_vibe": cell_text("bg_music_vibe", "mystery"),
                            "captions": captions_list,
                            "narrations": narrations_list,
                            "queries": queries_list,
                            "seo_title": cell_text("seo_title", f"{cell_text('title')} — Watch This ✨"),
                            "seo_description": cell_text("seo_description"),
                            "seo_hashtags": cell_text("seo_hashtags", "#Reels #ShortVideos #ContentCreator"),
                            "seo_short_caption": cell_text("seo_short_caption")
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
                topics_list = [{"type": "rss", "link": art.get("link", ""), "desc": art.get("description", ""), "title": art.get("title", "")}]
            else:
                if not news_url.strip():
                    st.error("Add a valid public RSS feed or article URL before starting.")
                else:
                    topics_list = [{"type": "direct", "link": news_url.strip(), "desc": "", "title": "Scraped Article"}]
        elif mode == "AI Script Formatter (Paste Raw Text)":
            if not raw_script_input.strip():
                st.error("Paste the script you want the AI to format before starting.")
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
            manager = get_job_manager(config.JOB_WORKER_MODE)
            queued_jobs = []
            for idx, t in enumerate(topics_list, 1):
                config.BG_MUSIC_VIBE = (
                    vibe_selection if vibe_selection != "random"
                    else random.choice(["mystery", "epic", "sad", "ancient", "modern", "intense"])
                )
                job = create_generation_job(config)
                if mode == "Fully Custom Script (Manual Override)":
                    job_id = manager.submit(job, topic=None, provider=provider, manual_script_data=manual_script_data)
                elif mode == "AI Script Formatter (Paste Raw Text)":
                    job_id = manager.submit(job, topic=t, provider=provider, is_raw_script=True)
                elif mode == "Live News & RSS Scraping":
                    job_id = manager.submit(job, topic=t, provider=provider)
                elif mode == "CSV/Excel Batch Upload" and t["type"] == "manual_script":
                    job_id = manager.submit(job, topic=None, provider=provider, manual_script_data=t["data"])
                elif mode == "CSV/Excel Batch Upload":
                    job_id = manager.submit(job, topic=t["data"], provider=provider)
                else:
                    job_id = manager.submit(job, topic=t, provider=provider)
                queued_jobs.append(job_id)

            st.success(f"{len(queued_jobs)} reel job(s) added to the render queue.")
            st.session_state["latest_render_job_ids"] = queued_jobs
            st.info("Follow the live stage tracker below. The completed video and its SEO package will appear here automatically.")

    st.markdown("### 🧵 Background Render Queue")
    render_live_generation_status(config.OUTPUT_DIR)
    try:
        current_records = JobStore(config.OUTPUT_DIR).list_jobs(limit=25)
    except OSError:
        current_records = []
    tracked_ids = st.session_state.get("latest_render_job_ids", [])
    tracked_records = [record for record in current_records if record.get("job_id") in tracked_ids]
    completed_current_records = completed_deliverable_records(tracked_records)
    if not completed_current_records:
        completed_current_records = completed_deliverable_records(current_records[:1])
    if completed_current_records:
        render_completed_deliverables(
            completed_current_records,
            key_prefix="create_complete",
            heading="### ✅ Latest completed reel",
        )

# Tab 2: Reel library and job history
with tabs[1]:
    st.markdown("<div class='widget-title'>🎞️ MY VIDEOS</div>", unsafe_allow_html=True)
    st.caption("Preview completed videos, download deliverables and keep an eye on every render in one place.")

    try:
        try:
            job_store = JobStore(config.OUTPUT_DIR)
        except OSError:
            raise Exception("JobStore access failed")
        manager = get_job_manager(config.JOB_WORKER_MODE)
        recent_jobs = job_store.list_jobs(limit=15)
        completed_count = sum(record.get("status") == "succeeded" for record in recent_jobs)
        active_count = sum(record.get("status") in {"queued", "running"} for record in recent_jobs)
        metric_one, metric_two, metric_three = st.columns(3)
        metric_one.metric("Recent jobs", len(recent_jobs))
        metric_two.metric("Ready to publish", completed_count)
        metric_three.metric("Currently rendering", active_count)

        if manager.mode == "process" and st.button("Recover queued process jobs"):
            recovered = manager.recover_queued(config.OUTPUT_DIR)
            st.success(f"Started {recovered} recoverable queued job(s).")
            st.rerun()
        with st.expander("History maintenance", expanded=False):
            st.caption("This removes old job records and event logs only. Your exported videos and SEO files stay untouched.")
            retention_days = st.number_input("Keep terminal job history for days", min_value=1, max_value=3650, value=30, step=1)
            if st.button("Purge old history records"):
                removed = job_store.cleanup_history(int(retention_days))
                st.success(f"Removed {removed} terminal history record(s). Deliverable media files were not changed.")

        if recent_jobs:
            st.markdown("#### Render queue & recent activity")
            for record in recent_jobs:
                job_id = record["job_id"]
                status = record["status"]
                with st.container(border=True):
                    title_col, progress_col, action_col = st.columns([3, 2, 1])
                    title_col.markdown(f"**{record.get('topic') or 'Untitled reel'}**")
                    title_col.caption(f"{_status_badge(status)} · Job {job_id[-8:]}")
                    progress = int(record.get("progress") or 0)
                    if status in {"queued", "running"}:
                        progress_col.progress(progress, text=f"{_workflow_label(record.get('current_stage'))} · {progress}%")
                    elif status == "succeeded":
                        progress_col.success("Complete · MP4 and SEO package ready")
                    else:
                        progress_col.caption(f"{_workflow_label(record.get('current_stage'))} · Needs attention")
                    if status in {"queued", "running"}:
                        if action_col.button("Cancel", key=f"cancel_{job_id}"):
                            manager.cancel(config.OUTPUT_DIR, job_id)
                            st.rerun()
                    elif status in {"failed", "cancelled"}:
                        if action_col.button("Retry", key=f"retry_{job_id}"):
                            retry_id = manager.retry(config.OUTPUT_DIR, config, job_id)
                            if retry_id:
                                st.success(f"Retry queued: {retry_id}")
                                st.rerun()
                            else:
                                st.error("This job cannot be retried because its original local request details are unavailable.")
                    else:
                        action_col.caption("Complete")
                    with st.expander("Technical event log", expanded=False):
                        events = job_store.list_events(job_id, limit=25)
                        if events:
                            st.dataframe(events, width="stretch", hide_index=True)
                        else:
                            st.caption("No detailed events were recorded for this job.")
        else:
            st.info("No render history yet. Create your first reel from the **Create Reel** tab and its live progress will appear here.")
    except Exception:
        st.warning("Render history is temporarily unavailable. Your output files can still be previewed below; refresh the page in a moment to retry.")
    
    completed_records = completed_deliverable_records(recent_jobs if 'recent_jobs' in locals() else [])
    if completed_records:
        render_completed_deliverables(
            completed_records,
            key_prefix="library_complete",
            heading="#### Recent completed renders",
        )

    # Scan directory for older exports that predate the durable job history.
    mp4_files = glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4"))
    mp4_files.sort(key=os.path.getmtime, reverse=True)
    recorded_videos = {record["output_video_path"] for record in completed_records}
    mp4_files = [path for path in mp4_files if path not in recorded_videos]
    
    if not mp4_files:
        st.markdown("### Your reel library is ready")
        st.info("No completed videos yet. Create a reel, follow its render status, then return here to preview and download the final MP4 plus SEO package.")
    else:
        st.markdown("#### Earlier exported videos")
        st.caption(f"{len(mp4_files)} older reel(s). Select one to preview and export without loading the entire library at once.")
        selected_video = st.selectbox(
            "Choose a reel to preview",
            options=mp4_files,
            format_func=lambda path: os.path.basename(path).rsplit(".", 1)[0],
        )
        file_basename = os.path.basename(selected_video)
        file_title = file_basename.rsplit(".", 1)[0]
        txt_path = os.path.join(config.OUTPUT_DIR, f"{file_title}.txt")
        modified = datetime.fromtimestamp(os.path.getmtime(selected_video)).strftime("%d %b %Y · %I:%M %p")
        with st.container(border=True):
            st.markdown(f"<div class='gallery-card-title'>🎬 {file_title}</div>", unsafe_allow_html=True)
            try:
                file_size = os.path.getsize(selected_video)
            except FileNotFoundError:
                file_size = 0
            st.markdown(
                f"<div class='gallery-meta'>Exported {modified} · {_format_file_size(file_size)} · Vertical reel deliverable</div>",
                unsafe_allow_html=True,
            )
            col_g_vid, col_g_txt = st.columns([1.15, 0.85])
            with col_g_vid:
                st.video(selected_video)
                st.download_button(
                    "⬇️ Download MP4",
                    data=open(selected_video, "rb"),
                    file_name=file_basename,
                    mime="video/mp4",
                    key=f"download_video_{file_title}",
                    width="stretch",
                )
            with col_g_txt:
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as seo_file:
                        seo_content = seo_file.read()
                    st.text_area("SEO package", value=seo_content, height=260, key=f"txt_{file_title}")
                    st.download_button(
                        "⬇️ Download SEO package",
                        data=seo_content,
                        file_name=os.path.basename(txt_path),
                        mime="text/plain",
                        key=f"download_seo_{file_title}",
                        width="stretch",
                    )
                else:
                    st.info("The MP4 is ready. No SEO package was found for this older export.")

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
            4. **\"Create API Key\"** press karein aur key ko local `.env` ya hosting platform ke managed secrets mein save karein.
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
            3. **\"Create new secret key\"** click karein aur key ko local `.env` ya hosting platform ke managed secrets mein save karein.
            """)

        # 5. ElevenLabs API Key
        with st.expander("🗣️ 5. ElevenLabs API Key (Premium Realistic Voices)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Premium ultra-realistic AI voice synthesis generate karne ke liye use hota hai (supports Urdu and English).
            
            **How to Get (Banane ka tareeqa):**
            1. Visit [ElevenLabs.io](https://elevenlabs.io/).
            2. Sign up or log into your account.
            3. Go to **Profile Settings** (bottom left avatar menu) and select **"Profile + API Keys"**.
            4. Copy your **API Key** and save it in local `.env` or your hosting platform's managed secrets.
            """)

        # 6. Pexels Stock Media API Key
        with st.expander("📹 6. Pexels API Key (Free High-Quality Footage)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Script ke flow ke mutabiq free 9:16 vertical stock videos aur images search and download karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [Pexels Developer Portal](https://www.pexels.com/api/).
            2. Sign up / login kar ke apna developer account settings page open karein.
            3. **\"Your API Key\"** section se key copy karke local `.env` ya hosting platform ke managed secrets mein save karein.
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
            **Working (Kaam):** Aap is option main kisi bhi niche ka topic likhte hain (e.g. *study tips*, *fitness*, *travel*, *technology*), aur system AI model ke through automatic voice, script, clips matching aur final compilation process handle karta hai.
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

        with st.expander("⚙️ Mode 7: Run Fallback Demo (Universal Creator Demo)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Ye ek neutral creator demo run karta hai jisse aap pipeline ka output check kar sakte hain. Is mode mein bhi configured media sources aur local assets ki availability result par asar dalti hai.
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
            * `mystery`: suspenseful, dramatic storytelling.
            * `epic`: bold, high-energy storytelling.
            * `sad`: emotional or reflective storytelling.
            * `ancient`: traditional or retro acoustic instruments.
            """)

        with st.expander("🎥 Media Type Preference Selector", expanded=False):
            st.markdown("""
            **Description:** Visual footage filtering preference:
            * `Mixed (Videos + Images)`: videos first, image falls back.
            * `Videos Only`: downloads only vertical video stock loops.
            * `Images Only`: loads static vintage/retro pictures, and compiles them using a smooth dynamic Ken Burns panning-and-zoom motion filter graph (cinematic vertical scale zoom!).
            """)

