# Reproducible Python environment

Phase 12 pins the project's direct Python dependencies to versions verified locally on 2026-07-17. The project supports Python 3.11 through 3.14.

Create an isolated environment and install the verified dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For editable development installation and the `history-reels` command:

```powershell
python -m pip install -e .
```

Verify the installed dependency graph and project checks:

```powershell
python -m pip check
.\scripts\verify.ps1
```

Provider credentials remain outside dependency files. Use the local `.env` file or a hosting platform's managed secret store as described in `docs/DEPLOYMENT_SECURITY.md`.
