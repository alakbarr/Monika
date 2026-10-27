# ==============================================================================
# Package: monika.infrastructure.database
# File: backup.py
# ==============================================================================

"""
Utilitas Backup Database — Membuat dump PostgreSQL berkala.
Menggunakan pg_dump untuk backup SQL terkompresi (rotasi otomatis).
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import monika.core.platform as platform

logger = logging.getLogger("TradingAgent.DBBackup")


async def create_backup(settings: dict, force: bool = False) -> Dict[str, Any]:
    """
    Buat backup PostgreSQL terkompresi via pg_dump.
    Menghapus backup lama secara otomatis.
    """
    backup_cfg = dict(settings.get("database", {}).get("backup", {}))
    if force:
        backup_cfg["enabled"] = True
    if not backup_cfg.get("enabled", False):
        return {"skipped": True, "reason": "backup_disabled"}

    backup_dir = Path(backup_cfg.get("backup_dir", "backups"))
    keep_last_n = int(backup_cfg.get("keep_last_n", 7))
    db_url = os.getenv("DATABASE_URL", "")

    if not db_url:
        return {"error": "DATABASE_URL not set"}

    if "sqlite" in db_url:
        from monika.infrastructure.database.db import get_canonical_db_path

        clean_url = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        sqlite_file = (
            Path(clean_url).resolve() if clean_url and ":memory:" not in clean_url else get_canonical_db_path()
        )
        if not sqlite_file.exists():
            return {"error": f"SQLite database file not found at {sqlite_file}"}

        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"trading_agent_{timestamp}.db.gz"

        def _do_sqlite_backup() -> None:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                with sqlite3.connect(str(sqlite_file)) as src, sqlite3.connect(str(tmp_path)) as dst:
                    src.backup(dst)
                with open(tmp_path, "rb") as f_in, gzip.open(backup_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

        try:
            async with asyncio.timeout(60.0):
                await asyncio.to_thread(_do_sqlite_backup)
            file_size_mb = backup_file.stat().st_size / (1024 * 1024)
            logger.info(f"SQLite DB backup created: {backup_file} ({file_size_mb:.2f} MB)")

            all_backups = sorted(backup_dir.glob("trading_agent_*.db.gz"))
            if len(all_backups) > keep_last_n:
                for old_backup in all_backups[:-keep_last_n]:
                    old_backup.unlink()
                    logger.info(f"Old SQLite backup removed: {old_backup}")

            return {
                "success": True,
                "backup_file": str(backup_file),
                "size_mb": round(file_size_mb, 2),
                "timestamp": timestamp,
            }
        except Exception as e:
            logger.error(f"SQLite backup failed: {e}")
            return {"error": str(e)}

    # Parse connection info from DATABASE_URL
    parsed = urlparse(db_url)
    if not parsed.hostname or not parsed.username:
        return {"error": "Cannot parse DATABASE_URL for backup"}

    db_user = parsed.username
    db_pass = parsed.password or ""
    db_host = parsed.hostname
    db_port = str(parsed.port or 5432)
    db_name = parsed.path.lstrip("/").split("?")[0]
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"trading_agent_{timestamp}.sql.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass

    try:
        cmd = [
            "pg_dump",
            "-h",
            db_host,
            "-p",
            db_port,
            "-U",
            db_user,
            "-d",
            db_name,
            "--no-password",
        ]
        returncode, stdout_str, stderr_str = await platform.safe_subprocess_run(
            cmd,
            env=env,
            timeout=120,
        )
        if returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr_str}")

        with gzip.open(backup_file, "wb") as f:
            f.write(stdout_str.encode("utf-8"))

        file_size_mb = backup_file.stat().st_size / (1024 * 1024)
        logger.info(f"DB backup created: {backup_file} ({file_size_mb:.1f} MB)")

        # Cleanup old backups
        all_backups = sorted(backup_dir.glob("trading_agent_*.sql.gz"))
        if len(all_backups) > keep_last_n:
            for old_backup in all_backups[:-keep_last_n]:
                old_backup.unlink()
                logger.info(f"Old backup removed: {old_backup}")

        return {
            "success": True,
            "backup_file": str(backup_file),
            "size_mb": round(file_size_mb, 2),
            "timestamp": timestamp,
        }

    except subprocess.TimeoutExpired, asyncio.TimeoutError:
        return {"error": "pg_dump timed out after 120 seconds"}
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "skipped": True,
            "message": "pg_dump not found on host. Database backup requires PostgreSQL client tools installed or a local SQLite database.",
        }
    except Exception as e:
        logger.error(f"DB backup failed: {e}")
        return {"error": str(e)}
