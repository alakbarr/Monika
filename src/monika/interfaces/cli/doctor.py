# ==============================================================================
# Package: monika.interfaces.cli
# File: doctor.py
# Description: Comprehensive CLI diagnostic and self-healing telemetry presentation.
# ==============================================================================

"""
CLI presentation layer for Monika System Doctor.
Delegates diagnostic checks to `monika.core.telemetry.doctor.SystemDoctor` and renders
rich console tables and stamps.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from monika.core.telemetry.doctor import (
    DiagnosticItem,
    SystemDoctor as CoreSystemDoctor,
)
from monika.interfaces.cli.theme import (
    BRASS,
    LEDGER_BOX,
    PAPER,
    PHOSPHOR_AMBER,
    get_console,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

logger = logging.getLogger("Monika.Interfaces.CLI.Doctor")


class SystemDoctor(CoreSystemDoctor):
    """CLI specialization of SystemDoctor that renders rich terminal reports."""

    def render_report(self) -> int:
        """Render rich console report. Returns exit code (0 if OK/WARN, 1 if any FAIL)."""
        from rich.table import Table

        console = get_console()
        table = Table(
            title=f"[{PHOSPHOR_AMBER}]MONIKA SYSTEM DOCTOR (UNIFIED DIAGNOSTIC REPORT)[/]",
            box=LEDGER_BOX,
            header_style=f"bold {PHOSPHOR_AMBER}",
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
            console.print(
                f"[{PHOSPHOR_AMBER}]One or more critical checks failed. Resolve FAIL items before starting live trading.[/]\n"
            )
            return 1
        else:
            console.print(f"{stamp_ok('SYSTEM HEALTHY')} All core diagnostic checks passed. System ready.\n")
            return 0


__all__ = ["DiagnosticItem", "SystemDoctor"]
