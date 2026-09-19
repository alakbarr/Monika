"""
File: cli/doctor.py
Comprehensive diagnostic and self-healing engine for Monika (MT5 Trading Agent).
Provides deep MT5, database, API, and config health checks.
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

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
    """Performs deep environmental and functional sanity checks with optional auto-fix."""

    def __init__(self, fix: bool = False, verbose: bool = False):
        self.fix = fix
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

    def check_configuration(self) -> None:
        """Check settings.yaml and modular split files."""
        from config.settings import load_settings, load_settings_with_lkg
        try:
            cfg = load_settings(validate=False)
            self._record("Config", "settings.yaml", "OK", "Configuration file parsed successfully.")

            # Check paper_trading requirement
            pt = cfg.get("paper_trading", {})
            if isinstance(pt, dict) and pt.get("enabled") is True:
                self._record("Config", "paper_trading", "OK", "Safety guard active (paper_trading.enabled: true).")
            else:
                self._record("Config", "paper_trading", "WARN", "paper_trading.enabled is False or missing. Live trading mode!")

            # Check LLM routing
            llm_cfg = cfg.get("llm", {})
            roles = llm_cfg.get("task_roles", {})
            if roles:
                self._record("Config", "llm.task_roles", "OK", f"{len(roles)} task roles mapped in configuration.")
            else:
                self._record("Config", "llm.task_roles", "WARN", "No task_roles defined in llm configuration.")

        except Exception as e:
            self._record("Config", "settings.yaml", "FAIL", f"Configuration parsing error: {e}")

    def check_api_keys(self) -> None:
        """Check presence of essential environment variables."""
        required = ["ANTHROPIC_API_KEY", "DATABASE_URL"]
        recommended = ["GEMINI_API_KEY", "OPENAI_API_KEY", "FINNHUB_API_KEY", "FRED_API_KEY"]

        for key in required:
            val = os.environ.get(key)
            if val and len(val.strip()) > 4:
                self._record("Credentials", key, "OK", f"{key} is configured.")
            else:
                self._record("Credentials", key, "FAIL", f"Required environment variable {key} is missing or empty.")

        for key in recommended:
            val = os.environ.get(key)
            if val and len(val.strip()) > 4:
                self._record("Credentials", key, "OK", f"{key} is configured.")
            else:
                self._record("Credentials", key, "WARN", f"Optional recommended variable {key} is not set.")

    def check_mt5_environment(self) -> None:
        """Check MT5 terminal paths and environment."""
        mt5_path = os.environ.get("MT5_PATH")
        if not mt5_path:
            self._record("MT5", "MT5_PATH", "WARN", "MT5_PATH not set in environment (required for MT5 terminal binding).")
        elif os.path.exists(mt5_path):
            self._record("MT5", "MT5_PATH", "OK", f"Terminal executable found at {mt5_path}")
        else:
            self._record("MT5", "MT5_PATH", "WARN", f"MT5_PATH is set ({mt5_path}) but executable does not exist.")

        account = os.environ.get("MT5_ACCOUNT")
        server = os.environ.get("MT5_SERVER")
        if account and server:
            self._record("MT5", "MT5_ACCOUNT", "OK", f"Account #{account} on {server}")
        else:
            self._record("MT5", "MT5_ACCOUNT", "WARN", "MT5_ACCOUNT or MT5_SERVER missing.")

    async def check_database(self) -> None:
        """Check database connectivity and tables."""
        try:
            from database.db import init_db, get_session
            await init_db()
            async with get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            self._record("Database", "PostgreSQL", "OK", "Database connection successful (SELECT 1 passed).")
        except Exception as e:
            self._record("Database", "PostgreSQL", "FAIL", f"Database connection failed: {str(e)[:150]}")

    async def run_diagnostics(self) -> List[DiagnosticItem]:
        """Runs the entire battery of doctor checks."""
        await self.check_directories()
        self.check_configuration()
        self.check_api_keys()
        self.check_mt5_environment()
        await self.check_database()
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
            title=f"[{PHOSPHOR_AMBER}]MONIKA SYSTEM DOCTOR (DIAGNOSTIC REPORT)[/]",
            box=LEDGER_BOX,
            header_style=f"bold {PHOSPHOR_AMBER}"
        )
        table.add_column("Category", style=f"bold {BRASS}", width=14)
        table.add_column("Component", style=PAPER, width=22)
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
            console.print(f"{stamp_err('DOCTOR')} Detected critical failures. Resolve the issues above or run with '--fix'.")
            return 1
        else:
            console.print(f"{stamp_ok('DOCTOR')} System passed diagnostics. Monika is ready for operation.")
            return 0
