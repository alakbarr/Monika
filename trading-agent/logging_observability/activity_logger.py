# ==============================================================================
# File: logging_observability/activity_logger.py
# ==============================================================================

"""
Activity Logger: Unified Structured Logging (Python logging stdlib & DB `activity_log`).

Dual functionality:
1. File/Console Log: Asynchronous rotatable stream for runtime operations.
2. DB ActivityLog: Structured persistence for dashboard metrics and Telegram bot history.
"""

import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORIES = frozenset({"trading", "analysis", "risk", "system", "scraping", "telegram"})
LOG_FORMAT_FILE    = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FORMAT_CONSOLE = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT        = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# 1. Python stdlib logging setup
# ---------------------------------------------------------------------------

import queue
try:
    from utils.infra.log_redactor import RedactingFormatter
except ImportError:
    from ..utils.infra.log_redactor import RedactingFormatter

_queue_listener: Optional[logging.handlers.QueueListener] = None


def shutdown_logging() -> None:
    """Stop the background QueueListener worker thread cleanly."""
    global _queue_listener
    if _queue_listener is not None:
        try:
            _queue_listener.stop()
        except Exception:
            pass
        _queue_listener = None
    logging.getLogger().handlers.clear()


def setup_logging(
    log_dir: str = "logs",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB per file
    backup_count: int = 5,
) -> logging.Logger:
    """
    Setup root logger with non-blocking QueueHandler and RedactingFormatter.
    Dipanggil sekali saat aplikasi startup.
    """
    global _queue_listener
    import sys
    is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
    if is_pytest and log_dir == "logs":
        log_dir = os.path.join("logs", "test_runs")

    os.makedirs(log_dir, exist_ok=True)

    # Stop existing listener if re-initializing
    shutdown_logging()

    root = logging.getLogger("TradingAgent")
    root.setLevel(level)

    root.propagate = bool(is_pytest)
    root.handlers.clear()

    # Root logger setup so third-party loggers (httpx, telegram, httpcore, etc.)
    # inherit standard format and RedactingFormatter
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # --- Real file handler (rotating) ---
    try:
        from concurrent_log_handler import ConcurrentRotatingFileHandler as _RotHandler
    except ImportError:
        _RotHandler = logging.handlers.RotatingFileHandler

    file_handler = _RotHandler(
        filename=os.path.join(log_dir, "agent.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(RedactingFormatter(LOG_FORMAT_FILE, datefmt=DATE_FORMAT))

    # Separate error-only file for quick issue scanning
    error_handler = _RotHandler(
        filename=os.path.join(log_dir, "errors.log"),
        maxBytes=max_bytes,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(RedactingFormatter(LOG_FORMAT_FILE, datefmt=DATE_FORMAT))

    # --- Console handler ---
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(RedactingFormatter(LOG_FORMAT_CONSOLE, datefmt=DATE_FORMAT))

    # Non-blocking QueueHandler / QueueListener (I3 & H7)
    if is_pytest:
        root.addHandler(file_handler)
        root.addHandler(error_handler)
        root.addHandler(console)

        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console)
    else:
        log_queue: queue.Queue = queue.Queue(maxsize=10000)
        queue_handler = logging.handlers.QueueHandler(log_queue)
        root.addHandler(queue_handler)
        root_logger.addHandler(queue_handler)

        _queue_listener = logging.handlers.QueueListener(
            log_queue, file_handler, error_handler, console, respect_handler_level=True
        )
        _queue_listener.start()

    root.info(f"Logging initialized. Log dir: {os.path.abspath(log_dir)}")
    return root



# ---------------------------------------------------------------------------
# 2. DB ActivityLog writer
# ---------------------------------------------------------------------------

class ActivityLogger:
    """
    Penulis log asinkron ke DB `activity_log`.
    Didesain non-blocking, exception di-handle internal agar tidak mengganggu logika utama.
    """

    def __init__(self):
        self._logger = logging.getLogger("TradingAgent.ActivityLogger")

    async def log(
        self,
        category: str,
        description: str,
        related_id: Optional[int] = None,
        actor: str = "system",
        session = None,
    ) -> Optional[int]:
        """Catat satu entri aktivitas ke DB."""
        if category not in CATEGORIES:
            self._logger.warning(f"Unknown activity category: {category}")
            category = "system"

        try:
            from database.db import get_session
            from database.models import ActivityLog

            entry = ActivityLog(
                timestamp=datetime.now(timezone.utc),
                category=category,
                description=description[:2000],  # Safety truncation
                related_id=related_id,
                actor=actor,
            )
            
            if session:
                session.add(entry)
                await session.flush()
                return entry.id
            else:
                async with get_session() as new_session:
                    new_session.add(entry)
                    await new_session.commit()
                    await new_session.refresh(entry)
                    return entry.id
        except Exception as e:
            self._logger.error(f"ActivityLogger DB write failed: {e}")
            return None

    # Category shortcuts
    async def trading(self, description: str, related_id: Optional[int] = None, actor: str = "system", session = None) -> Optional[int]:
        self._logger.info(f"[TRADING] {description}")
        return await self.log("trading", description, related_id, actor, session=session)

    async def analysis(self, description: str, related_id: Optional[int] = None, actor: str = "ai_agent", session = None) -> Optional[int]:
        self._logger.info(f"[ANALYSIS] {description}")
        return await self.log("analysis", description, related_id, actor, session=session)

    async def risk(self, description: str, related_id: Optional[int] = None, actor: str = "risk_gate", session = None) -> Optional[int]:
        self._logger.warning(f"[RISK] {description}")
        return await self.log("risk", description, related_id, actor, session=session)

    async def system(self, description: str, related_id: Optional[int] = None, actor: str = "system", session = None) -> Optional[int]:
        self._logger.info(f"[SYSTEM] {description}")
        return await self.log("system", description, related_id, actor, session=session)

    async def scraping(self, description: str, related_id: Optional[int] = None, actor: str = "scraper", session = None) -> Optional[int]:
        self._logger.debug(f"[SCRAPING] {description}")
        return await self.log("scraping", description, related_id, actor, session=session)

    async def telegram(self, description: str, related_id: Optional[int] = None, actor: str = "telegram", session = None) -> Optional[int]:
        self._logger.info(f"[TELEGRAM] {description}")
        return await self.log("telegram", description, related_id, actor, session=session)

    # Bulk write (for batch inserts)
    async def bulk(self, entries: list[dict], session = None) -> int:
        """Catat banyak entri sekaligus dalam 1 transaksi (batch)."""
        if not entries:
            return 0
        try:
            from database.db import get_session
            from database.models import ActivityLog

            async def _do_bulk(sess):
                count = 0
                for e in entries:
                    cat = e.get("category", "system")
                    if cat not in CATEGORIES:
                        cat = "system"
                    sess.add(ActivityLog(
                        timestamp=datetime.now(timezone.utc),
                        category=cat,
                        description=e.get("description", "")[:2000],
                        related_id=e.get("related_id"),
                        actor=e.get("actor", "system"),
                    ))
                    count += 1
                return count
                
            if session:
                return await _do_bulk(session)
            else:
                async with get_session() as new_session:
                    res = await _do_bulk(new_session)
                    await new_session.commit()
                    return res
        except Exception as e:
            self._logger.error(f"ActivityLogger bulk write failed: {e}")
            return 0


# Module-level singleton for convenience
_default_logger: Optional[ActivityLogger] = None


def get_activity_logger() -> ActivityLogger:
    """Mendapatkan singleton instance `ActivityLogger`."""
    global _default_logger
    if _default_logger is None:
        _default_logger = ActivityLogger()
    return _default_logger
