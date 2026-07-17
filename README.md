# Universal Content Engine — Premium AI Shorts Auto-Pilot Dashboard 🎥✨

An advanced, feature-rich auto-pilot compilation pipeline designed for generating premium vertical short-form videos (9:16 reels/TikToks/Shorts) for any niche. This system integrates multilingual voiceover narration (via Edge-TTS & ElevenLabs), language-aware subtitles, dynamic background music mixing, and media search/scrapers to build ready-to-publish reels.

Now upgraded to a **Fully Dynamic System** supporting videos up to 10 minutes long, with a beautiful organized Streamlit visual control dashboard and 7+ flexible script structuring methods to prevent API quota bottlenecks.

---

## 🌟 What's New in V2.0 (The Universal Update)

* **Dynamic Scripts & Pacing:** No more 4-slide limits! Generate 3 to 10-minute long videos effortlessly. The AI mathematically calculates slides, subtitles, and queries based on your target duration.
* **Creative Direction Controls:** Set a niche, content language, tone, target platform, and visual style for every AI-generated reel. These choices are stored with each queued job and reused on retries.
* **Language-Aware Captions:** Urdu, English, Hindi, Arabic, and Roman Urdu each use an appropriate caption font. You can also upload a `.ttf` or `.otf` font; the render pipeline preserves and burns that exact uploaded font.
* **Local-First Music + Media Quality:** Every music vibe uses a reusable original FFmpeg-generated local track instead of a fragile download URL. A balanced/high-quality source filter rejects undersized video candidates before download.
* **Reliable Render Queue:** Every job has a durable local status, stage, event log, retry action, and cancellation checkpoints. Interrupted queued jobs become clearly retryable instead of remaining stuck forever.
* **Verified Deliverables:** A no-network matrix covers Urdu, English, Hindi, Arabic, Roman Urdu, vertical/landscape/square layouts, music modes, and media-quality profiles. Every completed render is also checked with FFprobe before it is marked ready.
* **Categorized UI Dashboard:** Generator settings are cleanly organized into 5 expandable accordions (AI Models, Audio & Voice, Visuals & Transitions, Branding & Overlays, API Keys).
* **Cinematic Visual Effects:** Added support for Color Grading LUTs (Cyberpunk, Vintage, Horror), Cinematic Film Grain, and high-energy Camera Shake transitions.
* **Pro Audio Mastering:** Smart Audio Ducking (music lowers when AI speaks), Voice EQ Compression, and dynamic Ambient Soundscapes (Rain, Wind, Rumble).
* **Branding Options:** Burn translucent Custom Brand Logos/Watermarks, attach Intro/Outro Bumper clips automatically, and display an animated Progress Bar.
* **Custom Export Directory:** Choose exactly where your final MP4s and SEO text files are saved on your PC right from the UI (using a native file browser).
* **Rock-Solid Stability (Multi-Agent Patched):** Massive architecture improvements ensuring flawless partial-download handling, graceful JSON fallbacks, precise FFmpeg text escaping, and bulletproof rendering reliability.
* **Approved Media Sources:** Uses the selected Pexels, Pixabay, Google/Bing image, and Wikimedia image providers. Low-quality candidates are rejected before download, and the renderer reuses valid assets rather than creating blank frames when a subset of media requests fails.

---

## Key Features 🚀

### 1. 🖥️ Interactive Streamlit Dashboard
* **Visual Progress Console:** Watch stock media search, voice rendering, and FFmpeg video merging logs live on screen.
* **Completion Cards:** When a render finishes, the Create Reel page immediately shows the MP4 preview, download button, full SEO package, and SEO download. The same verified deliverable appears separately in **My Videos**.
* **Secure API Key Status:** See which providers are configured without displaying secret values. Persistent keys stay in `.env` or a managed hosting secret store.
* **Output Gallery:** Browse recent completed renders without misleading progress bars, then access older exports separately. Each video includes its corresponding SEO text package (optimized description, tags, and hashtags).

