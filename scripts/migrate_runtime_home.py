"""
One-Time Runtime State Migration Utility for Monika Trading Agent.
Safely copies active SQLite databases, sessions, logs, and runtime state
from the in-repo data/ directory to the canonical external MONIKA_HOME.
Non-destructive: Copies files and verifies SHA-256 integrity. Does NOT delete source data.
"""

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from monika.core.paths import REPO_ROOT, get_default_monika_home


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def copy_with_verification(src: Path, dst: Path, dry_run: bool = False) -> bool:
    """Copy file and verify SHA-256 checksum."""
    if dry_run:
        print(f"  [DRY-RUN] Would copy: {src} -> {dst}")
        return True

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    src_hash = compute_sha256(src)
    dst_hash = compute_sha256(dst)
    if src_hash != dst_hash:
        raise ValueError(f"Integrity check failed for {src.name}! Source hash: {src_hash}, Dest hash: {dst_hash}")
    return True


def migrate_runtime_state(target_home: Path, dry_run: bool = False) -> None:
    """Migrate in-repo runtime state to external MONIKA_HOME."""
    src_data = REPO_ROOT / "data"
    src_logs = REPO_ROOT / "logs"

    dst_data = target_home / "data"
    dst_logs = target_home / "logs"

    print("============================================================")
    print("  MONIKA - Runtime State Migration to MONIKA_HOME           ")
    print("============================================================")
    print(f"Source repo data:   {src_data}")
    print(f"Target MONIKA_HOME: {target_home}")
    print(f"Execution mode:     {'DRY-RUN (Preview Only)' if dry_run else 'ACTIVE COPY'}")
    print("------------------------------------------------------------")

    migrated_files = 0
    total_bytes = 0

    # 1. Databases and JSON states
    if src_data.exists():
        for entry in src_data.iterdir():
            if entry.is_file():
                # Skip gitkeep and README
                if entry.name in (".gitkeep", "README.md"):
                    continue
                dst_file = dst_data / entry.name
                file_size = entry.stat().st_size
                print(f"[*] Migrating state file: {entry.name} ({file_size / 1024:.1f} KB)")
                copy_with_verification(entry, dst_file, dry_run=dry_run)
                migrated_files += 1
                total_bytes += file_size

        # 2. Sessions directory (browser profiles, contexts)
        src_sessions = src_data / "sessions"
        if src_sessions.exists() and src_sessions.is_dir():
            dst_sessions = dst_data / "sessions"
            print(f"[*] Migrating sessions directory: {src_sessions} -> {dst_sessions}")
            for root, _, files in os.walk(src_sessions):
                rel_dir = Path(root).relative_to(src_sessions)
                for f in files:
                    src_f = Path(root) / f
                    dst_f = dst_sessions / rel_dir / f
                    file_size = src_f.stat().st_size
                    copy_with_verification(src_f, dst_f, dry_run=dry_run)
                    migrated_files += 1
                    total_bytes += file_size

    # 3. Logs directory
    if src_logs.exists() and src_logs.is_dir():
        print(f"[*] Migrating logs directory: {src_logs} -> {dst_logs}")
        for root, _, files in os.walk(src_logs):
            rel_dir = Path(root).relative_to(src_logs)
            for f in files:
                src_f = Path(root) / f
                dst_f = dst_logs / rel_dir / f
                file_size = src_f.stat().st_size
                copy_with_verification(src_f, dst_f, dry_run=dry_run)
                migrated_files += 1
                total_bytes += file_size

    print("------------------------------------------------------------")
    print(f"Migration completed successfully!")
    print(f"Total files migrated: {migrated_files}")
    print(f"Total volume copied:  {total_bytes / (1024 * 1024):.2f} MB")
    print("============================================================")


def main():
    parser = argparse.ArgumentParser(description="Migrate in-repo runtime state to MONIKA_HOME.")
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Target MONIKA_HOME directory (defaults to platform-standard path)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without writing files",
    )
    args = parser.parse_args()

    target_home = args.target or Path(os.environ.get("MONIKA_HOME") or get_default_monika_home())
    migrate_runtime_state(target_home=target_home, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
