# History Reels Builder

[![Quality checks](https://github.com/anisar699/History-Reels-Builder-Gemini/actions/workflows/quality.yml/badge.svg)](https://github.com/anisar699/History-Reels-Builder-Gemini/actions/workflows/quality.yml)

A local-first Streamlit dashboard and CLI for turning a topic, article, spreadsheet,
or manual script into a narrated short-form video. The pipeline combines AI-assisted
script generation, multilingual voiceover, relevant stock media, narration-synced
visual timing, captions, music, branding, FFmpeg rendering, and post-render QA.

The default output is a vertical `720x1280` MP4 suitable for Reels, TikTok, and
YouTube Shorts. Landscape and square presets are also available.

## Highlights

- **Multilingual content:** Urdu, English, Hindi, Arabic, and Roman Urdu.
- **Urdu/Arabic subtitle rendering:** language-aware fonts and shaped raster
  overlays are used where normal subtitle rendering is unreliable.
- **AI provider fallback:** Gemini → OpenAI → local Ollama → OpenRouter → Groq.
- **Seven input modes:** single topic, topic batch, RSS/article, CSV/Excel,
  pasted narrative, fully manual slides, and a built-in fallback demo.
- **Relevant media selection:** candidates are ranked using subject anchors,
  technical quality, orientation, provider diversity, and creator diversity.
- **Narration-synced visuals:** each narration slide receives its own duration,
  with crossfade overlap compensated automatically.
- **Subject-aware crop:** a local saliency estimate keeps the most informative
  region visible in vertical, landscape, and square exports.
- **Visual QA:** blank, near-duplicate, low-detail, and badly distributed frames
  can be rejected before a render is accepted.
- **Stable audio:** local soundtrack presets, automatic voice mastering, and
  music ducking are applied without extra dashboard switches.
- **Reliable jobs:** isolated workspaces, persisted status/events, cancellation
  checkpoints, retry support, and verified deliverables.
- **One-click Windows installer:** prepares Python, FFmpeg, an isolated virtual
  environment, and Desktop/Start Menu shortcuts.

## How the pipeline works

1. A topic, article, spreadsheet row, or manual script is converted into
   slide-aligned captions, narration, and media queries.
2. Edge-TTS or ElevenLabs creates the voice track.
3. Enabled media providers return candidate videos and images.
4. Relevance and quality scoring select varied, usable assets for each slide.
5. Narration timing controls the visual cuts and subject-aware crops.
6. FFmpeg renders a fixed crossfade, captions, music, logo/progress overlays,
   and optional intro/outro bumpers.
7. FFprobe and visual sampling validate the final MP4 before it is exposed as a
   completed deliverable.

The selected duration is a script and pacing target. The final video follows the
natural narration duration instead of adding a silent tail. Presets range from
10 seconds to 10 minutes; longer videos require more source media and render time.

## Current dashboard controls

| Area | Available choices |
| --- | --- |
| AI | Auto fallback, Gemini, OpenAI, Groq, Ollama, OpenRouter |
| Language | Urdu, English, Hindi, Arabic, Roman Urdu |
| Voice | Free Edge-TTS or optional ElevenLabs |
| Format | Vertical 9:16, landscape 16:9, square 1:1 |
| Media | Mixed, videos only, images only |
| Media quality | Balanced or stricter high-quality filtering |
| Pacing | Approximately 3, 5, or 7 seconds per cut |
| Music | Mystery, epic, sad, ancient, modern, intense |
| Color | None or documentary high contrast |
| Branding | Caption font/size, PNG logo, intro/outro, fixed progress bar |

Normal media sources are Pexels, Pixabay, Google/Bing Images, Wikimedia Commons,
and Unsplash. Storyblocks, NASA Images, and Internet Archive are kept under
**Advanced media sources** for specialized use.

## Windows one-click installation

Download and run:

**[ReelsBuilderSetup.exe](dist/ReelsBuilderSetup.exe)**

The setup installs the application for the current Windows user under:

```text
%LOCALAPPDATA%\Programs\History Reels Builder
```

It then:

- finds or installs Python 3.11–3.14 and FFmpeg;
- creates an isolated `.venv`;
- installs the pinned packages in `requirements.txt`;
- creates Desktop and Start Menu shortcuts;
- prepares output and runtime folders; and
- opens the dashboard in the default browser.

Internet access is required during the first installation. The setup contains a
blank `.env.example`; personal API keys, generated videos, job databases, and
development files are not bundled. Existing `.env` values are preserved when the
installer is run again as an update.

The executable is currently unsigned. If Windows SmartScreen appears, inspect the
publisher/file details and use **More info → Run anyway** only when the file came
from this repository. Its matching checksum is available at
[`dist/ReelsBuilderSetup.exe.sha256`](dist/ReelsBuilderSetup.exe.sha256).

Full installer and rebuild instructions are in
[`docs/INSTALLER.md`](docs/INSTALLER.md).

## Source installation

### Requirements

- Windows with Python 3.11–3.14
- FFmpeg and FFprobe available on `PATH`
- Git
- Internet access for online AI, Edge-TTS, and stock-media providers

Clone the repository and create an isolated environment:

```powershell
git clone https://github.com/anisar699/History-Reels-Builder-Gemini.git
cd History-Reels-Builder-Gemini
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Start the dashboard:

```powershell
python -m streamlit run app.py
```

The old `install.py` flow installs into the current system Python and is retained
only for compatibility. New installations should use the Windows setup or the
isolated source steps above.

## API keys and local mode

API keys can be entered in the dashboard's **API Key Status** section. On a local
desktop installation, saved values are written only to that installation's
ignored `.env` file and applied immediately.

At least one script provider is needed for AI-generated scripts:

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`
- or a locally running Ollama model such as `qwen2.5:7b`

Media-provider keys improve stock coverage:

- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `UNSPLASH_API_KEY`
- `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_CX`
- optional `STORYBLOCKS_PUBLIC_KEY` and `STORYBLOCKS_PRIVATE_KEY`

`ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` are optional. Edge-TTS remains the
default voice provider. Fully manual script input avoids LLM API usage, but online
voice or media providers may still require internet access.

Never commit `.env`, `.streamlit/secrets.toml`, API keys, or generated user data.

## Command-line usage

Run commands from an activated project environment:

```powershell
# Generate one video with the best configured provider
python build_reel.py --topic "5 productivity tips for students" --provider auto

# Generate a script through local Ollama
python build_reel.py --topic "Beginner home workout" --provider ollama

# Build from an RSS feed or article
python build_reel.py --news-url "https://feeds.bbci.co.uk/urdu/rss.xml" --provider groq

# Build from CSV or Excel rows
python build_reel.py --csv "batch_scripts.csv" --provider openrouter

# Keep an isolated job workspace for debugging
python build_reel.py --topic "The printing press" --keep-workspace
```

Supported providers are `auto`, `gemini`, `openai`, `groq`, `ollama`, and
`openrouter`.

## Testing

Run the same regression command used by GitHub Actions:

```powershell
python -B -m unittest discover -s tests -v
```

CI runs the suite on Python 3.11 and 3.12. Tests cover job isolation/retry,
security-sensitive input handling, multilingual captions/fonts, fixed audio and
transition behavior, media relevance/quality, narration timing, subject-aware
crop, visual QA, and deliverable verification.

## Project layout

```text
app.py                         Streamlit dashboard
build_reel.py                  CLI entry point
history_reels/                 Pipeline package
tests/                         Regression suite
installer/                     Runtime bootstrap, launcher, and Inno Setup source
dist/ReelsBuilderSetup.exe     Shareable Windows installer
docs/                          Environment, QA, verification, and installer guides
```

Generated videos are stored by default under:

```text
%USERPROFILE%\Pictures\history videos
```

Installer and dashboard logs are stored inside the installed application's
`runtime\logs` directory.

## Additional documentation

- [Environment and deployment](docs/ENVIRONMENT.md)
- [Quality checks](docs/QUALITY_CHECKS.md)
- [Verification matrix](docs/VERIFICATION.md)
- [Windows installer](docs/INSTALLER.md)