### 2. 📝 7 Flexible Generation Methods
* **Single Video Mode:** Provide a topic from any niche, and the system does everything.
* **Batch Videos Mode:** Input comma-separated topics list to generate multiple reels sequentially.
* **Automated News Scraping:** Scrape XML RSS feeds (e.g. BBC Urdu, Dawn) or direct web article links. The system cleans HTML paragraphs and structures the video from live content.
* **CSV/Excel Batch Upload:** Upload validated spreadsheets (`.csv` or `.xlsx`) to bulk-compile up to 1,000 rows per dashboard batch.
* **Manual AI Script (Paste & Struct):** Paste a raw narrative story paragraph, and the AI automatically splits it into dynamically timed slides.
* **Manual Script Input (100% Free):** Directly write subtitles, voiceover lines, music vibe, and search queries manually via multi-line text areas. Bypasses LLMs entirely!
* **Fallback Mode:** Triggers a built-in pre-written hardcoded script if APIs completely fail.

### 3. 🎥 Smart Media Priority & Ken Burns Zoompan
* Select preference: **Mixed (Videos + Images)**, **Videos Only**, or **Images Only**.
* If **Images Only** or fallback images are used, the engine applies a cinematic vertical Ken Burns crop-scale-and-pan filter graph (scale=1440:2560 and custom FFmpeg zoompan) to create premium motion animations from static topical images.

---

## Setup & Installation 🛠️ (1-Click Auto Installer)

We have created an automatic setup script for beginners! You do not need to type long commands or create folders manually.

### Step 1: Download Python & Git
1. **Download Python:** Go to [python.org](https://www.python.org/downloads/) and install it. 
   ⚠️ **CRITICAL:** Check the box **"Add Python to PATH"** at the bottom before clicking Install!
2. **Download Git:** Go to [git-scm.com](https://git-scm.com/downloads) and install Git for Windows (just keep clicking Next).

### Step 2: Download the Project
Open a normal **PowerShell** window and type:
```powershell
git clone https://github.com/anisar699/History-Reels-Builder-Gemini.git
cd History-Reels-Builder-Gemini
```

### Step 3: Run the Auto-Installer 🚀
While inside the `History-Reels-Builder-Gemini` folder, simply type:
```powershell
python install.py
```
**That's it! The script will automatically:**
* Check and install FFmpeg (Video Engine) for you.
* Download and install all required AI Python libraries.
* Create the configured output, background-music, and font asset folders.
* Create a **"Start Reels Builder"** shortcut right on your Desktop!
* Launch the Dashboard automatically in your web browser!

---

## Running the Dashboard 💻

Double-click the **Gemini Reels Dashboard.lnk** shortcut on your desktop, or run the following command in the project directory:
```powershell
streamlit run app.py
```

### Command Line Interface (CLI)
You can also trigger batch jobs directly via the terminal:
```powershell
# Generate via Gemini
python build_reel.py --topic "5 productivity tips for students" --provider gemini

# Generate offline via local Ollama
python build_reel.py --topic "Beginner home workout" --provider ollama

# Generate from Web Scraper
python build_reel.py --news-url "https://feeds.bbci.co.uk/urdu/rss.xml" --provider groq

# Generate from CSV file
python build_reel.py --csv "batch_scripts.csv" --provider openrouter
```

### Local verification

Run the full local regression suite before publishing changes:

```powershell
python -B -m unittest discover -s tests -v
```

The test suite covers queue dispatch and retry behavior, safe input handling, captions/fonts, local music, media fallbacks, post-render verification, and completed-deliverable paths.

---

## ℹ️ Configuration & API Help
Open the **Tool Help/Guide** tab inside the running Streamlit dashboard for a detailed Hinglish/Roman Urdu walkthrough on how to generate free API keys for Pexels, Pixabay, Gemini, Groq, OpenRouter, and setting up local offline **Ollama** models.

For deployment and environment details, see [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md), [docs/QUALITY_CHECKS.md](docs/QUALITY_CHECKS.md), and [docs/VERIFICATION.md](docs/VERIFICATION.md).
