# Quality checks

Run this before committing or sharing a local build:

```powershell
.\scripts\verify.ps1
```

The command parses every Python file and runs the no-network unit test suite. It does not launch the dashboard, render media, call a provider API, or read/write credentials.

The same checks are defined in `.github/workflows/quality.yml`. After the user chooses to push these local changes, GitHub Actions will run them for pull requests and pushes to `main`, `master`, or `agent/**` branches, using Python 3.11 and 3.12. The workflow has read-only repository permissions and does not receive API keys.
