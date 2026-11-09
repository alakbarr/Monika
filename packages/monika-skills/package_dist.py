#!/usr/bin/env python3
"""
Monika Institutional Skill Suite - Release Packager (package_dist.py)

Generates standalone distribution ZIP archives for:
- Full Institutional Bundle (11-in-1 Master Suite)
- Individual Standalone Package ZIPs (for marketplaces / modular distribution)
- SHA-256 Checksums for integrity verification
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import zipfile

SKILLS_ROOT = Path(__file__).resolve().parent
DIST_DIR = SKILLS_ROOT / "dist"
VERSION = "1.0.0"

PACKAGES = [
    "01-monika-full-trading-cycle",
    "02-monika-data-gathering",
    "03-monika-central-banks-monetary-policy",
    "04-monika-yield-curve-liquidity-plumbing",
    "05-monika-economic-nowcasting-event-absorption",
    "06-monika-cot-positioning-anti-crowding",
    "07-monika-smc-ict-price-action",
    "08-monika-session-killzones-microstructure",
    "09-monika-commodities-crypto-carry-playbooks",
    "10-monika-dialectical-debate-judge",
    "11-monika-deterministic-risk-math",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def add_dir_to_zip(zip_file: zipfile.ZipFile, src_dir: Path, arc_prefix: str) -> int:
    file_count = 0
    for root, _, files in os.walk(src_dir):
        rel_root = Path(root).relative_to(src_dir)
        # Skip pycache and hidden
        if "__pycache__" in str(rel_root) or ".git" in str(rel_root):
            continue
        for file in files:
            if file.endswith((".pyc", ".pyo", ".DS_Store")):
                continue
            file_path = Path(root) / file
            arc_name = f"{arc_prefix}/{rel_root / file}".replace("\\", "/").replace("//", "/")
            zip_file.write(file_path, arcname=arc_name)
            file_count += 1
    return file_count


def package():
    print("=" * 80)
    print(f"PACKAGING MONIKA INSTITUTIONAL SKILL SUITE v{VERSION}")
    print("=" * 80)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    generated_files: list[Path] = []

    # 1. Individual Skill ZIPs
    print("\n--- 1. Generating Modular Standalone Skill ZIPs ---")
    for pkg in PACKAGES:
        pkg_src = SKILLS_ROOT / pkg
        if not pkg_src.exists():
            print(f"[WARN] Skipping missing package: {pkg}")
            continue

        zip_name = f"{pkg}-v{VERSION}.zip"
        zip_path = DIST_DIR / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            cnt = add_dir_to_zip(zf, pkg_src, arc_prefix=pkg)

        sz_kb = zip_path.stat().st_size / 1024.0
        print(f"[OK] {zip_name:<48} ({cnt:>2} files, {sz_kb:>6.1f} KB)")
        generated_files.append(zip_path)

    # 2. Master Full Bundle ZIP
    print("\n--- 2. Generating Master 11-in-1 Suite Archive ---")
    bundle_name = f"monika-skills-suite-v{VERSION}-full.zip"
    bundle_path = DIST_DIR / bundle_name
    bundle_cnt = 0

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all packages
        for pkg in PACKAGES:
            pkg_src = SKILLS_ROOT / pkg
            if pkg_src.exists():
                bundle_cnt += add_dir_to_zip(zf, pkg_src, arc_prefix=f"monika-skills/{pkg}")

        # Add install.py and README.md if present
        for top_file in ("install.py", "README.md", "LICENSE"):
            fp = SKILLS_ROOT / top_file
            if fp.exists():
                zf.write(fp, arcname=f"monika-skills/{top_file}")
                bundle_cnt += 1

    sz_mb = bundle_path.stat().st_size / (1024.0 * 1024.0)
    print(f"[OK] {bundle_name:<48} ({bundle_cnt:>2} files, {sz_mb:>6.2f} MB)")
    generated_files.append(bundle_path)

    # 3. Compute SHA256 Checksums
    print("\n--- 3. Generating SHA-256 Checksums ---")
    checksum_path = DIST_DIR / "SHA256SUMS.txt"
    with open(checksum_path, "w", encoding="utf-8") as f:
        for gf in sorted(generated_files):
            ck = sha256_file(gf)
            f.write(f"{ck}  {gf.name}\n")
            print(f"  {ck[:16]}...  {gf.name}")

    print("\n" + "=" * 80)
    print(f"PACKAGING COMPLETE: {len(generated_files)} archives generated in:")
    print(f"{DIST_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    package()
