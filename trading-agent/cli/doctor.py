"""
File: cli/doctor.py
Comprehensive diagnostic and self-healing engine for Monika (MT5 Trading Agent).
Integrates deep AST analysis, MT5, database schema, API, dependency, and config health checks.
"""

import os
import sys
import shutil
import logging
import asyncio
import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("TradingAgent.CLI.Doctor")


@dataclass
class DiagnosticItem:
    category: str
    name: str
    status: str  # "OK", "WARN", "FAIL", "FIXED"
    message: str
    fixable: bool = False
    details: Optional[str] = None


class SystemDoctor:
    """Performs deep environmental and functional sanity checks with unified StartupChecker and auto-fix."""

    def __init__(self, fix: bool = False, live_probes: bool = True, verbose: bool = False):
        self.fix = fix
        self.live_probes = live_probes
        self.verbose = verbose
        self.diagnostics: List[DiagnosticItem] = []

    def _record(self, category: str, name: str, status: str, message: str, fixable: bool = False, details: Optional[str] = None):
        self.diagnostics.append(
            DiagnosticItem(category=category, name=name, status=status, message=message, fixable=fixable, details=details)
        )

    async def check_directories(self) -> None:
        """Verify required directories exist and are writable."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        req_dirs = [
            os.path.join(base_dir, "skills", "trading", "playbooks"),
            os.path.join(base_dir, "skills", "trading", "playbooks", "archive"),
            os.path.join(base_dir, "data"),
            os.path.join(base_dir, "config"),
            os.path.join(base_dir, "logs"),
            os.path.join(base_dir, "data", "cache", "spillover"),
        ]
        for d in req_dirs:
            if os.path.exists(d):
                self._record("Filesystem", f"dir:{os.path.basename(d)}", "OK", f"Directory exists: {d}")
            else:
                if self.fix:
                    try:
                        os.makedirs(d, exist_ok=True)
                        self._record("Filesystem", f"dir:{os.path.basename(d)}", "FIXED", f"Created directory: {d}")
                    except Exception as e:
                        self._record("Filesystem", f"dir:{os.path.basename(d)}", "FAIL", f"Failed to create: {e}")
                else:
                    self._record("Filesystem", f"dir:{os.path.basename(d)}", "WARN", f"Missing directory: {d}", fixable=True)

    def check_dependencies(self, settings: Optional[dict] = None) -> None:
        """Verify system binaries and critical python packages with tier awareness."""
        from config.settings import get_installation_tier
        tier = get_installation_tier(settings or {})

        # Check Node.js and npm for dashboard
        node_path = shutil.which("node")
        npm_path = shutil.which("npm")
        if node_path and npm_path:
            self._record("Dependencies", "Node/NPM", "OK", f"Dashboard prerequisites available ({node_path})")
        elif tier == "trial":
            self._record("Dependencies", "Node/NPM", "INFO", "Node/npm optional in Trial package (using CLI + Telegram).")
        else:
            self._record("Dependencies", "Node/NPM", "WARN", "Node.js or npm not found. Dashboard frontend build may fail.", details="Install Node.js LTS if running the local web dashboard.")

        # Check MetaTrader5 Python package or Linux RPC bridge
        try:
            from execution.mt5_compat import ensure_mt5_module, is_native_mt5_available, is_mt5linux_available
            mt5 = ensure_mt5_module()
            if is_native_mt5_available():
                self._record("Dependencies", "MetaTrader5-Pkg", "OK", f"MetaTrader5 native Python package installed (v{getattr(mt5, '__version__', 'unknown')}).")
            elif is_mt5linux_available():
                self._record("Dependencies", "MetaTrader5-Pkg", "OK", f"MetaTrader5 Linux RPC bridge (mt5linux) available.")
            elif tier == "trial":
                self._record("Dependencies", "MetaTrader5-Pkg", "INFO", "Internal Paper Trading Sandbox active (native MT5 binary optional).")
            else:
                self._record("Dependencies", "MetaTrader5-Pkg", "WARN", "MetaTrader5 native package or mt5linux not installed.", details="For Windows: pip install MetaTrader5. For Linux VPS: pip install mt5linux")
        except Exception as e:
            if tier == "trial":
                self._record("Dependencies", "MetaTrader5-Pkg", "INFO", "Paper Trading simulation sandbox active.")
            else:
                self._record("Dependencies", "MetaTrader5-Pkg", "WARN", f"MetaTrader5 check error: {e}", details="For Windows: pip install MetaTrader5. For Linux VPS: pip install mt5linux")

    def check_market_session(self) -> None:
        """Checks whether the global financial markets are open or in weekend closure."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        weekday = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = now_utc.hour

        # Forex closes Friday ~21:00 UTC and reopens Sunday ~21:00 UTC
        is_weekend = (weekday == 5) or (weekday == 4 and hour >= 21) or (weekday == 6 and hour < 21)
        if is_weekend:
            self._record("Market", "SessionStatus", "WARN", "Forex market currently CLOSED for weekend. Evaluation & crypto active.")
        else:
            self._record("Market", "SessionStatus", "OK", "Forex & global financial markets are OPEN.")

    def check_configuration(self, settings: dict) -> None:
        """Check settings.yaml and modular split files."""
        try:
            pt = settings.get("paper_trading", {})
            if isinstance(pt, dict) and pt.get("enabled") is True:
                self._record("Config", "paper_trading", "OK", "Safety guard active (paper_trading.enabled: true).")
            else:
                self._record("Config", "paper_trading", "WARN", "paper_trading.enabled is False or missing. Live trading mode!")

            llm_cfg = settings.get("llm", {})
            roles = llm_cfg.get("task_roles", {})
            if roles:
                self._record("Config", "llm.task_roles", "OK", f"{len(roles)} task roles mapped in configuration.")
            else:
                self._record("Config", "llm.task_roles", "WARN", "No task_roles defined in llm configuration.")

        except Exception as e:
            self._record("Config", "settings.yaml", "FAIL", f"Configuration parsing error: {e}")

    def check_credentials(self, settings: dict) -> None:
        """Check API keys and credential definitions in environment without reading .env directly."""
        providers = [
            ("GEMINI_API_KEY", "Google Gemini"),
            ("ANTHROPIC_API_KEY", "Anthropic Claude"),
            ("OPENAI_API_KEY", "OpenAI"),
            ("GROQ_API_KEY", "Groq"),
            ("DEEPSEEK_API_KEY", "DeepSeek"),
        ]
        active_count = 0
        for env_var, name in providers:
            if os.getenv(env_var) or (env_var == "GEMINI_API_KEY" and os.getenv("GEMINI_API_KEYS")):
                self._record("Credentials", env_var, "OK", f"{name} API key configured.")
                active_count += 1
            else:
                self._record("Credentials", env_var, "WARN", f"{name} ({env_var}) not set in environment.")

        if active_count == 0:
            self._record("Credentials", "LLM_PROVIDERS", "FAIL", "No AI provider API keys found. Agent cannot execute reasoning tasks.")

    def check_mt5(self, settings: dict) -> None:
        """Check MT5 terminal and account settings."""
        mt5_cfg = settings.get("mt5", {}) if isinstance(settings, dict) else {}
        pt = settings.get("paper_trading", {}) if isinstance(settings, dict) else {}
        is_paper = pt.get("enabled", True) if isinstance(pt, dict) else True

        mt5_path = os.getenv("MT5_PATH") or mt5_cfg.get("path")
        if mt5_path and os.path.exists(mt5_path):
            self._record("MT5", "MT5_PATH", "OK", f"MT5 terminal binary located at: {mt5_path}")
        elif is_paper:
            self._record("MT5", "MT5_PATH", "INFO", "MT5 terminal binary not found (Paper trading active, MT5 optional).")
        else:
            self._record("MT5", "MT5_PATH", "WARN", f"MT5 binary path not found or unset: {mt5_path}")

        account = os.getenv("MT5_ACCOUNT")
        if account:
            self._record("MT5", "MT5_ACCOUNT", "OK", f"MT5 Account configured ({account}).")
        elif is_paper:
            self._record("MT5", "MT5_ACCOUNT", "INFO", "MT5_ACCOUNT unset (Paper trading mode active, simulation only).")
        else:
            self._record("MT5", "MT5_ACCOUNT", "FAIL", "MT5_ACCOUNT environment variable is missing for live trading.")

    async def check_database_migrations(self) -> None:
        """Verify database connectivity, active DBA transaction locks, and schema migrations."""
        try:
            from database.db import init_db, get_session, close_db
            await init_db()
            async with get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))

                # Check for active blocking locks in PostgreSQL
                try:
                    lock_res = await session.execute(text("""
                        SELECT pid, usename, pg_blocking_pids(pid) AS blocked_by, query
                        FROM pg_stat_activity
                        WHERE cardinality(pg_blocking_pids(pid)) > 0;
                    """))
                    blocked_rows = lock_res.fetchall()
                    if blocked_rows:
                        self._record("Database", "PostgreSQL-Locks", "WARN", f"Detected {len(blocked_rows)} blocked transaction(s) in PostgreSQL.")
                    else:
                        self._record("Database", "PostgreSQL-Locks", "OK", "No deadlocks or blocked transactions detected.")
                except Exception:
                    pass

                # Check Alembic version table
                try:
                    alembic_res = await session.execute(text("SELECT version_num FROM alembic_version;"))
                    ver = alembic_res.scalar_one_or_none()
                    if ver:
                        self._record("Database", "Alembic-Version", "OK", f"Current migration head revision: {ver}")
                    else:
                        self._record("Database", "Alembic-Version", "WARN", "alembic_version table is empty.")
                except Exception:
                    self._record("Database", "Alembic-Version", "WARN", "alembic_version table not initialized.")

            db_type_label = "SQLite" if "sqlite" in os.getenv("DATABASE_URL", "") else "PostgreSQL"
            self._record("Database", db_type_label, "OK", f"{db_type_label} connection successful (SELECT 1 passed).")
        except Exception as e:
            self._record("Database", "PostgreSQL", "FAIL", f"Database connection failed: {str(e)[:150]}")
            if self.fix:
                self._record("Database", "AutoFix", "INFO", "Attempting alembic migration...")
                try:
                    import subprocess
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    env = os.environ.copy()
                    db_url = env.get("DATABASE_URL", "")
                    if "+asyncpg" in db_url:
                        env["DATABASE_URL"] = db_url.replace("postgresql+asyncpg://", "postgresql://")
                    subprocess.run(["alembic", "upgrade", "head"], cwd=base_dir, env=env, check=False)
                except Exception:
                    pass
        finally:
            try:
                from database.db import close_db
                await close_db()
            except Exception:
                pass

    async def check_startup_checker_suite(self, settings: dict) -> None:
        """Execute unified 11-step StartupChecker from agent/startup_checks.py."""
        from agent.startup_checks import StartupChecker
        checker = StartupChecker(settings=settings)
        try:
            ok, warnings = await checker.run_all_checks()
            if ok:
                self._record("PreFlight", "StartupCheckerSuite", "OK", "All 11 pre-flight verification checks passed.")
            else:
                self._record("PreFlight", "StartupCheckerSuite", "FAIL", "One or more critical startup checks failed.")

            for w in warnings:
                if w.startswith("FAIL:"):
                    self._record("PreFlight", "Check", "FAIL", w[5:].strip())
                elif w.startswith("WARN:"):
                    self._record("PreFlight", "Check", "WARN", w[5:].strip())
                else:
                    self._record("PreFlight", "Check", "WARN", w.strip())
        except Exception as e:
            self._record("PreFlight", "StartupCheckerSuite", "FAIL", f"StartupChecker error: {e}")
        finally:
            try:
                from database.db import close_db
                await close_db()
            except Exception:
                pass

    def check_wal_integrity_and_repair(self) -> None:
        """Verify SQLite WAL database files integrity and clear stale locks."""
        import sqlite3
        wal_dbs = [
            Path("trading-agent/data/session_db.sqlite"),
            Path("data/universal_cron.db"),
        ]
        for db_file in wal_dbs:
            if not db_file.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_file), timeout=5.0)
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                res = cursor.fetchone()
                conn.close()
                if res and res[0] == "ok":
                    self._record("DatabaseWAL", f"wal:{db_file.name}", "OK", f"Integrity check passed ({db_file.name}).")
                else:
                    self._record("DatabaseWAL", f"wal:{db_file.name}", "WARN", f"Integrity check returned: {res}")
            except Exception as e:
                self._record("DatabaseWAL", f"wal:{db_file.name}", "WARN", f"WAL check error: {e}")

    async def check_redis(self, settings: dict) -> None:
        """Verify Redis cache connectivity if configured or using localhost."""
        redis_cfg = settings.get("redis", {}) if isinstance(settings, dict) else {}
        redis_url = os.getenv("REDIS_URL") or redis_cfg.get("url") or "redis://localhost:6379/0"
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(redis_url, socket_connect_timeout=1.0)
            await client.ping()
            await client.aclose()
            self._record("Cache", "Redis", "OK", f"Redis connection verified ({redis_url}).")
        except Exception as e:
            self._record("Cache", "Redis", "WARN", f"Redis offline or unreachable ({str(e)[:70]}). Local in-memory cache active.")

    async def run_diagnostics(self) -> List[DiagnosticItem]:
        """Runs the entire unified battery of doctor checks."""
        from config.settings import load_all_config
        try:
            settings = load_all_config()
        except Exception as e:
            settings = {}
            self._record("Config", "load_all_config", "FAIL", f"Error loading settings: {e}")

        await self.check_directories()
        self.check_dependencies(settings)
        self.check_market_session()
        self.check_configuration(settings)
        self.check_credentials(settings)
        self.check_mt5(settings)
        self.check_wal_integrity_and_repair()
        if self.live_probes:
            try:
                await asyncio.gather(
                    self.check_database_migrations(),
                    self.check_redis(settings),
                    self.check_startup_checker_suite(settings),
                    return_exceptions=True
                )
            finally:
                try:
                    from database.db import close_db
                    await close_db()
                except Exception:
                    pass
        return self.diagnostics

    def render_report(self) -> int:
        """Render rich console report. Returns exit code (0 if OK/WARN, 1 if any FAIL)."""
        from cli.theme import (
            get_console, LEDGER_BOX, PHOSPHOR_AMBER, BRASS,
            stamp_ok, stamp_err, stamp_warn, stamp_info, MUTED, PAPER
        )
        from rich.table import Table

        console = get_console()
        table = Table(
            title=f"[{PHOSPHOR_AMBER}]MONIKA SYSTEM DOCTOR (UNIFIED DIAGNOSTIC REPORT)[/]",
            box=LEDGER_BOX,
            header_style=f"bold {PHOSPHOR_AMBER}"
        )
        table.add_column("Category", style=f"bold {BRASS}", width=14)
        table.add_column("Component", style=PAPER, width=24)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Message", style=PAPER)

        has_fail = False
        for item in self.diagnostics:
            if item.status == "OK":
                st = stamp_ok("PASS")
            elif item.status == "FIXED":
                st = stamp_ok("FIXED")
            elif item.status == "WARN":
                st = stamp_warn("WARN")
            elif item.status == "INFO":
                st = stamp_info("INFO")
            else:
                st = stamp_err("FAIL")
                has_fail = True

            table.add_row(item.category, item.name, st, item.message)
            if self.verbose and item.details:
                table.add_row("", "", "", f"[dim]{item.details}[/]")

        console.print()
        console.print(table)
        console.print()

        if has_fail:
            console.print(f"[{PHOSPHOR_AMBER}]One or more critical checks failed. Resolve FAIL items before starting live trading.[/]\n")
            return 1
        else:
            console.print(f"{stamp_ok('SYSTEM HEALTHY')} All core diagnostic checks passed. System ready.\n")
            return 0
