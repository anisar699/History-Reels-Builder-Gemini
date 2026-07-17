# Project baseline — Phase A / Phase 1

Last reviewed: 2026-07-17

## Purpose

This document records the local starting point before the professionalization roadmap begins. It is a working baseline, not a release tag or a GitHub update.

## Local source state

- Upstream commit at review: `e6f41842b2f171f34eb09a13fcbcdfbae403750a` — *Add UI option to select Urdu font (Jameel Noori Nastaleeq or Noto Nastaliq)*.
- Phase A / Phases 1–2 were published as commit `10b6e81` on branch `agent/phase-a-foundation`.
- Phase 3 and Phase 4 changes remain local until the user explicitly requests another GitHub update.
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

The project metadata requires Python 3.11–3.14. The current verified runtime is Windows with FFmpeg and Edge TTS available on `PATH`.

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

1. Dashboard controls still use module-level configuration until a job snapshot is created; a persistent settings model would remove that remaining shared UI state.
2. The default local worker keeps the Streamlit interface responsive and supports manual plus one-time transient automatic retries. Optional `JOB_WORKER_MODE=process` enables queued-job recovery after dashboard restart; long-running FFmpeg/download operations still stop only at their next safe checkpoint.
3. User-supplied URLs, uploads, and downloaded media need stronger size, type, source, and license controls before public hosting.
4. Public hosting requires environment-managed secrets and an enabled dashboard password gate; deployment instructions are in `docs/DEPLOYMENT_SECURITY.md`.
5. There is still no container definition or release process. Transitive dependency resolution remains dependent on the Python package index.

## Phase A progress

Phase A / Phase 1 is complete: durable repository rules, a baseline document, secret-ignore protections, and a verified local health check exist.

Phase A / Phase 2 is complete: every pipeline run snapshots dashboard settings into a `GenerationJob`, uses a unique `history_reels_tmp/jobs/<job-id>` workspace, owns its own media IDs, attributions, slide timing, transitions, and errors, and uses a job-suffixed deliverable name to avoid output collisions.

Phase A / Phase 3 is complete: the selected dashboard music vibe remains authoritative even when AI suggests a different vibe, and output names now use the selected Edge-TTS narrator or the ElevenLabs provider instead of a hard-coded voice label.

Phase A / Phase 4 is complete: no-network pipeline tests now verify that every generation stage receives the same job snapshot and that input validation failures remain attached to the correct job.

Phase 5 is complete: each local render now records queued, running, succeeded, failed, or cancelled state in a SQLite job history beside the deliverables. The dashboard shows recent job history, and cancellation requests are honored at safe boundaries between pipeline stages.

Phase 6 is complete: dashboard submissions now enter a single-worker local background queue, preserving UI responsiveness. The Gallery history provides cancel controls for active jobs and retry controls for failed or cancelled jobs using the persisted local request payload.

Phase 7 is complete: every job now writes structured stage events and progress to local SQLite history, visible from the Gallery. Transient failures receive one automatic retry by default; validation failures and cancellations do not retry.

Phase 8 is complete: history maintenance can safely delete old terminal job records and event logs without touching rendered deliverables, failures are classified into stable categories, and optional process-worker mode can recover persisted queued jobs. The next recommended phase is Phase 9: add authentication, managed secrets, and public-hosting security controls before production deployment.

Phase 9 is complete: the dashboard no longer displays existing API key values or writes `.env` files. Public hosting can require a salted PBKDF2 password gate using managed environment variables, while session-only key overrides are disabled by default and can never persist credentials.

Phase 10 is complete: dashboard uploads now have size and basic file-signature checks, and the news/RSS fetcher rejects non-public, non-HTTP(S), credentialed, or non-standard-port URLs before making a request.

Phase 11 is complete: a repeatable local verification script and a least-privilege GitHub Actions quality workflow now parse Python source and run the no-network unit suite on Python 3.11 and 3.12.

Phase 12 is complete: direct runtime dependencies are pinned to verified versions, the project has installable Python package metadata with a `history-reels` CLI entry point, and environment setup instructions document the supported Python range and local verification steps.

## Post-phase integration audit

The Phase 1–12 audit fixed cross-phase regressions in renderer transition snapshots, retry/recovery settings, process-worker automatic retry, duplicate recovery launches, redirect-safe news fetching, XLSX expansion checks, password hashing, CSV manual-script conversion, empty/misaligned script validation, working-directory-independent asset paths, verification exit codes, and stale secure-key setup instructions. Regression coverage now exercises these paths without provider API calls or real media rendering.

Phase 13 adds a clean isolated staging environment and a bounded real acceptance runner. The runner keeps staging assets separate from normal deliverables, validates the final audio/video streams and duration with `ffprobe`, and writes a secret-free machine-readable result.
