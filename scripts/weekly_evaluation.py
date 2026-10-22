#!/usr/bin/env python3
"""
Weekly evaluation harness (Wave 3 context/efficiency).

Runs the harness audit and prints a one-line verdict per check,
mirroring the contract verification that runs before major releases.
"""

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main():
    try:
        import subprocess
    except ImportError:
        print("subprocess unavailable")
        return 1

    audit_cmd = [sys.executable, "-m", "monika.interfaces.cli.harness_audit", "--json"]
    result = subprocess.run(
        audit_cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print("AUDIT EXECUTION FAILED:", result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        return result.returncode
    import json

    data = json.loads(result.stdout)
    passed = sum(1 for c in data.get("checks", []) if c.get("passed"))
    total = len(data.get("checks", []))
    status = "HEALTHY" if passed == total else "DEGRADED"
    print(
        f"WAVE3 WEEKLY EVAL: {status} | {passed}/{total} checks passed | Commit: {subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=str(REPO_ROOT)).decode().strip()}"
    )
    return 0 if status == "HEALTHY" else 1


if __name__ == "__main__":
    sys.exit(main())
