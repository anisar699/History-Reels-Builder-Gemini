import os
import sys
import glob
import random
import contextlib
import streamlit as st

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from history_reels import config
from history_reels.cli import generate_video_for_topic

# Streamlit Page Config
st.set_page_config(
    page_title="History Reels Auto-Pilot UI",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark theme premium styling
st.markdown("""
<style>
    /* Styling for Streamlit App */
    .stApp {
        background-color: #0b0c10;
        color: #c5c6c7;
    }
    .main-title {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-size: 3rem !important;
        font-weight: 800;
        background: linear-gradient(45deg, #00d2ff, #3a7bd5, #ffd700);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        text-align: center;
        font-size: 1.1rem;
        color: #85858f;
        margin-bottom: 2rem;
    }
    .premium-card {
        background-color: #1f2833;
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid #45f3ff;
        margin-bottom: 1.5rem;
    }
    .widget-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #66fcf1;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_stdio=True)

# Context manager to redirect stdout/stderr to a Streamlit code block
@contextlib.contextmanager
def redirect_stdout_to_streamlit(placeholder):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    class WebConsoleWriter:
        def __init__(self):
            self.content = ""
        def write(self, string):
            if string:
                self.content += string
                # Keep last 100 lines for the log output view
                lines = self.content.splitlines()[-100:]
                placeholder.code("\n".join(lines))
        def flush(self):
            pass
            
    writer = WebConsoleWriter()
    sys.stdout = writer
    sys.stderr = writer
    try:
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

# Main Layout
st.markdown("<h1 class='main-title'>🎥 HISTORY REELS AUTO-PILOT UI</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Generate premium short-form historical reels with Urdu script & AI Voiceovers in 1 click.</p>", unsafe_allow_html=True)

# Sidebar Control Panel
with st.sidebar:
    st.markdown("<div class='widget-title'>⚙️ GENERATOR SETTINGS</div>", unsafe_allow_html=True)
    
    provider = st.selectbox(
        "AI Content Provider",
        options=["gemini", "openai"],
        index=0,
        help="Select the AI model provider to write scripts and create SEO content."
    )
    
    vibe_selection = st.selectbox(
        "Background Music Vibe",
        options=["random", "mystery", "epic", "sad", "ancient"],
        index=0,
        help="Custom soundtrack feel. 'random' will choose a random vibe."
    )
    
    st.markdown("---")
    st.markdown("<div class='widget-title'>🔑 API KEYS (Loaded from .env)</div>", unsafe_allow_html=True)
    
    # Check key statuses
    keys = {
        "Gemini API Key": config.GEMINI_API_KEY,
        "OpenAI API Key": config.OPENAI_API_KEY,
        "Pexels API Key": config.PEXELS_API_KEY,
        "Pixabay API Key": config.PIXABAY_API_KEY
    }
    for key_name, val in keys.items():
        if val:
            st.success(f"✔️ {key_name} Active")
        else:
            st.error(f"❌ {key_name} Missing")

tabs = st.tabs(["🚀 Generate Videos", "📂 View Gallery Output"])

# Tab 1: Video Generator
with tabs[0]:
    col_input, col_action = st.columns([2, 1])
    
    with col_input:
        st.markdown("<div class='widget-title'>📝 STEP 1: DEFINE TOPIC(S)</div>", unsafe_allow_html=True)
        
        mode = st.radio(
            "Generation Mode",
            options=["Single Video", "Batch Videos (Multiple)", "Run Fallback Demo (Baghdad Battery)"],
            index=0
        )
        
        topic_input = ""
        batch_input = ""
        
        if mode == "Single Video":
            topic_input = st.text_input("Enter Video Topic", placeholder="e.g. Titanic Tragedy, Taj Mahal, Roman Empire")
        elif mode == "Batch Videos (Multiple)":
            batch_input = st.text_area(
                "Enter Multiple Topics (Comma Separated)",
                placeholder="e.g. Titanic, Taj Mahal, Giza Pyramids, Cleopatra",
                height=150
            )
            
    with col_action:
        st.markdown("<div class='widget-title'>🎬 STEP 2: BUILD IT</div>", unsafe_allow_html=True)
        st.write("Click below to start generating the video asset pipeline. This will query the AI model, download matched stock clips, mix voice/music, and compile the final reel.")
        
        start_btn = st.button("🚀 Start Video Pipeline", use_container_width=True)

    # Output Console & Log Blocks
    if start_btn:
        topics_list = []
        if mode == "Single Video":
            if not topic_input.strip():
                st.error("Error: Please provide a video topic.")
            else:
                topics_list = [topic_input.strip()]
        elif mode == "Batch Videos (Multiple)":
            if not batch_input.strip():
                st.error("Error: Please provide topics.")
            else:
                topics_list = [t.strip() for t in batch_input.split(",") if t.strip()]
        else:
            topics_list = [None] # Fallback mode triggers with None topic

        if topics_list:
            st.markdown("### 🖥️ Compilation Progress Console")
            console_placeholder = st.empty()
            
            # Setup logs placeholder
            with redirect_stdout_to_streamlit(console_placeholder):
                for idx, t in enumerate(topics_list, 1):
                    # Set custom vibe if selected (non-random)
                    if vibe_selection != "random":
                        config.BG_MUSIC_VIBE = vibe_selection
                        
                    if t:
                        print(f"\n[UI Run {idx}/{len(topics_list)}] Initiating Topic: '{t}'")
                    else:
                        print(f"\n[UI Run] Initiating Fallback Mode...")
                        
                    success = generate_video_for_topic(t, provider=provider)
                    
                    if success:
                        st.balloons()
                        st.success(f"Successfully generated Video for Topic: '{t or 'Baghdad Battery'}'!")
                        
                        # Find and display the generated video + SEO package in UI
                        clean_title = "".join(c for c in config.TOPIC_TITLE if c.isalnum() or c in (' ', '_', '-')).strip()
                        clean_year = "".join(c for c in config.TOPIC_YEAR if c.isalnum() or c in (' ', '_', '-')).strip()
                        output_name = f"{clean_title} {clean_year} Asad Voice"
                        
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
                        st.error(f"Failed compilation for Topic: '{t or 'Baghdad Battery'}'")

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
