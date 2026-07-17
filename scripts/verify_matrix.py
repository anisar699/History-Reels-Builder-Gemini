"""Run the no-network reel configuration verification matrix."""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Allow direct execution from the repository without requiring package install.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from history_reels.verification import run_verification_matrix


def main() -> int:
    report = run_verification_matrix()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
