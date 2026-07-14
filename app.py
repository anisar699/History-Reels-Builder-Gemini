import os
import sys
import glob
import random
import contextlib
import importlib
import streamlit as st

# Force reload of history_reels modules to prevent Streamlit caching errors
for mod in list(sys.modules.keys()):
    if mod.startswith("history_reels"):
        try:
            importlib.reload(sys.modules[mod])
        except Exception:
            pass

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
""", unsafe_allow_html=True)

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
        options=["gemini", "openai", "groq", "ollama", "openrouter"],
        index=0,
        help="Select the AI model provider to write scripts and create SEO content."
    )
    
    if provider == "ollama":
        st.info("💡 Local Mode: Uses 'qwen2.5:3b' model. Ensure Ollama service is running.")
        
    vibe_selection = st.selectbox(
        "Background Music Vibe",
        options=["random", "mystery", "epic", "sad", "ancient"],
        index=0,
        help="Custom soundtrack feel. 'random' will choose a random vibe."
    )
    
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
    
    st.markdown("---")
    st.markdown("<div class='widget-title'>🔑 API KEYS CONFIGURATION</div>", unsafe_allow_html=True)
    
    new_gemini = st.text_input("Gemini API Key", value=config.GEMINI_API_KEY or "", type="password")
    new_openai = st.text_input("OpenAI API Key", value=config.OPENAI_API_KEY or "", type="password")
    new_groq = st.text_input("Groq API Key", value=config.GROQ_API_KEY or "", type="password")
    new_openrouter = st.text_input("OpenRouter API Key", value=getattr(config, "OPENROUTER_API_KEY", "") or "", type="password")
    new_pexels = st.text_input("Pexels API Key", value=config.PEXELS_API_KEY or "", type="password")
    new_pixabay = st.text_input("Pixabay API Key", value=config.PIXABAY_API_KEY or "", type="password")
    
    if st.button("Save & Reload Keys 💾", use_container_width=True):
        # Update local .env file in the workspace root
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        env_content = f"""PEXELS_API_KEY={new_pexels.strip()}
PIXABAY_API_KEY={new_pixabay.strip()}
OPENAI_API_KEY={new_openai.strip()}
GEMINI_API_KEY={new_gemini.strip()}
GROQ_API_KEY={new_groq.strip()}
OPENROUTER_API_KEY={new_openrouter.strip()}
"""
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
            
        # Update config singleton attributes instantly
        config.GEMINI_API_KEY = new_gemini.strip()
        config.OPENAI_API_KEY = new_openai.strip()
        config.GROQ_API_KEY = new_groq.strip()
        config.OPENROUTER_API_KEY = new_openrouter.strip()
        config.PEXELS_API_KEY = new_pexels.strip()
        config.PIXABAY_API_KEY = new_pixabay.strip()
        
        # Update os.environ
        os.environ["GEMINI_API_KEY"] = new_gemini.strip()
        os.environ["OPENAI_API_KEY"] = new_openai.strip()
        os.environ["GROQ_API_KEY"] = new_groq.strip()
        os.environ["OPENROUTER_API_KEY"] = new_openrouter.strip()
        os.environ["PEXELS_API_KEY"] = new_pexels.strip()
        os.environ["PIXABAY_API_KEY"] = new_pixabay.strip()
        
        st.toast("API Keys saved to .env & reloaded!", icon="💾")
        st.rerun()

tabs = st.tabs(["🚀 Generate Videos", "📂 View Gallery Output", "ℹ️ Tool Help/Guide"])

# Tab 1: Video Generator
with tabs[0]:
    col_input, col_action = st.columns([2, 1])
    
    with col_input:
        st.markdown("<div class='widget-title'>📝 STEP 1: DEFINE TOPIC(S)</div>", unsafe_allow_html=True)
        
        mode = st.radio(
            "Generation Mode",
            options=["Single Video", "Batch Videos (Multiple)", "Automated News Scraping (Live RSS/Web)", "CSV/Excel Batch Upload", "Manual AI Script (Paste & Struct)", "Manual Script Input (Free & Custom)", "Run Fallback Demo (Baghdad Battery)"],
            index=0
        )
        
        topic_input = ""
        batch_input = ""
        news_url = ""
        raw_script_input = ""
        manual_script_data = None
        
        if mode == "Single Video":
            topic_input = st.text_input("Enter Video Topic", placeholder="e.g. Titanic Tragedy, Taj Mahal, Roman Empire")
        elif mode == "Batch Videos (Multiple)":
            batch_input = st.text_area(
                "Enter Multiple Topics (Comma Separated)",
                placeholder="e.g. Titanic, Taj Mahal, Giza Pyramids, Cleopatra",
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
        elif mode == "Automated News Scraping (Live RSS/Web)":
            st.markdown("### 📰 Automated News Scraping")
            news_url = st.text_input("Enter RSS Feed or Article Web Page URL", value="https://feeds.bbci.co.uk/urdu/rss.xml")
            
            # Setup session state for news articles
            if "fetched_articles" not in st.session_state:
                st.session_state["fetched_articles"] = []
                st.session_state["feed_url_cache"] = ""
                
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
        elif mode == "Manual AI Script (Paste & Struct)":
            raw_script_input = st.text_area(
                "Paste Your Raw Script (Urdu, English, or Roman Urdu)",
                placeholder="Paste your raw script text here. The selected AI provider will automatically split it into 4 slides, format Urdu captions, match Pexels/Pixabay/Google queries, and build the video.",
                height=250
            )
        elif mode == "Manual Script Input (Free & Custom)":
            st.markdown("### 📝 Enter Custom Script Details")
            title = st.text_input("Video Title", value="Ancient Treasures")
            year = st.text_input("Historical Era / Year", value="1000 CE")
            music_vibe = st.selectbox("Soundtrack Vibe", options=["mystery", "epic", "sad", "ancient"], index=0)
            
            st.markdown("#### Subtitles (Urdu Nastaliq - Bold words with **double asterisks**)")
            cap1 = st.text_input("Slide 1 Caption", value="کِیا آپ جانتے ہیں کہ **قدیم خزانہ** کہاں ملا؟")
            cap2 = st.text_input("Slide 2 Caption", value="صدیوں پرانی **پراسرار مٹی** کے نیچے چھپا تھا۔")
            cap3 = st.text_input("Slide 3 Caption", value="ماہرین نے آخرکار اسے **کھوج نکالا**!")
            cap4 = st.text_input("Slide 4 Caption", value="کمنٹس میں اپنی **رائے** کا اظہار کریں۔")
            
            st.markdown("#### Spoken Speech Narration (Urdu Speech Text)")
            narr1 = st.text_input("Slide 1 Speech", value="کیا آپ جانتے ہیں کہ قدیم خزانہ کہاں ملا؟")
            narr2 = st.text_input("Slide 2 Speech", value="صدیوں پرانی پراسرار مٹی کے نیچے چھپا تھا۔")
            narr3 = st.text_input("Slide 3 Speech", value="ماہرین نے آخرکار اسے کھوج نکالا!")
            narr4 = st.text_input("Slide 4 Speech", value="کمنٹس میں اپنی رائے کا اظہار کریں۔")
            
            st.markdown("#### Media Search Queries (8 queries, comma separated)")
            queries_str = st.text_area(
                "Image/Video Search Queries", 
                value="ancient chest, gold coins, mysterious cave, digging dirt, archaeologists, treasure map, golden crown, glowing gold"
            )
            
            # Parse queries list
            queries_list = [q.strip() for q in queries_str.split(",") if q.strip()]
            while len(queries_list) < 8:
                queries_list.append("treasure")
            queries_list = queries_list[:8]
            
            # Assemble custom script dictionary structure
            manual_script_data = {
                "title": title.strip(),
                "year": year.strip(),
                "bg_music_vibe": music_vibe,
                "caption_text_1": cap1.strip(),
                "caption_text_2": cap2.strip(),
                "caption_text_3": cap3.strip(),
                "caption_text_4": cap4.strip(),
                "narration_text_1": narr1.strip(),
                "narration_text_2": narr2.strip(),
                "narration_text_3": narr3.strip(),
                "narration_text_4": narr4.strip(),
                "queries": queries_list,
                "seo_title": f"{title.strip()} — Secrets of the Past 🏺✨",
                "seo_description": f"{title.strip()} ({year.strip()}) custom script generated manually.\n\nUrdu Script:\n{cap1} {cap2}\n{cap3} {cap4}",
                "seo_hashtags": "#History #CustomStory #UrduNarratives #AncientTech",
                "seo_short_caption": f"Secrets of {title.strip()} revealed! #History #Urdu"
            }
            
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
        elif mode == "CSV/Excel Batch Upload":
            if "uploaded_df" not in st.session_state or st.session_state["uploaded_df"] is None or st.session_state["uploaded_df"].empty:
                st.error("Error: Please upload a valid CSV or Excel file first.")
            else:
                import pandas as pd
                df = st.session_state["uploaded_df"]
                cols = [c.lower() for c in df.columns]
                has_script_cols = ("title" in cols and "caption_text_1" in cols and "narration_text_1" in cols)
                
                for _, row in df.iterrows():
                    row_dict = row.to_dict()
                    if has_script_cols:
                        queries_val = row_dict.get("queries", "")
                        if pd.isna(queries_val):
                            queries_val = ""
                        queries_list = [q.strip() for q in str(queries_val).split(",") if q.strip()]
                        while len(queries_list) < 8:
                            queries_list.append("history")
                        queries_list = queries_list[:8]
                        
                        script_data = {
                            "title": str(row_dict.get("title", "")).strip(),
                            "year": str(row_dict.get("year", "Unknown")).strip(),
                            "bg_music_vibe": str(row_dict.get("bg_music_vibe", "mystery")).strip(),
                            "caption_text_1": str(row_dict.get("caption_text_1", "")).strip(),
                            "caption_text_2": str(row_dict.get("caption_text_2", "")).strip(),
                            "caption_text_3": str(row_dict.get("caption_text_3", "")).strip(),
                            "caption_text_4": str(row_dict.get("caption_text_4", "")).strip(),
                            "narration_text_1": str(row_dict.get("narration_text_1", "")).strip(),
                            "narration_text_2": str(row_dict.get("narration_text_2", "")).strip(),
                            "narration_text_3": str(row_dict.get("narration_text_3", "")).strip(),
                            "narration_text_4": str(row_dict.get("narration_text_4", "")).strip(),
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
                                topic_col = c
                                break
                        if not topic_col:
                            topic_col = df.columns[0]
                        topic_val = str(row_dict[topic_col]).strip()
                        if topic_val and not pd.isna(row_dict[topic_col]):
                            topics_list.append({"type": "topic", "data": topic_val, "title": topic_val})
        elif mode == "Automated News Scraping (Live RSS/Web)":
            if st.session_state.get("selected_article_data"):
                art = st.session_state["selected_article_data"]
                topics_list = [{"type": "rss", "link": art["link"], "desc": art["description"], "title": art["title"]}]
            else:
                if not news_url.strip():
                    st.error("Error: Please provide a news RSS feed or web page URL.")
                else:
                    topics_list = [{"type": "direct", "link": news_url.strip(), "desc": "", "title": "Scraped Article"}]
        elif mode == "Manual AI Script (Paste & Struct)":
            if not raw_script_input.strip():
                st.error("Error: Please paste your raw script.")
            else:
                topics_list = [raw_script_input.strip()]
        elif mode == "Manual Script Input (Free & Custom)":
            topics_list = [manual_script_data["title"]]
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
                        
                    t_name = t
                    if isinstance(t, dict):
                        t_name = t.get("title", "Scraped Article")
                        
                    if t:
                        if mode == "Manual AI Script (Paste & Struct)":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Structuring Raw Script Input...")
                        elif mode == "Automated News Scraping (Live RSS/Web)":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Scraping and Structuring from '{t_name}'...")
                        elif mode == "CSV/Excel Batch Upload":
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Processing uploaded batch row '{t_name}'...")
                        else:
                            print(f"\n[UI Run {idx}/{len(topics_list)}] Initiating Topic: '{t_name}'")
                    else:
                        print(f"\n[UI Run] Initiating Fallback Mode...")
                        
                    if mode == "Manual Script Input (Free & Custom)":
                        success = generate_video_for_topic(None, provider=provider, manual_script_data=manual_script_data)
                    elif mode == "Manual AI Script (Paste & Struct)":
                        success = generate_video_for_topic(t, provider=provider, is_raw_script=True)
                    elif mode == "Automated News Scraping (Live RSS/Web)":
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
                    
                    if success:
                        st.balloons()
                        st.success(f"Successfully generated Video for Topic: '{t_name or 'Baghdad Battery'}'!")
                        
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

        # 5. Pexels Stock Media API Key
        with st.expander("📹 5. Pexels API Key (Free High-Quality Footage)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Script ke flow ke mutabiq free 9:16 vertical stock videos aur images search and download karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [Pexels Developer Portal](https://www.pexels.com/api/).
            2. Sign up / login kar ke apna developer account settings page open karein.
            3. **\"Your API Key\"** section main request submission (simple form entry) karte hi instant aur free API key show ho jayegi, use copy kar ke dashboard sidebar main paste kar dein.
            """)

        # 6. Pixabay Stock Media API Key
        with st.expander("🖼️ 6. Pixabay API Key (Backup Stock Media)", expanded=False):
            st.markdown("""
            **Working (Kaam):** Pexels ke limits lagne par backup images aur videos download karne ke liye use hota hai.
            
            **How to Get (Banane ka tareeqa):**
            1. Go to [Pixabay API Documentation](https://pixabay.com/api/docs/).
            2. Apne Pixabay account main login / register karein.
            3. Documentation page ko refresh/scroll down karein, aur **\"Parameters\"** key description section main check karein, aapka personal **`key`** parameter block visible ho jayega (e.g. `key: 12345678-abcdef...`).
            4. Wo key copy kar ke sidebar main paste kar dein.
            """)

        # 7. Local Offline Ollama (Offline Mode)
        with st.expander("💻 7. Local Offline Ollama Setup (Offline & Free)", expanded=False):
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
        st.write("Apni reels ki content priority aur styling customize karne ke liye settings panels configure karein:")

        with st.expander("🤖 AI Content Provider Selector", expanded=True):
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

