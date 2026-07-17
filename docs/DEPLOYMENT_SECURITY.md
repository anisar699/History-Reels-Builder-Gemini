# Deployment security

This dashboard is safe for local use by default. Before exposing it on the internet, configure the hosting platform's secret store or environment variables; do not put keys in source code or in a browser form.

## Required public-hosting controls

Set these environment variables in the hosting provider:

```text
DASHBOARD_REQUIRE_AUTH=true
DASHBOARD_PASSWORD_HASH=<salted PBKDF2 hash of a strong dashboard password>
DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE=false
```

Generate the password hash locally with an interactive prompt so the password does not enter shell history:

```powershell
python -B -m history_reels.security
```

Store only the generated `pbkdf2_sha256$...` value in `DASHBOARD_PASSWORD_HASH`. When authentication is enabled but the hash is missing, the application blocks access instead of becoming public accidentally. Hashes are compared safely and the raw password is never stored by the app. Legacy 64-character SHA-256 hashes remain accepted for existing local configurations, but PBKDF2 is recommended.

Keep provider keys (for example `OPENAI_API_KEY`, `GEMINI_API_KEY`, `PEXELS_API_KEY`, and media/voice provider keys) in the same managed secret store. The dashboard only reports whether a key is configured; it never fills secret fields with existing values and never writes `.env` files.

## Operational checklist

- Use HTTPS and an authenticated hosting account.
- Keep `DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE=false` for any shared or public deployment.
- Rotate a provider key immediately if it has appeared in a chat, commit, screenshot, or log.
- Restrict who can access the host and its secret-management settings.
- Use `JOB_WORKER_MODE=process` if your host supports background worker processes and you need recovery after dashboard restarts.
- Back up deliverables separately; history cleanup only deletes local job-history records.

For local desktop use, leave `DASHBOARD_REQUIRE_AUTH` unset or false. Existing local environment keys continue to work without being inspected, changed, or displayed by the dashboard.
