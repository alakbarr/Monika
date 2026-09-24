"""
Curate and audit synthesized strategies in trading-agent/analysis/strategies/synthesized/
Categorizes strategies into:
- VALID: Pass AST security, compile cleanly, pass canary check.
- STUB: Hardcoded signals (e.g. confidence=0.82, direction='buy').
- BROKEN: Syntax errors, AST security violations, missing classes, canary exceptions.
Moves STUB and BROKEN strategies into trading-agent/analysis/strategies/synthesized/quarantine/
"""

import os
import sys
import shutil
from pathlib import Path

# Add trading-agent to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler


def curate_strategies(dry_run: bool = True):
    synth_dir = BASE_DIR / "analysis" / "strategies" / "synthesized"
    quarantine_dir = synth_dir / "quarantine"
    
    if not dry_run:
        quarantine_dir.mkdir(parents=True, exist_ok=True)

    files = [f for f in synth_dir.glob("*.py") if f.name != "__init__.py"]
    print(f"Total strategy files found: {len(files)}")

    scheduler = StrategySynthesisScheduler({})
    valid_files = []
    stub_files = []
    broken_files = []

    for f in sorted(files):
        try:
            code = f.read_text(encoding="utf-8")
        except Exception as e:
            broken_files.append((f.name, f"read_error: {e}"))
            continue

        sid = f.stem
        # Check for stub templates
        if ('direction="buy"' in code or "direction='buy'") and "confidence=0.82" in code:
            stub_files.append(f.name)
            continue

        # Check code safety
        if not scheduler.validate_code_safety(code):
            broken_files.append((f.name, "ast_safety_failed"))
            continue

        # Try to find class name
        import re
        m = re.search(r"class\s+([A-Za-z0-9_]+)\s*\(", code)
        if not m:
            broken_files.append((f.name, "no_class_found"))
            continue
        cname = m.group(1)

        strat_cls = scheduler.compile_strategy_class(code, cname)
        if strat_cls is None:
            broken_files.append((f.name, "compilation_failed"))
            continue

        # Canary instantiation test
        try:
            inst = strat_cls({})
            if inst is None:
                broken_files.append((f.name, "instantiation_returned_none"))
                continue
        except Exception as err:
            broken_files.append((f.name, f"canary_inst_error: {err}"))
            continue

        valid_files.append(f.name)

    print(f"\n--- Curate Summary ---")
    print(f"Valid strategies: {len(valid_files)}")
    print(f"Stub strategies: {len(stub_files)}")
    print(f"Broken strategies: {len(broken_files)}")

    if not dry_run:
        moved_count = 0
        for fname in stub_files:
            src = synth_dir / fname
            dst = quarantine_dir / fname
            shutil.move(str(src), str(dst))
            moved_count += 1
        for fname, reason in broken_files:
            src = synth_dir / fname
            dst = quarantine_dir / fname
            shutil.move(str(src), str(dst))
            moved_count += 1
        print(f"Successfully quarantined {moved_count} invalid/stub strategy files.")
    else:
        print("[Dry Run] No files moved.")

    return valid_files, stub_files, broken_files


if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    curate_strategies(dry_run=dry)
