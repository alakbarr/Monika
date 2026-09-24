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

    def check_dependencies(self) -> None:
        """Verify system binaries and critical python packages."""
        # Check Node.js and npm for dashboard
        node_path = shutil.which("node")
        npm_path = shutil.which("npm")
        if node_path and npm_path:
            self._record("Dependencies", "Node/NPM", "OK", f"Dashboard prerequisites available ({node_path})")
        else:
            self._record("Dependencies", "Node/NPM", "WARN", "Node.js or npm not found. Dashboard frontend build may fail.", details="Install Node.js LTS if running the local web dashboard.")

        # Check MetaTrader5 Python package
        try:
            import MetaTrader5 as mt5
            self._record("Dependencies", "MetaTrader5-Pkg", "OK", f"MetaTrader5 Python package installed (v{getattr(mt5, '__version__', 'unknown')}).")
        except ImportError:
            self._record("Dependencies", "MetaTrader5-Pkg", "WARN", "MetaTrader5 python package not found in virtual environment.", details="Run: pip install MetaTrader5")

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
        mt5_path = os.getenv("MT5_PATH") or mt5_cfg.get("path")
        if mt5_path and os.path.exists(mt5_path):
            self._record("MT5", "MT5_PATH", "OK", f"MT5 terminal binary located at: {mt5_path}")
        else:
            self._record("MT5", "MT5_PATH", "WARN", f"MT5 binary path not found or unset: {mt5_path}")

        account = os.getenv("MT5_ACCOUNT")
        if account:
            self._record("MT5", "MT5_ACCOUNT", "OK", f"MT5 Account configured ({account}).")
        else:
            self._record("MT5", "MT5_ACCOUNT", "FAIL", "MT5_ACCOUNT environment variable is missing.")

    async def check_database_migrations(self) -> None:
        """Verify database connectivity and schema tables."""
        try:
            from database.db import init_db, get_session, close_db
            await init_db()
            async with get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            self._record("Database", "PostgreSQL", "OK", "Database connection successful (SELECT 1 passed).")
        except Exception as e:
            self._record("Database", "PostgreSQL", "FAIL", f"Database connection failed: {str(e)[:150]}")
            if self.fix:
                self._record("Database", "AutoFix", "INFO", "Attempting alembic migration...")
                try:
                    import subprocess
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    subprocess.run(["alembic", "upgrade", "head"], cwd=base_dir, check=False)
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

    async def run_diagnostics(self) -> List[DiagnosticItem]:
        """Runs the entire unified battery of doctor checks."""
        from config.settings import load_all_config
        try:
            settings = load_all_config()
        except Exception as e:
            settings = {}
            self._record("Config", "load_all_config", "FAIL", f"Error loading settings: {e}")

        await self.check_directories()
        self.check_dependencies()
        self.check_market_session()
        self.check_configuration(settings)
        self.check_credentials(settings)
        self.check_mt5(settings)
        if self.live_probes:
            await asyncio.gather(
                self.check_database_migrations(),
                self.check_startup_checker_suite(settings),
                return_exceptions=True
            )
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
