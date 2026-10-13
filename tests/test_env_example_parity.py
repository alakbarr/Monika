"""
Parity test verifying that critical environment variables read across src/monika
are documented with default guidance in .env.example.
Prevents configuration documentation drift and hidden runtime knobs.
"""

import os
import re
from pathlib import Path

from monika.core.paths import REPO_ROOT

# System and internal test flags that do not belong in public user .env.example
IGNORED_SYSTEM_ENV_VARS = {
    "ALL_PROXY",
    "APPDATA",
    "COLORTERM",
    "ConEmuPID",
    "EDITOR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "LOG_DIR",
    "MONIKA_ALLOW_PROD_DB_IN_TEST",
    "MONIKA_API_URL",
    "MONIKA_PARENT_DEATH_FD",
    "MONIKA_PARENT_HANDLE",
    "NO_COLOR",
    "PYTEST_CURRENT_TEST",
    "PTB_TIMEDELTA",
    "MPLCONFIGDIR",
    "TERM",
    "TERM_PROGRAM",
    "TRADEAGENT_API_URL",
    "WT_SESSION",
    "XDG_DATA_HOME",
}


def test_env_example_documents_codebase_env_vars():
    """Verify that all application environment variables read via os.environ are in .env.example."""
    src_dir = REPO_ROOT / "src" / "monika"
    env_example = REPO_ROOT / ".env.example"

    assert env_example.exists(), ".env.example must exist at repository root"
    example_text = env_example.read_text(encoding="utf-8")

    # Match VAR= or # VAR=
    documented_vars = set(re.findall(r"^[#\s]*([A-Za-z0-9_]+)=", example_text, re.MULTILINE))

    pattern = re.compile(r'os\.(?:environ\.get|getenv)\s*\(\s*["\']([A-Za-z0-9_]+)["\']')
    found_vars = set()

    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                code = (Path(root) / f).read_text(encoding="utf-8", errors="ignore")
                for match in pattern.findall(code):
                    if match not in IGNORED_SYSTEM_ENV_VARS:
                        found_vars.add(match)

    undocumented = found_vars - documented_vars
    assert not undocumented, f"The following environment variables are read in code but missing from .env.example: {sorted(undocumented)}"
