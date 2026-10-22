# ==============================================================================
# File: interfaces/cli/harness_audit.py
# ==============================================================================

"""Standalone CLI entry point for the hermetic agent-harness audit suite.

Examples:
    python -m monika.interfaces.cli.harness_audit
    python -m monika.interfaces.cli.harness_audit --json --output harness_audit.json
    python -m monika.interfaces.cli.harness_audit --strict   # CI gate after ratchet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from monika.application.evals.harness_audit import report_to_json, run_harness_audit_sync
from monika.interfaces.cli.platform_compat import ensure_utf8_streams


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermetic agent-harness invariant audit")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any invariant fails")
    parser.add_argument("--output", default=None, help="Write the JSON report to this path")
    args = parser.parse_args(argv)

    ensure_utf8_streams()
    report = run_harness_audit_sync()
    payload = report_to_json(report)

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")

    if args.json:
        print(payload)
    else:
        print(f"Harness audit v1 — {report.passed}/{len(report.checks)} checks passed in {report.duration_ms} ms")
        for check in report.checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.check_id}: {check.title}")
            if not check.passed:
                print(f"       {check.detail}")

    return 1 if args.strict and not report.all_passed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
