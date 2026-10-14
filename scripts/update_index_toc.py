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


def main() -> int:
    args = [sys.executable, str(GENERATE_SCRIPT)]
    if "--check" in sys.argv:
        args.append("--check")
    res = subprocess.run(args, cwd=str(ROOT_DIR))
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
