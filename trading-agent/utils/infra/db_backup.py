# ==============================================================================
# File: utils/db_backup.py
# ==============================================================================

"""
Utilitas Backup Database — Membuat dump PostgreSQL berkala.
Menggunakan pg_dump untuk backup SQL terkompresi (rotasi otomatis).
"""
import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("TradingAgent.DBBackup")


async def create_backup(settings: dict) -> dict:
    """
    Buat backup PostgreSQL terkompresi via pg_dump.
    Menghapus backup lama secara otomatis.
    """
    backup_cfg = settings.get("database", {}).get("backup", {})
    if not backup_cfg.get("enabled", False):
        return {"skipped": True, "reason": "backup_disabled"}

    backup_dir = Path(backup_cfg.get("backup_dir", "backups"))
    keep_last_n = int(backup_cfg.get("keep_last_n", 7))
    db_url = os.getenv("DATABASE_URL", "")

    if not db_url:
        return {"error": "DATABASE_URL not set"}

    # Parse connection info from DATABASE_URL
    from urllib.parse import urlparse
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
        from utils.infra.platform_compat import safe_subprocess_run

        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", db_port,
            "-U", db_user,
            "-d", db_name,
            "--no-password",
        ]
        returncode, stdout_str, stderr_str = await safe_subprocess_run(
            cmd,
            env=env,
            timeout=120,
        )
        if returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr_str}")
        
        import gzip
        with gzip.open(backup_file, 'wb') as f:
            f.write(stdout_str.encode('utf-8'))
        
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

    except (subprocess.TimeoutExpired, asyncio.TimeoutError):
        return {"error": "pg_dump timed out after 120 seconds"}
    except FileNotFoundError:
        return {"error": "pg_dump not found. Ensure PostgreSQL client tools are installed."}
    except Exception as e:
        logger.error(f"DB backup failed: {e}")
        return {"error": str(e)}
