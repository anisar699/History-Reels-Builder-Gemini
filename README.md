# Universal Content Engine — Premium AI Shorts Auto-Pilot Dashboard 🎥✨

An advanced, feature-rich auto-pilot compilation pipeline designed for generating premium vertical short documentaries (9:16 reels/TikToks/Shorts). This system integrates custom Urdu voiceover narration (via Edge-TTS & ElevenLabs), authentic right-to-left Nastaliq subtitles, dynamic background music mixing, and keyless search/scrapers to build ready-to-publish history assets in seconds.

Now upgraded to a **Fully Dynamic System** supporting videos up to 10 minutes long, with a beautiful organized Streamlit visual control dashboard and 7+ flexible script structuring methods to prevent API quota bottlenecks.

---

## 🌟 What's New in V2.0 (The Universal Update)

* **Dynamic Scripts & Pacing:** No more 4-slide limits! Generate 3 to 10-minute long videos effortlessly. The AI mathematically calculates slides, subtitles, and queries based on your target duration.
* **Categorized UI Dashboard:** Generator settings are cleanly organized into 5 expandable accordions (AI Models, Audio & Voice, Visuals & Transitions, Branding & Overlays, API Keys).
* **Cinematic Visual Effects:** Added support for Color Grading LUTs (Cyberpunk, Vintage, Horror), Cinematic Film Grain, and high-energy Camera Shake transitions.
* **Pro Audio Mastering:** Smart Audio Ducking (music lowers when AI speaks), Voice EQ Compression, and dynamic Ambient Soundscapes (Rain, Wind, Rumble).
* **Branding Options:** Burn translucent Custom Brand Logos/Watermarks, attach Intro/Outro Bumper clips automatically, and display an animated Progress Bar.
* **Advanced Media Sources:** Pulls ultra-HD footage from Pexels, Pixabay, Storyblocks (Premium), NASA, Internet Archive, Wikimedia, Unsplash, Google Images, and Pinterest.

---

## Key Features 🚀

### 1. 🖥️ Interactive Streamlit Dashboard
* **Visual Progress Console:** Watch stock media search, voice rendering, and FFmpeg video merging logs live on screen.
* **API Keys Manager:** Configure and reload keys for 10+ providers instantly from the UI.
* **Output Gallery:** Browse, play, and copy the corresponding SEO text packages (optimized description, tags, hashtags) of compiled reels directly from the dashboard.

### 2. 📝 7 Flexible Generation Methods
* **Single Video Mode:** Provide a simple historical topic, and the system does everything.
* **Batch Videos Mode:** Input comma-separated topics list to generate multiple reels sequentially.
* **Automated News Scraping:** Scrape XML RSS feeds (e.g. BBC Urdu, Dawn) or direct web article links. The system cleans HTML paragraphs and structures the video from live content.
* **CSV/Excel Batch Upload:** Upload spreadsheets (.csv or .xlsx) to bulk-compile scripts. Handles dynamically infinite rows for long videos.
* **Manual AI Script (Paste & Struct):** Paste a raw narrative story paragraph, and the AI automatically splits it into dynamically timed slides.
* **Manual Script Input (100% Free):** Directly write subtitles, voiceover lines, music vibe, and search queries manually via multi-line text areas. Bypasses LLMs entirely!
* **Fallback Mode:** Triggers a built-in pre-written hardcoded script if APIs completely fail.

### 3. 🎥 Smart Media Priority & Ken Burns Zoompan
* Select preference: **Mixed (Videos + Images)**, **Videos Only**, or **Images Only**.
* If **Images Only** or fallback images are used, the engine applies a cinematic vertical Ken Burns crop-scale-and-pan filter graph (scale=1440:2560 and custom FFmpeg zoompan) to create premium motion animations from static retro history pictures.

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
* Create the `history videos/bg_music` and `fonts` asset folders.
* Create a **"Start Reels Builder"** shortcut right on your Desktop!
* Launch the Dashboard automatically in your web browser!

---

## Running the Dashboard 💻

Double-click the **Gemini Reels Dashboard.lnk** shortcut on your desktop, or run the following command in the project directory:
`powershell
streamlit run app.py
`

### Command Line Interface (CLI)
You can also trigger batch jobs directly via the terminal:
`powershell
# Generate via Gemini
python build_reel.py --topic "Taj Mahal History" --provider gemini

# Generate offline via local Ollama
python build_reel.py --topic "Roman Empire" --provider ollama

# Generate from Web Scraper
python build_reel.py --news-url "https://feeds.bbci.co.uk/urdu/rss.xml" --provider groq

# Generate from CSV file
python build_reel.py --csv "batch_scripts.csv" --provider openrouter
`

---

## ℹ️ Configuration & API Help
Open the **Tool Help/Guide** tab inside the running Streamlit dashboard for a detailed Hinglish/Roman Urdu walkthrough on how to generate free API keys for Pexels, Pixabay, Gemini, Groq, OpenRouter, and setting up local offline **Ollama** models.