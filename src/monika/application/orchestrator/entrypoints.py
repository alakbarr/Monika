# ==============================================================================
# File: application/orchestrator/entrypoints.py
# ==============================================================================

"""
Main executable entry points, CLI arguments, and single-instance PID locking.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

from monika.application.agent.startup_checks import run_startup_checks as _delegate_startup_checks
from monika.application.agent.task_registry import (
    get_emergency_exit_code,
    mark_clean_shutdown,
)
from monika.application.orchestrator.agent import TradingAgent
from monika.application.orchestrator.lifecycle import BANNER
from monika.core.config.settings import load_all_config
from monika.infrastructure.database.db import close_db, init_db

logger = logging.getLogger("TradingAgent.Main")

PID_FILE = os.path.join(os.getenv("LOG_DIR", "logs"), "trading_agent.pid")
_EMERGENCY_EXIT_CODE: Optional[int] = None


async def run_startup_checks(settings: dict) -> bool:
    """
    Run all startup health checks.
    P2-3: Validasi bahwa PostgreSQL digunakan (bukan SQLite).
    PostgreSQL is REQUIRED — partial unique indexes behave incorrectly on SQLite.

    Returns:
        True if all critical checks pass, False if agent should abort.
    """
    db_url = os.getenv("DATABASE_URL", "")
    is_paper = settings.get("paper_trading", {}).get("enabled", True)
    if "sqlite" in db_url.lower() and not is_paper:
        logger.error(
            "[FAIL] SQLite detected. PostgreSQL is REQUIRED for live trading — partial unique indexes behave incorrectly on SQLite."
        )
        return False
    return await _delegate_startup_checks(settings)


def release_single_instance_lock() -> None:
    """Explicitly release single instance lock file."""
    try:
        current_pid = os.getpid()
        should_remove = False
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                if f.read().strip() == str(current_pid):
                    should_remove = True
            if should_remove and os.path.exists(PID_FILE):
                os.remove(PID_FILE)
    except Exception:
        pass


def acquire_single_instance_lock() -> bool:
    """
    Ensure only one instance of TradingAgent runs at a time.
    Returns True if lock acquired, False if another instance is actively running.
    """
    import atexit
    import psutil

    current_pid = os.getpid()
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    existing_pid = int(content)
                    if existing_pid != current_pid and psutil.pid_exists(existing_pid):
                        try:
                            proc = psutil.Process(existing_pid)
                            if proc.is_running() and "python" in proc.name().lower():
                                logger.warning(
                                    f"[LOCK] Another instance of TradingAgent is already running (PID: {existing_pid}). "
                                    f"Aborting startup of PID {current_pid} to prevent port/MT5/Telegram conflicts."
                                )
                                return False
                        except psutil.NoSuchProcess, psutil.AccessDenied:
                            pass
        except Exception as e:
            logger.debug(f"[LOCK] Error inspecting PID file: {e}")

    try:
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(current_pid))

        atexit.register(release_single_instance_lock)
        return True
    except Exception as e:
        logger.warning(f"[LOCK] Failed to write PID file: {e}")
        return True


async def _amain() -> None:
    """Async main — sets up DB then runs the agent."""
    if not acquire_single_instance_lock():
        sys.exit(0)

    # Single composition root: bootstrap runtime and service container
    from monika.application.bootstrap import bootstrap_application

    container = bootstrap_application()
    settings = container.settings

    # Configure Gemini Rate Limiter limits from settings
    from monika.infrastructure.llm.rate_limiting.gemini_rate_limiter import configure_from_settings

    configure_from_settings(settings)

    # Init DB (create tables)
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready")

    # Startup health checks
    logger.info("Running startup health checks...")
    checks_ok = await run_startup_checks(settings)
    if not checks_ok:
        logger.critical("Critical startup check failed — aborting")
        sys.exit(1)

    # Launch agent
    parser = argparse.ArgumentParser(description="Monika: Autonomous MT5 Trading Agent")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (skip MT5 execution)")
    args = parser.parse_args()
    if not getattr(args, "action", None):
        setattr(args, "action", "execute")

    agent = TradingAgent(settings, dry_run=args.dry_run, container=container)
    try:
        await agent.start()
    finally:
        await close_db()


def main() -> None:
    """Synchronous entry point."""
    try:
        # Python 3.14+: gunakan loop_factory (policy system deprecated).
        # Psycopg (LangGraph checkpointer) butuh SelectorEventLoop di Windows
        # karena ProactorEventLoop tidak support add_reader()/add_writer().
        # asyncpg (SQLAlchemy) tetap kompatibel dengan SelectorEventLoop.
        if sys.platform == "win32":
            asyncio.run(_amain(), loop_factory=asyncio.SelectorEventLoop)
        else:
            asyncio.run(_amain())
        emerg_code = get_emergency_exit_code() or _EMERGENCY_EXIT_CODE
        release_single_instance_lock()
        if emerg_code is not None and emerg_code != 0:
            sys.exit(emerg_code)
        mark_clean_shutdown()
        sys.exit(0)
    except KeyboardInterrupt:
        # Already handled by signal handler — this is just a safety net
        release_single_instance_lock()
        mark_clean_shutdown()
        sys.exit(0)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
        release_single_instance_lock()
        if code == 0:
            mark_clean_shutdown()
        sys.exit(code)
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        release_single_instance_lock()
        emerg_code = get_emergency_exit_code() or _EMERGENCY_EXIT_CODE
        if emerg_code is not None:
            sys.exit(emerg_code)
        sys.exit(1)


__all__ = [
    "BANNER",
    "PID_FILE",
    "_EMERGENCY_EXIT_CODE",
    "_amain",
    "acquire_single_instance_lock",
    "main",
    "release_single_instance_lock",
    "run_startup_checks",
]
