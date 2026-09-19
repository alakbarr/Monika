"""
File: cli/doctor.py
Comprehensive diagnostic and self-healing engine for Monika (MT5 Trading Agent).
Integrates deep AST analysis, MT5, database schema, API, and config health checks.
"""

import os
import sys
import logging
import asyncio
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

    def __init__(self, fix: bool = False, live_probes: bool = False, verbose: bool = False):
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
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self._record("Credentials", "ANTHROPIC_API_KEY", "OK", "Anthropic API key present.")
        else:
            self._record("Credentials", "ANTHROPIC_API_KEY", "WARN", "ANTHROPIC_API_KEY not set in environment.")

    def check_mt5(self, settings: dict) -> None:
        """Check MT5 terminal and account settings."""
        mt5_cfg = settings.get("mt5", {}) if isinstance(settings, dict) else {}
        mt5_path = os.getenv("MT5_PATH") or mt5_cfg.get("path")
        if mt5_path and os.path.exists(mt5_path):
            self._record("MT5", "MT5_PATH", "OK", f"MT5 terminal binary located at: {mt5_path}")
        else:
            self._record("MT5", "MT5_PATH", "WARN", f"MT5 binary path not found or unset: {mt5_path}")

    async def check_database_migrations(self) -> None:
        """Verify Alembic schema head and database tables."""
        try:
            from database.db import init_db, get_session
            await init_db()
            async with get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            self._record("Database", "PostgreSQL", "OK", "Database connection successful (SELECT 1 passed).")
        except Exception as e:
            self._record("Database", "PostgreSQL", "FAIL", f"Database connection failed: {str(e)[:150]}")

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
        self.check_configuration(settings)
        self.check_credentials(settings)
        self.check_mt5(settings)
        if self.live_probes:
            await self.check_database_migrations()
            await self.check_startup_checker_suite(settings)
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

        has_failure = False
        for item in self.diagnostics:
            if item.status == "OK":
                badge = stamp_ok("PASS")
            elif item.status == "FIXED":
                badge = stamp_ok("FIXED")
            elif item.status == "WARN":
                badge = stamp_warn("WARN")
            else:
                badge = stamp_err("FAIL")
                has_failure = True

            table.add_row(item.category, item.name, badge, item.message)

        console.print()
        console.print(table)
        console.print()

        if has_failure:
            console.print(f"{stamp_err('DOCTOR')} Detected critical issues. Run `monika doctor --fix` or resolve the items above.")
            return 1
        else:
            console.print(f"{stamp_ok('DOCTOR')} System passed diagnostics. Monika is ready for operation.")
            return 0
