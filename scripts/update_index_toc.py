#!/usr/bin/env python3
# ==============================================================================
# File: scripts/update_index_toc.py
# Description: Compatibility Entrypoint for Automated AST Documentation Generator
# ==============================================================================

"""
Backward-compatible entrypoint forwarding to scripts/generate_ast_docs.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATE_SCRIPT = ROOT_DIR / "scripts" / "generate_ast_docs.py"


def generate_toc(check_only: bool = False):
    """Backward-compatible helper function executing generate_ast_docs."""
    args = [sys.executable, str(GENERATE_SCRIPT)]
    if check_only:
        args.append("--check")
    res = subprocess.run(args, cwd=str(ROOT_DIR))
    if check_only and res.returncode != 0:
        sys.exit(1)
    return None


def main() -> int:
    check_mode = "--check" in sys.argv
    generate_toc(check_only=check_mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
