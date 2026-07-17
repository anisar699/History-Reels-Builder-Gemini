# Phase 13 staging acceptance

Phase 13 uses an isolated `.venv` and writes all test downloads, temporary files, job history, and deliverables under `.staging/`. It never prints or stores API keys in its JSON report.

Activate the clean environment and run preflight without an API call:

```powershell
$env:PATH="$(Resolve-Path .venv\Scripts);$env:PATH"
.\.venv\Scripts\python.exe scripts\run_staging_acceptance.py --provider groq --duration 30 --preflight-only
```

Run one bounded real acceptance reel:

```powershell
.\.venv\Scripts\python.exe scripts\run_staging_acceptance.py --provider groq --duration 30
```

The run passes only when the pipeline succeeds and `ffprobe` confirms a non-empty video with audio and video streams, a duration within tolerance, and a non-empty SEO package. Machine-readable results are written to `staging_reports/latest.json`.

Failure reports distinguish `blocked_quota` (provider credits or project usage limit), `blocked_rate_limit` (temporary request/token limit), and `failed` (another pipeline failure). Provider response text and request headers are not copied into the report; a safe OpenAI request ID is retained when available for support diagnostics.

This is a staging check, not a load test. Each non-preflight run may consume one provider request, TTS/network usage, and multiple media downloads.
