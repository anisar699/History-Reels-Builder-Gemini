# Project baseline — Phase A / Phase 1

Last reviewed: 2026-07-17

## Purpose

This document records the local starting point before the professionalization roadmap begins. It is a working baseline, not a release tag or a GitHub update.

## Local source state

- Upstream commit at review: `e6f41842b2f171f34eb09a13fcbcdfbae403750a` — *Add UI option to select Urdu font (Jameel Noori Nastaleeq or Noto Nastaliq)*.
- The local working tree also contains approved, uncommitted fixes to `install.py`, `requirements.txt`, and `tests/test_pipeline.py`.
- No local commit or tag was created for this baseline. A tag at the upstream commit would omit the approved working-tree fixes.
- GitHub operations are disabled by project policy unless the user explicitly requests them.

## Supported local runtime

| Component | Verified local version |
| --- | --- |
| Python | 3.14.6 |
| Streamlit | 1.59.2 |
| FFmpeg / FFprobe | 8.1.2 |
| Edge TTS | 7.2.8 |
| Pandas | 3.0.3 |
| OpenPyXL | 3.1.5 |

The project requires Python 3.10+ in its user documentation. The current verified runtime is Windows with FFmpeg and Edge TTS available on `PATH`.

## Current capabilities

- Streamlit dashboard with topic, batch, RSS/web article, CSV/XLSX, manual AI script, manual script, and fallback generation modes.
- AI script generation through Gemini, OpenAI, Groq, Ollama, OpenRouter, and an automatic fallback chain.
- Edge TTS and ElevenLabs voice providers.
- Pexels, Pixabay, Storyblocks, Bing/Google, Pinterest, Wikimedia, NASA, Internet Archive, and Unsplash media-source controls.
- FFmpeg rendering with subtitles, aspect-ratio presets, transitions, audio ducking, optional ambient sound, grading, progress bar, watermark, and intro/outro bumpers.
- SEO package generation alongside rendered media.

## Verified local checks

The following checks are expected for the Phase 1 working baseline:

- All Python files parse successfully.
- `python -B -m unittest discover -s tests -v` passes.
- CSV/XLSX dependencies are present and a simple XLSX read/write roundtrip succeeds.
- The existing desktop launcher still targets this repository and starts `streamlit run app.py`.

## Known risks and next priorities

1. Generation state is held in mutable module globals, so concurrent Streamlit sessions can interfere with one another.
2. Rendering, downloads, and TTS run synchronously in the dashboard process; there is no persistent job queue, cancellation, recovery, or job history.
3. The selected music vibe is overwritten by AI script data during normal generation, and output names still contain the hard-coded `Asad Voice` label.
4. User-supplied URLs, uploads, and downloaded media need stronger size, type, source, and license controls before public hosting.
5. Secrets are locally ignored but dashboard key management still writes plaintext `.env`; hosted deployment needs managed secrets and authentication.
6. There is no CI workflow, lockfile, container definition, formal Python package metadata, or release process.

## Phase A progress

Phase A / Phase 1 is complete: durable repository rules, a baseline document, secret-ignore protections, and a verified local health check exist.

Phase A / Phase 2 is complete: every pipeline run snapshots dashboard settings into a `GenerationJob`, uses a unique `history_reels_tmp/jobs/<job-id>` workspace, owns its own media IDs, attributions, slide timing, transitions, and errors, and uses a job-suffixed deliverable name to avoid output collisions. The next approved phase is Phase 3: resolve functional behavior issues, starting with preserving the user-selected music vibe and removing the hard-coded voice label from output names.
