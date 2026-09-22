# ==============================================================================
# File: execution/ea_bridge/heartbeat_writer.py
# ==============================================================================

"""
Heartbeat Writer — Menjaga dead-man's switch EA tetap terpenuhi.

Sesuai spesifikasi §10: Backend Python secara periodik menulis file heartbeat
yang dibaca oleh EA MT5. Jika file heartbeat usang (> 120 detik), EA akan menutup
semua posisi sebagai pengamanan darurat.

Modul ini berjalan sebagai task background asyncio.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("TradingAgent.Heartbeat")

import platform

# MT5 uses the Common folder for file sharing between EA and Python
# Default location: C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\
def _get_default_mt5_common():
    if platform.system() == "Windows":
        return os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files")
    else:
        # Linux/VPS: path bisa dikonfigurasi via env var
        return os.getenv("MT5_COMMON_FILES_PATH", "/tmp/mt5_common")

_DEFAULT_MT5_COMMON = _get_default_mt5_common()

HEARTBEAT_FILENAME = "ai_agent_heartbeat.txt"
LEGACY_HEARTBEAT_FILENAME = "claude_agent_heartbeat.txt"
EA_HEARTBEAT_FILENAME = "ea_heartbeat.txt"
HEARTBEAT_INTERVAL_SECONDS = 20      # Write every 20s (EA timeout is 10min)
EA_STALE_THRESHOLD_SECONDS  = 120    # Alert if EA heartbeat is >2min old


class HeartbeatManager:
    """
    Mengelola file heartbeat dari Python ke EA.
    Berjalan sebagai background task untuk terus memperbarui timestamp.
    """

    def __init__(self, mt5_common_path: Optional[str] = None):
        self.common_path = Path(mt5_common_path or _DEFAULT_MT5_COMMON)
        self.heartbeat_file = self.common_path / HEARTBEAT_FILENAME
        self.legacy_heartbeat_file = self.common_path / LEGACY_HEARTBEAT_FILENAME
        self.ea_heartbeat_file = self.common_path / EA_HEARTBEAT_FILENAME
        self._running = False
        self._stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        """Tulis heartbeat setiap HEARTBEAT_INTERVAL_SECONDS terus-menerus."""
        self._running = True
        self._stop_event.clear()
        logger.info(
            f"Heartbeat writer started. "
            f"Writing to: {self.heartbeat_file} "
            f"every {HEARTBEAT_INTERVAL_SECONDS}s"
        )
        while self._running and not self._stop_event.is_set():
            await asyncio.to_thread(self._write_heartbeat)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()

    def _write_heartbeat(self) -> None:
        """Tulis timestamp Unix saat ini ke file heartbeat (universal dan legacy untuk kompatibilitas)."""
        try:
            self.common_path.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            
            # Tulis ke file universal dan legacy (menggunakan UTF-8/ANSI standar)
            for hb_file in (self.heartbeat_file, self.legacy_heartbeat_file):
                for attempt in range(5):
                    try:
                        hb_file.write_text(str(ts), encoding="utf-8")
                        break
                    except PermissionError:
                        if attempt < 4:
                            time.sleep(0.5)
                        else:
                            raise
            logger.debug(f"Heartbeat written: {ts}")
        except Exception as e:
            logger.error(f"Failed to write heartbeat: {e}")

    def check_ea_alive(self) -> tuple[bool, int]:
        """Periksa apakah EA baru-baru ini menulis file heartbeat-nya (EA masih aktif)."""
        try:
            if not self.ea_heartbeat_file.exists():
                return False, -1

            # Baca file heartbeat EA (support UTF-8 dan UTF-16LE fallback)
            try:
                content = self.ea_heartbeat_file.read_text(encoding="utf-8").strip()
            except Exception:
                content = self.ea_heartbeat_file.read_text(encoding="utf-16le").strip()
            
            # Hapus Null characters yang mungkin terbaca
            content = content.replace("\x00", "").strip()
            if not content:
                return False, -1
                
            ea_ts = int(content)
            stale = int(time.time()) - ea_ts

            if stale > EA_STALE_THRESHOLD_SECONDS:
                logger.warning(
                    f"EA heartbeat stale: {stale}s old "
                    f"(threshold={EA_STALE_THRESHOLD_SECONDS}s)"
                )
                return False, stale

            return True, stale
        except Exception as e:
            logger.debug(f"EA heartbeat check error: {e}")
            return False, -1

    def get_watchdog(self, check_interval_seconds: float = 15.0) -> Any:
        """PR-16: Returns an active EAWatchdog instance bound to this manager."""
        from execution.ea_bridge.watchdog import EAWatchdog
        return EAWatchdog(
            heartbeat_manager=self,
            check_interval_seconds=check_interval_seconds,
        )


# Canonical backward compatibility alias
HeartbeatWriter = HeartbeatManager
