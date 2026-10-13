"""
Architecture boundary tests ensuring layer isolation and Clean Architecture invariants.
Uses import-linter to verify that no forbidden layer crossings occur.
"""

import subprocess
import sys


def test_import_linter_contracts():
    """Verify that all architectural layer contracts defined in .importlinter pass."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import Linter failed:\n{result.stdout}\n{result.stderr}"
