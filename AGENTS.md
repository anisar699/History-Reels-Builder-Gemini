# History Reels Builder agent guidance

## Working agreement

- Treat this as a local-first project. Do not run `git fetch`, `git pull`, `git push`, create a remote branch, or otherwise update GitHub unless the user explicitly asks in the current conversation.
- Do not edit project files, install dependencies, alter API keys, or run destructive cleanup unless the user explicitly authorizes that work.
- Preserve `.env`, untracked user files, and `.agents/`. Never print secret values or copy them into source files, logs, documentation, or commits.
- Use `apply_patch` for source and documentation edits. Keep changes scoped to the approved phase and report the final diff and verification results.
- Do not run `install.py` as a validation step: it installs software, creates a desktop launcher, and starts the dashboard.

## Project map

- `app.py`: Streamlit dashboard and user controls.
- `history_reels/`: generation pipeline, providers, downloads, subtitles, audio, rendering, and SEO output.
- `tests/test_pipeline.py`: lightweight unit tests.
- `.streamlit/config.toml`: dashboard theme configuration.
- `requirements.txt`: Python runtime dependencies.

## Local commands

Run these from the repository root unless the task says otherwise:

```powershell
python -B -m unittest discover -s tests -v
streamlit run app.py
```

For syntax-only validation without creating bytecode:

```powershell
python -B -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in pathlib.Path('.').rglob('*.py')]"
```

## Completion standard

For every approved change, explain the affected behavior, run the smallest relevant checks, and report failures honestly. For pipeline changes, avoid paid API calls and real media rendering unless the user explicitly asks for an end-to-end run.
