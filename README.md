# History Reels Builder 🎥✨

An AI-powered automated video compiler designed for generating historical, educational, and mysterious vertical shorts (reels/TikToks) with Urdu script narration, authentic Nastaliq subtitles, and relevant stock video transitions.

---

## Features 🚀
- **1-Click AI Reel Generator:** Just provide a topic (e.g. `--topic "Pyramids of Giza"`), and the script automatically writes the Urdu voiceover, drafts slide captions, generates matching video queries, and builds the reel.
- **Urdu Nastaliq Subtitles:** Uses `NotoNastaliqUrdu` font to draw beautiful, authentic, right-to-left Urdu subtitles.
- **Natural Voiceover (Edge-TTS):** Generates voiceovers using standard Pakistani Urdu narrator (`ur-PK-AsadNeural`) with custom diacritics to ensure perfect pronunciation of tricky Urdu words (like `کِیا`).
- **Dynamic Stock Footage:** Searches Pexels and Pixabay APIs automatically to download high-resolution portrait video clips matching each sentence.
- **Seamless Audio Mixing:** Crossfades video clips smoothly and merges background music loops with the voiceover track.

---

## Setup & Prerequisites 🛠️

### 1. Install System Tools
Make sure **Python 3.10+** and **FFmpeg** are installed on your computer and added to your system's PATH.

On Windows, you can install FFmpeg via PowerShell:
```powershell
winget install Gyan.FFmpeg
```

### 2. Install Python Libraries
Run the following command to install all required dependencies:
```powershell
pip install pillow requests edge-tts
```

### 3. Setup Folders
Create the following directory structure in your user's **Pictures** folder:
```
Pictures/
└── history videos/
    ├── bg_music/    # Add your looping mystery/sad/epic tracks (e.g., mystery_1.mp3, mystery_2.mp3)
    └── fonts/       # Place the NotoNastaliqUrdu-Bold.ttf font here
```

---

## How to Run 💻

### Option A: Fully Automated AI Mode (Recommended)
Run the script and provide the topic using the `--topic` flag. The script will query OpenAI (using your API key) to write the script and download Pexels videos:
```powershell
python build_reel.py --topic "Pyramids of Giza"
```

### Option B: Interactive Mode
Run the script without arguments. It will prompt you in the console:
```powershell
python build_reel.py
# Prompt: Enter video topic (e.g. Pyramids of Giza):
```

The compiled video and corresponding SEO metadata package (title, description, tags) will be saved in your `Pictures/history videos/` folder.

---

## Customizing Configurations
At the top of `build_reel.py`, you can configure:
- **API Keys:** Add your Pexels, Pixabay, or OpenAI API keys.
- **Voices:** Change default voice (`ur-PK-AsadNeural` or other Edge-TTS voices).
- **Background Music Vibes:** Map vibes (`mystery`, `epic`, `sad`, `ancient`) to matching track indexes.
