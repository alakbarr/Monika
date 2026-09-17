"""
Utility script to repair virtualenv console_scripts launcher stubs on Windows.
When a repository is moved to a different directory, launcher stubs in venv/Scripts/*.exe
retain hardcoded shebangs to the old path. This script regenerates all launchers cleanly.
"""

import importlib.metadata as md
import os
import sys
from pip._vendor.distlib.scripts import ScriptMaker


def fix_entrypoints() -> int:
    scripts_dir = os.path.dirname(sys.executable)
    print(f"Target Scripts directory: {scripts_dir}")
    print(f"Target Python executable: {sys.executable}")

    maker = ScriptMaker(scripts_dir, scripts_dir)
    maker.executable = sys.executable
    maker.clobber = True

    repaired = 0
    total = 0

    for dist in md.distributions():
        for ep in (dist.entry_points or []):
            if ep.group == "console_scripts":
                total += 1
                spec = f"{ep.name} = {ep.value}"
                try:
                    maker.make(spec)
                    repaired += 1
                except Exception as ex:
                    print(f"[WARN] Failed to regenerate {ep.name}: {ex}")

    # Also handle python versioned pip launcher (e.g. pip3.14)
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    for pip_alias in [f"pip{py_ver} = pip._internal.cli.main:main", f"pip{sys.version_info.major} = pip._internal.cli.main:main"]:
        try:
            maker.make(pip_alias)
        except Exception:
            pass

    print(f"[OK] Successfully regenerated {repaired}/{total} console_scripts launchers.")
    return 0


if __name__ == "__main__":
    sys.exit(fix_entrypoints())
