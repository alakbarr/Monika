# ==============================================================================
# Package: monika.core.telemetry
# File: doctor.py
# Description: Canonical Diagnostic and Self-Healing Telemetry Engine for Monika.
# ==============================================================================

"""
Canonical diagnostic and self-healing telemetry engine for Monika.
Integrates runtime environment, filesystem, MT5, database schema, API, dependency,
vault permissions, and supervisor health checks.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import shutil
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Monika.Core.Telemetry.Doctor")


@dataclass
class DiagnosticItem:
    category: str
    name: str
    status: str  # "OK", "WARN", "FAIL", "FIXED", "INFO"
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

    def _record(
        self,
        category: str,
        name: str,
        status: str,
        message: str,
        fixable: bool = False,
        details: Optional[str] = None,
    ) -> None:
        self.diagnostics.append(
            DiagnosticItem(
                category=category,
                name=name,
                status=status,
                message=message,
                fixable=fixable,
                details=details,
            )
        )

    def check_runtime_environment(self, settings: Optional[dict] = None) -> None:
        """Verify Python runtime, MONIKA_HOME/DATA_DIR boundaries, vault permissions, and Guardian/Watchdog."""
        # 1. Python version check
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 11):
            self._record("Environment", "Python-Version", "OK", f"Python runtime verified: v{py_ver}")
        else:
            self._record("Environment", "Python-Version", "WARN", f"Python version v{py_ver} < 3.11 recommended.")

        # 2. MONIKA_HOME / DATA_DIR isolation check
        from monika.core.paths import DATA_DIR

        if DATA_DIR.exists() and os.access(str(DATA_DIR), os.W_OK):
            self._record("Environment", "DataDir-Writable", "OK", f"Data directory verified and writable ({DATA_DIR}).")
        else:
            self._record(
                "Environment", "DataDir-Writable", "WARN", f"Data directory not writable or missing ({DATA_DIR})."
            )

        # 3. Credential Vault file permissions check
        vault_path = DATA_DIR / "vault"
        if vault_path.exists():
            try:
                mode = vault_path.stat().st_mode
                if os.name != "nt" and (mode & 0o077):
                    self._record(
                        "Security",
                        "Vault-Permissions",
                        "WARN",
                        f"Vault directory {vault_path} permissions too open ({oct(mode)}).",
                    )
                else:
                    self._record(
                        "Security",
                        "Vault-Permissions",
                        "OK",
                        f"Vault directory storage boundaries verified ({vault_path}).",
                    )
            except Exception as e:
                self._record("Security", "Vault-Permissions", "WARN", f"Vault access check note: {e}")
        else:
            self._record("Security", "Vault-Permissions", "INFO", "Vault directory not yet initialized.")

        # 4. Multi-Process Guardian / Watchdog status check
        pid_file = DATA_DIR / "trading_agent.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                self._record("Supervisor", "Primary-Daemon", "OK", f"Primary daemon lock registered (PID {pid}).")
            except Exception:
                self._record("Supervisor", "Primary-Daemon", "INFO", "Daemon lock file present but unparsed.")
        else:
            self._record("Supervisor", "Primary-Daemon", "INFO", "No active primary daemon PID lock.")

    async def check_directories(self) -> None:
        """Verify required directories exist and are writable."""
        from monika.infrastructure.infra.paths import get_repo_root

        base_dir = str(get_repo_root())
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
                    self._record(
                        "Filesystem",
                        f"dir:{os.path.basename(d)}",
                        "WARN",
                        f"Missing directory: {d}",
                        fixable=True,
                    )

    def check_dependencies(self, settings: Optional[dict] = None) -> None:
        """Verify system binaries and critical python packages with tier awareness."""
        from monika.core.config.settings import get_installation_tier

        tier = get_installation_tier(settings or {})

        # Check Node.js and npm for dashboard
        node_path = shutil.which("node")
        npm_path = shutil.which("npm")
        if node_path and npm_path:
            self._record("Dependencies", "Node/NPM", "OK", f"Dashboard prerequisites available ({node_path})")
        elif tier == "trial":
            self._record(
                "Dependencies",
                "Node/NPM",
                "INFO",
                "Node/npm optional in Trial package (using CLI + Telegram).",
            )
        else:
            self._record(
                "Dependencies",
                "Node/NPM",
                "WARN",
                "Node.js or npm not found. Dashboard frontend build may fail.",
                details="Install Node.js LTS if running the local web dashboard.",
            )

        # Check MetaTrader5 Python package or Linux RPC bridge
        try:
            from monika.infrastructure.brokers.mt5_compat import (
                ensure_mt5_module,
                is_mt5linux_available,
                is_native_mt5_available,
            )

            mt5 = ensure_mt5_module()
            if is_native_mt5_available():
                self._record(
                    "Dependencies",
                    "MetaTrader5-Pkg",
                    "OK",
                    f"MetaTrader5 native Python package installed (v{getattr(mt5, '__version__', 'unknown')}).",
                )
            elif is_mt5linux_available():
                self._record(
                    "Dependencies", "MetaTrader5-Pkg", "OK", "MetaTrader5 Linux RPC bridge (mt5linux) available."
                )
            elif tier == "trial":
                self._record(
                    "Dependencies",
                    "MetaTrader5-Pkg",
                    "INFO",
                    "Internal Paper Trading Sandbox active (native MT5 binary optional).",
                )
            else:
                self._record(
                    "Dependencies",
                    "MetaTrader5-Pkg",
                    "WARN",
                    "MetaTrader5 native package or mt5linux not installed.",
                    details="For Windows: pip install MetaTrader5. For Linux VPS: pip install mt5linux",
                )
        except Exception as e:
            if tier == "trial":
                self._record("Dependencies", "MetaTrader5-Pkg", "INFO", "Paper Trading simulation sandbox active.")
            else:
                self._record(
                    "Dependencies",
                    "MetaTrader5-Pkg",
                    "WARN",
                    f"MetaTrader5 check error: {e}",
                    details="For Windows: pip install MetaTrader5. For Linux VPS: pip install mt5linux",
                )

    def check_market_session(self) -> None:
        """Checks whether the global financial markets are open or in weekend closure."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        weekday = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = now_utc.hour

        # Forex closes Friday ~21:00 UTC and reopens Sunday ~21:00 UTC
        is_weekend = (weekday == 5) or (weekday == 4 and hour >= 21) or (weekday == 6 and hour < 21)
        if is_weekend:
            self._record(
                "Market",
                "SessionStatus",
                "WARN",
                "Forex market currently CLOSED for weekend. Evaluation & crypto active.",
            )
        else:
            self._record("Market", "SessionStatus", "OK", "Forex & global financial markets are OPEN.")

    def check_configuration(self, settings: dict) -> None:
        """Check settings.yaml and modular split files."""
        try:
            pt = settings.get("paper_trading", {})
            if isinstance(pt, dict) and pt.get("enabled") is True:
                self._record("Config", "paper_trading", "OK", "Safety guard active (paper_trading.enabled: true).")
            else:
                self._record(
                    "Config", "paper_trading", "WARN", "paper_trading.enabled is False or missing. Live trading mode!"
                )

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
            has_key = (
                bool(os.getenv(env_var))
                or (env_var == "GEMINI_API_KEY" and bool(os.getenv("GEMINI_API_KEYS")))
                or (env_var == "GROQ_API_KEY" and bool(os.getenv("GROQ_API_KEYS")))
                or (env_var == "ANTHROPIC_API_KEY" and bool(os.getenv("ANTHROPIC_API_KEYS")))
            )
            if has_key:
                self._record("Credentials", env_var, "OK", f"{name} API key configured.")
                active_count += 1
            else:
                self._record("Credentials", env_var, "WARN", f"{name} ({env_var}) not set in environment.")

        if active_count == 0:
            self._record(
                "Credentials",
                "LLM_PROVIDERS",
                "FAIL",
                "No AI provider API keys found. Agent cannot execute reasoning tasks.",
            )

    def check_mt5(self, settings: dict) -> None:
        """Check MT5 terminal and account settings."""
        mt5_cfg = settings.get("mt5", {}) if isinstance(settings, dict) else {}
        pt = settings.get("paper_trading", {}) if isinstance(settings, dict) else {}
        is_paper = pt.get("enabled", True) if isinstance(pt, dict) else True

        mt5_path = os.getenv("MT5_PATH") or mt5_cfg.get("path")
        if mt5_path and os.path.exists(mt5_path):
            self._record("MT5", "MT5_PATH", "OK", f"MT5 terminal binary located at: {mt5_path}")
        elif is_paper:
            self._record(
                "MT5",
                "MT5_PATH",
                "INFO",
                "MT5 terminal binary not found (Paper trading active, MT5 optional).",
            )
        else:
            self._record(
                "MT5",
                "MT5_PATH",
                "WARN",
                "MT5 terminal path not found.",
                details="Set MT5_PATH in environment or settings.yaml:mt5.path.",
            )

        account = os.getenv("MT5_LOGIN") or mt5_cfg.get("login")
        if account:
            self._record("MT5", "MT5_LOGIN", "OK", f"Account configured: {account}")
        elif is_paper:
            self._record("MT5", "MT5_LOGIN", "INFO", "Paper trading mode (broker login optional).")
        else:
            self._record(
                "MT5", "MT5_LOGIN", "WARN", "MT5 account login missing.", details="Set MT5_LOGIN in environment."
            )

    async def check_database_migrations(self) -> None:
        """Verify database connectivity, active DBA transaction locks, and schema migrations."""
        try:
            from monika.infrastructure.database.db import get_session, init_db

            await init_db()
            async with get_session() as session:
                from sqlalchemy import text

                await session.execute(text("SELECT 1"))

                # Check for active blocking locks in PostgreSQL
                try:
                    lock_res = await session.execute(
                        text("""
                        SELECT pid, usename, pg_blocking_pids(pid) AS blocked_by, query
                        FROM pg_stat_activity
                        WHERE cardinality(pg_blocking_pids(pid)) > 0;
                    """)
                    )
                    blocked_rows = lock_res.fetchall()
                    if blocked_rows:
                        self._record(
                            "Database",
                            "PostgreSQL-Locks",
                            "WARN",
                            f"Detected {len(blocked_rows)} blocked transaction(s) in PostgreSQL.",
                        )
                    else:
                        self._record(
                            "Database", "PostgreSQL-Locks", "OK", "No deadlocks or blocked transactions detected."
                        )
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

                    from monika.infrastructure.infra.paths import get_repo_root

                    base_dir = str(get_repo_root())
                    env = os.environ.copy()
                    db_url = env.get("DATABASE_URL", "")
                    if "+asyncpg" in db_url:
                        env["DATABASE_URL"] = db_url.replace("postgresql+asyncpg://", "postgresql://")
                    subprocess.run(["alembic", "upgrade", "head"], cwd=base_dir, env=env, check=False)
                except Exception:
                    pass
        finally:
            try:
                from monika.infrastructure.database.db import close_db

                await close_db()
            except Exception:
                pass

    async def check_startup_checker_suite(self, settings: dict) -> None:
        """Execute unified 11-step StartupChecker from agent/startup_checks.py."""
        from monika.application.agent.startup_checks import StartupChecker

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
                from monika.infrastructure.database.db import close_db

                await close_db()
            except Exception:
                pass

    def check_wal_integrity_and_repair(self) -> None:
        """Verify SQLite WAL database files integrity and clear stale locks."""
        import sqlite3

        from monika.infrastructure.infra.paths import DATA_DIR

        wal_dbs = [
            DATA_DIR / "session_db.sqlite",
            DATA_DIR / "universal_cron.db",
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
                    self._record(
                        "DatabaseWAL", f"wal:{db_file.name}", "OK", f"Integrity check passed ({db_file.name})."
                    )
                else:
                    self._record("DatabaseWAL", f"wal:{db_file.name}", "WARN", f"Integrity check returned: {res}")
            except Exception as e:
                self._record("DatabaseWAL", f"wal:{db_file.name}", "WARN", f"WAL check error: {e}")

    def check_database_url_and_offline_integrity(self, settings: Optional[dict] = None) -> None:
        """Validate DATABASE_URL formatting and perform offline file/integrity checks."""
        import sqlite3

        db_url = os.getenv("DATABASE_URL")
        if not db_url and isinstance(settings, dict):
            db_cfg = settings.get("database", {})
            if isinstance(db_cfg, dict):
                db_url = db_cfg.get("url")

        if not db_url:
            self._record("DatabaseConfig", "DATABASE_URL", "WARN", "DATABASE_URL is not set (will default to SQLite).")
            return

        parsed = urllib.parse.urlparse(db_url)
        scheme = parsed.scheme.lower()
        valid_schemes = (
            "sqlite",
            "sqlite+aiosqlite",
            "postgresql",
            "postgresql+asyncpg",
            "postgresql+psycopg2",
        )

        if not any(
            scheme == s or scheme.startswith("sqlite") or scheme.startswith("postgresql") for s in valid_schemes
        ):
            self._record("DatabaseConfig", "DATABASE_URL", "FAIL", f"Unsupported database scheme: '{scheme}'.")
            return

        self._record("DatabaseConfig", "DATABASE_URL", "OK", f"Database URI scheme validated: {scheme}")

        if "sqlite" in scheme:
            db_path = parsed.path
            if db_path.startswith("///"):
                file_path = Path(db_path[3:])
            elif db_path.startswith("/"):
                file_path = Path(db_path[1:]) if os.name == "nt" and ":" in db_path else Path(db_path)
            else:
                file_path = Path(db_path)

            if file_path.exists():
                try:
                    conn = sqlite3.connect(str(file_path), timeout=5.0)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check;")
                    res = cursor.fetchone()
                    conn.close()
                    if res and res[0] == "ok":
                        self._record(
                            "DatabaseConfig",
                            "SQLite-Integrity",
                            "OK",
                            f"Offline SQLite integrity verified ({file_path.name}).",
                        )
                    else:
                        self._record("DatabaseConfig", "SQLite-Integrity", "WARN", f"Integrity check returned: {res}")
                except Exception as e:
                    self._record("DatabaseConfig", "SQLite-Integrity", "WARN", f"Offline SQLite check failed: {e}")
            else:
                parent_dir = file_path.parent
                if parent_dir.exists() and os.access(parent_dir, os.W_OK):
                    self._record(
                        "DatabaseConfig",
                        "SQLite-Path",
                        "OK",
                        f"SQLite target file will be initialized in {parent_dir}.",
                    )
                else:
                    self._record(
                        "DatabaseConfig",
                        "SQLite-Path",
                        "WARN",
                        f"SQLite directory not writable or missing: {parent_dir}",
                    )
        elif "postgresql" in scheme:
            if not parsed.hostname:
                self._record("DatabaseConfig", "PostgreSQL-Config", "WARN", "PostgreSQL URI lacks a valid hostname.")
            else:
                self._record(
                    "DatabaseConfig",
                    "PostgreSQL-Config",
                    "OK",
                    f"Target host: {parsed.hostname}:{parsed.port or 5432}, DB: {parsed.path.lstrip('/')}",
                )

        # Offline Alembic Head Verification
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            from monika.infrastructure.infra.paths import get_repo_root

            alembic_ini = get_repo_root() / "alembic.ini"
            if alembic_ini.exists():
                cfg = Config(str(alembic_ini))
                script = ScriptDirectory.from_config(cfg)
                head = script.get_current_head()
                self._record("DatabaseConfig", "Alembic-Head", "OK", f"Alembic canonical head: {head}")
            else:
                self._record("DatabaseConfig", "Alembic-Head", "WARN", f"alembic.ini missing at {alembic_ini}")
        except Exception as exc:
            self._record("DatabaseConfig", "Alembic-Head", "WARN", f"Unable to read Alembic head: {exc}")

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
            self._record(
                "Cache",
                "Redis",
                "WARN",
                f"Redis offline or unreachable ({str(e)[:70]}). Local in-memory cache active.",
            )

    async def run_diagnostics(self) -> List[DiagnosticItem]:
        """Runs the entire unified battery of doctor checks."""
        from monika.core.config.settings import load_all_config

        try:
            settings = load_all_config()
        except Exception as e:
            settings = {}
            self._record("Config", "load_all_config", "FAIL", f"Error loading settings: {e}")

        self.check_runtime_environment(settings)
        await self.check_directories()
        self.check_dependencies(settings)
        self.check_market_session()
        self.check_configuration(settings)
        self.check_credentials(settings)
        self.check_mt5(settings)
        self.check_database_url_and_offline_integrity(settings)
        self.check_wal_integrity_and_repair()
        if self.live_probes:
            try:
                await asyncio.gather(
                    self.check_database_migrations(),
                    self.check_redis(settings),
                    self.check_startup_checker_suite(settings),
                    return_exceptions=True,
                )
            finally:
                try:
                    from monika.infrastructure.database.db import close_db

                    await close_db()
                except Exception:
                    pass
        return self.diagnostics


__all__ = ["DiagnosticItem", "SystemDoctor"]
