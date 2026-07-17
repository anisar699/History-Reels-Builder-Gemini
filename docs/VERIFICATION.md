# Verification matrix and delivery checks

Run the no-network configuration matrix:

```powershell
.\.venv\Scripts\python.exe scripts\verify_matrix.py
```

The matrix covers the supported caption languages, representative frame ratios, local music modes, and media-quality profiles. It makes no provider, TTS, or media requests.

For every normal render, the pipeline now verifies the copied MP4 with `ffprobe` before marking the job ready. The output must contain audio and video streams, match the chosen frame dimensions, have a measurable duration, and include a non-empty SEO package. A JSON report is saved in `verification_reports` inside the output folder.

Run one bounded real staging acceptance reel separately only when you want to consume provider/media resources:

```powershell
.\.venv\Scripts\python.exe scripts\run_staging_acceptance.py --provider groq --duration 30
```
