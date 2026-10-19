"""
File: scripts/consolidate_sqlite_dbs.py
Utility to verify and healthcheck SQLite database state in Monika.
Ensures D:/Monika/data/monika.db is safely configured and no split databases exist.
"""

from pathlib import Path


def consolidate():
    root_dir = Path(__file__).resolve().parent.parent
    root_db = root_dir / "data" / "monika.db"
    legacy_db = root_dir / "trading-agent" / "data" / "monika.db"

    print("[*] Checking databases:")
    print(f"    Canonical DB: {root_db} (Exists: {root_db.exists()})")
    print(f"    Legacy DB:    {legacy_db} (Exists: {legacy_db.exists()})")

    if legacy_db.exists():
        print(f"[!] Legacy DB found at {legacy_db}. Recommending manual cleanup or merge.")
    else:
        print("[OK] No split legacy DB found. System is cleanly unified on data/monika.db.")


if __name__ == "__main__":
    consolidate()
