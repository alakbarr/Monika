"""
Architecture tests verifying synchronization between code, documentation, and metadata.
"""

import subprocess
import sys
from pathlib import Path


def test_index_toc_synchronization():
    """Verify that INDEX.md Table of Contents is strictly synchronized with file line numbers."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "scripts" / "update_index_toc.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--check"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"INDEX.md TOC is out of date:\n{result.stdout}\n{result.stderr}"
