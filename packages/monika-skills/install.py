#!/usr/bin/env python3
"""
Monika Institutional Skill Suite - Universal Cross-Platform Installer (install.py)

Zero-dependency Python script to install Monika's institutional skill suite into:
- Claude Code (~/.claude/skills/)
- Google Antigravity (~/.gemini/antigravity-cli/skills/ or ~/.gemini/config/skills/)
- Project Workspace (./.claude/skills/ or ./.agents/skills/)
- Custom Directory (--path <DIR>)

Usage Examples:
    python install.py --target claude --all
    python install.py --target antigravity --package 01
    python install.py --target project --path ./my-workspace --all
    python install.py --list
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

SKILLS_ROOT = Path(__file__).resolve().parent

PACKAGES_MAP: Dict[str, Tuple[str, str]] = {
    "01": (
        "01-monika-full-trading-cycle",
        "Master Institutional Desk: Complete 5-stage cognitive trading cycle & 12-point RiskGate",
    ),
    "02": (
        "02-monika-data-gathering",
        "Data Gathering & Timing: Multi-TF telemetry verification, TTL freshness, session killzones",
    ),
    "03": (
        "03-monika-central-banks-monetary-policy",
        "Monetary Policy: CB reaction functions, Taylor Rule, r-star, and FX policy differentials",
    ),
    "04": (
        "04-monika-yield-curve-liquidity-plumbing",
        "Macro Liquidity Plumbing: 2s10s yield curve slope, Fed net liquidity (WALCL-TGA-RRP), TIPS",
    ),
    "05": (
        "05-monika-economic-nowcasting-event-absorption",
        "Event Nowcasting: Pre-event pricing, surprise z-scores, post-event liquidity absorption",
    ),
    "06": (
        "06-monika-cot-positioning-anti-crowding",
        "COT & Anti-Crowding: 3-specialist triangulation (Tech 45%, Macro 35%, Contrarian Sent 20%)",
    ),
    "07": (
        "07-monika-smc-ict-price-action",
        "SMC / ICT Structure: 3-zone dealing range (pos), order blocks, FVGs, 20-pt confluence scorecard",
    ),
    "08": (
        "08-monika-session-killzones-microstructure",
        "Session Microstructure: Killzone execution windows, Judas swing detection, spread expansion gates",
    ),
    "09": (
        "09-monika-commodities-crypto-carry-playbooks",
        "Specialized Playbooks: Brent/WTI arbitrage, 3:2:1 crack spread, BTC funding, carry trade score",
    ),
    "10": (
        "10-monika-dialectical-debate-judge",
        "Dialectical Debate & Bayesian Judge: 2-round Bull/Bear debate, rebuttal attenuation, Brier calibration",
    ),
    "11": (
        "11-monika-deterministic-risk-math",
        "Deterministic Risk Math: Pre-computed brackets, Decimal ROUND_FLOOR lot sizing, 12-point RiskGate",
    ),
}


def resolve_target_dir(target: str, custom_path: Optional[str] = None) -> Path:
    home = Path.home()

    if target == "claude":
        return home / ".claude" / "skills"
    elif target == "antigravity":
        # Check standard Antigravity directories
        cand1 = home / ".gemini" / "antigravity-cli" / "skills"
        cand2 = home / ".gemini" / "config" / "skills"
        if cand1.parent.exists():
            return cand1
        elif cand2.parent.exists():
            return cand2
        return cand1
    elif target == "project":
        base = Path(custom_path) if custom_path else Path.cwd()
        return base / ".claude" / "skills"
    elif target == "custom":
        if not custom_path:
            raise ValueError("--path must be specified when using --target custom")
        return Path(custom_path).resolve()
    else:
        raise ValueError(f"Unknown target: {target}")


def install_package(pkg_dir_name: str, dest_root: Path, dry_run: bool = False) -> bool:
    src_dir = SKILLS_ROOT / pkg_dir_name
    if not src_dir.exists():
        print(f"[ERROR] Source package directory not found: {src_dir}")
        return False

    dest_dir = dest_root / pkg_dir_name

    print(f"Installing '{pkg_dir_name}' -> {dest_dir}")
    if dry_run:
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy SKILL.md
    skill_file = src_dir / "SKILL.md"
    if skill_file.exists():
        shutil.copy2(skill_file, dest_dir / "SKILL.md")

    # Copy subdirectories (scripts, templates, references)
    for sub in ("scripts", "templates", "references"):
        sub_src = src_dir / sub
        if sub_src.exists() and sub_src.is_dir():
            sub_dest = dest_dir / sub
            if sub_dest.exists():
                shutil.rmtree(sub_dest)
            shutil.copytree(
                sub_src,
                sub_dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"),
            )

    return True


def verify_installed_package(dest_dir: Path) -> bool:
    scripts_dir = dest_dir / "scripts"
    if not scripts_dir.exists():
        return True

    py_scripts = list(scripts_dir.glob("*.py"))
    if not py_scripts:
        return True

    test_script = py_scripts[0]
    cmd = [sys.executable, str(test_script), "--help"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Universal Installer for Monika Institutional Skill Suite (Claude Code, Antigravity, Custom)"
    )
    parser.add_argument(
        "--target",
        type=str,
        choices=["claude", "antigravity", "project", "custom"],
        default="claude",
        help="Target platform or directory (default: claude)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Custom destination directory for --target custom or project root for --target project",
    )
    parser.add_argument(
        "--package",
        type=str,
        default=None,
        help="Specific package code (01-11) or package name to install (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install all 11 packages (default if --package is not specified)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing installation of selected packages before copying",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available skill packages and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the installation without creating or copying files",
    )

    args = parser.parse_args()

    if args.list:
        print("=" * 80)
        print("MONIKA INSTITUTIONAL SKILL SUITE - AVAILABLE PACKAGES")
        print("=" * 80)
        for code, (name, desc) in sorted(PACKAGES_MAP.items()):
            print(f"[{code}] {name}")
            print(f"     Description: {desc}")
        print("=" * 80)
        return 0

    dest_root = resolve_target_dir(args.target, args.path)
    print("=" * 80)
    print("MONIKA SKILL SUITE INSTALLER")
    print("=" * 80)
    print(f"Target Platform : {args.target}")
    print(f"Destination Path: {dest_root}")
    print(f"Python Runtime  : {sys.executable} (v{sys.version.split()[0]})")
    print("=" * 80)

    # Determine packages to install
    to_install: List[str] = []
    if args.package:
        key = args.package.strip()
        if key in PACKAGES_MAP:
            to_install.append(PACKAGES_MAP[key][0])
        else:
            # Check by folder name
            matched = [v[0] for v in PACKAGES_MAP.values() if key.lower() in v[0].lower()]
            if matched:
                to_install.append(matched[0])
            else:
                print(f"[ERROR] Invalid package selector: {args.package}")
                print(f"Valid keys: {list(PACKAGES_MAP.keys())}")
                return 1
    else:
        # Default is all packages
        to_install = [v[0] for v in sorted(PACKAGES_MAP.values())]

    print(f"Packages to install ({len(to_install)}):")
    for p in to_install:
        print(f"  - {p}")
    print()

    if not args.dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)

    installed_count = 0
    for pkg_name in to_install:
        pkg_dest = dest_root / pkg_name
        if args.clean and pkg_dest.exists() and not args.dry_run:
            print(f"Cleaning existing directory: {pkg_dest}")
            shutil.rmtree(pkg_dest)

        ok = install_package(pkg_name, dest_root, dry_run=args.dry_run)
        if ok:
            installed_count += 1
            if not args.dry_run:
                verified = verify_installed_package(pkg_dest)
                status = "[OK Verified]" if verified else "[WARN Unverified]"
                print(f"  -> Status: {status}")

    print("\n" + "=" * 80)
    if args.dry_run:
        print(f"DRY RUN COMPLETE: {installed_count} packages simulated.")
    else:
        print(f"INSTALLATION COMPLETE: {installed_count} packages installed successfully.")
        print(f"\nNext Steps:")
        print(f"1. Open Claude Code or Antigravity in your workspace.")
        print(f"2. Your agent will automatically discover the skills at:")
        print(f"   {dest_root}")
        print(f"3. Prompt your agent, for example:")
        print(f'   "Analyze EURUSD multi-timeframe structure and macro policy using Monika."')
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
