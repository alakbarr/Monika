"""
File: cli/setup_wizard.py
Interactive onboarding setup wizard for Monika (MT5 Trading Agent).
Provides guided terminal prompts to configure credentials, MT5 settings, and risk limits.
"""

import os
import sys
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("TradingAgent.CLI.SetupWizard")


class SetupWizard:
    """Guided terminal configuration wizard with non-interactive safety guards and comment-preserving atomic writes."""

    def __init__(self, settings_path: Optional[str] = None):
        self.settings_path = settings_path or "config/settings.yaml"

    def run_wizard(self) -> bool:
        from cli.theme import (
            get_console, LEDGER_BOX, PHOSPHOR_AMBER, BRASS,
            stamp_ok, stamp_err, stamp_warn, stamp_info, MUTED, PAPER
        )
        from rich.prompt import Prompt, Confirm
        from config.atomic_writer import AtomicConfigWriter

        console = get_console()
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]       MONIKA (MT5 TRADING AGENT) — SETUP WIZARD             [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        # Headless check
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            console.print(f"{stamp_warn('HEADLESS')} Non-interactive environment detected. Use `monika config set` to configure.")
            return False

        console.print(f"{stamp_info('STEP 1/4')} [bold {BRASS}]Trading Mode & Safety Guards[/]")
        is_paper = Confirm.ask("Enable Paper Trading Mode (mandatory for initial evaluation)?", default=True)
        max_risk = float(Prompt.ask("Max risk per trade percent (e.g. 1.0)", default="1.0"))
        max_daily_dd = float(Prompt.ask("Max daily drawdown percent (e.g. 3.0)", default="3.0"))

        console.print(f"\n{stamp_info('STEP 2/4')} [bold {BRASS}]MetaTrader 5 (MT5) Terminal Configuration[/]")
        account = Prompt.ask("MT5 Account Number (leave blank to keep current env)", default="")
        server = Prompt.ask("MT5 Broker Server name (e.g. MetaQuotes-Demo)", default="MetaQuotes-Demo")
        mt5_path = Prompt.ask("MT5 terminal executable path (or blank for auto-detect)", default="")

        console.print(f"\n{stamp_info('STEP 3/4')} [bold {BRASS}]Model Architecture Preset[/]")
        console.print(f"[{MUTED}]Pilih preset alokasi model agar seluruh 30+ task role terkonfigurasi optimal:[/{MUTED}]")
        console.print(f"  1. [bold {BRASS}]Budget / High-Efficiency Mode[/]: Gemini 3.8 Flash / Flash-Lite (hemat token, kecepatan tinggi)")
        console.print(f"  2. [bold {BRASS}]Institutional Performance Mode[/]: Claude 3.5/3.7 Sonnet (Stage 1/2) + Gemini 3.8 Flash (Subagents)")
        console.print(f"  3. [bold {BRASS}]Keep Current Roles[/]: Pertahankan konfigurasi role di settings.yaml saat ini")

        preset_choice = Prompt.ask("Pilih preset (1/2/3)", choices=["1", "2", "3"], default="1")

        console.print(f"\n{stamp_info('STEP 4/4')} [bold {BRASS}]Applying Configuration[/]")

        update_dict: Dict[str, Any] = {
            "paper_trading": {"enabled": is_paper},
            "trading": {
                "risk": {
                    "risk_percent_per_trade": max_risk,
                    "max_daily_drawdown_percent": max_daily_dd,
                }
            }
        }

        if account:
            os.environ["MT5_ACCOUNT"] = str(account)
        if server:
            os.environ["MT5_SERVER"] = str(server)
        if mt5_path:
            os.environ["MT5_PATH"] = str(mt5_path)

        # Apply Model Presets without wiping task_roles
        if preset_choice == "1":
            # Budget mode: map key roles to gemini-3.8-flash
            update_dict["llm"] = {
                "task_roles": {
                    "stage1_fundamental": {"primary": "gemini-3.8-flash"},
                    "stage2_per_asset_primary": {"primary": "gemini-3.8-flash"},
                    "stage2_per_asset_secondary": {"primary": "gemini-3.8-flash"},
                    "debate_judge": {"primary": "gemini-3.8-flash"},
                    "trade_reflection": {"primary": "gemini-3.8-flash"},
                }
            }
        elif preset_choice == "2":
            # Performance mode: sonnet for critical reasoning, gemini-3.8-flash for reflection/subagents
            update_dict["llm"] = {
                "task_roles": {
                    "stage1_fundamental": {"primary": "claude-3-5-sonnet"},
                    "stage2_per_asset_primary": {"primary": "claude-3-5-sonnet"},
                    "stage2_per_asset_secondary": {"primary": "claude-3-5-sonnet"},
                    "debate_judge": {"primary": "claude-3-5-sonnet"},
                    "trade_reflection": {"primary": "gemini-3.8-flash"},
                }
            }

        try:
            AtomicConfigWriter.update_in_place(self.settings_path, update_dict)
            console.print(f"\n{stamp_ok('SUCCESS')} Configuration atomically updated in {self.settings_path} (comments preserved).")
            console.print(f"{stamp_info('NEXT')} Run `monika doctor --live` to verify environment and live API connectivity.")
            return True
        except Exception as e:
            console.print(f"\n{stamp_err('FAILED')} Failed to update settings: {e}")
            return False
