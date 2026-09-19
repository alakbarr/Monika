"""
File: cli/setup_wizard.py
Interactive onboarding setup wizard for Monika (MT5 Trading Agent).
Provides guided terminal prompts to configure credentials, MT5 settings, and risk limits.
"""

import os
import sys
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("TradingAgent.CLI.SetupWizard")


class SetupWizard:
    """Guided terminal configuration wizard with non-interactive safety guards."""

    def __init__(self, settings_path: Optional[str] = None):
        self.settings_path = settings_path or "config/settings.yaml"

    def run_wizard(self) -> bool:
        from cli.theme import (
            get_console, LEDGER_BOX, PHOSPHOR_AMBER, BRASS,
            stamp_ok, stamp_err, stamp_warn, stamp_info, MUTED, PAPER
        )
        from rich.prompt import Prompt, Confirm

        console = get_console()
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]       MONIKA (MT5 TRADING AGENT) — SETUP WIZARD             [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        # Headless check
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            console.print(f"{stamp_warn('HEADLESS')} Non-interactive environment detected. Use `monika config set` to configure.")
            return False

        console.print(f"{stamp_info('STEP 1/3')} [bold {BRASS}]Trading Mode & Safety Guards[/]")
        is_paper = Confirm.ask("Enable Paper Trading Mode (highly recommended for evaluation)?", default=True)
        max_risk = float(Prompt.ask("Max risk per trade percent (e.g. 1.0)", default="1.0"))
        max_daily_dd = float(Prompt.ask("Max daily drawdown percent (e.g. 3.0)", default="3.0"))

        console.print(f"\n{stamp_info('STEP 2/3')} [bold {BRASS}]MetaTrader 5 (MT5) Terminal Configuration[/]")
        account = Prompt.ask("MT5 Account Number (leave blank to configure later)", default="")
        server = Prompt.ask("MT5 Broker Server name (e.g. MetaQuotes-Demo)", default="MetaQuotes-Demo")
        mt5_path = Prompt.ask("MT5 terminal executable path (or blank for auto-detect)", default="")

        console.print(f"\n{stamp_info('STEP 3/3')} [bold {BRASS}]Primary AI Model Configuration[/]")
        provider = Prompt.ask("Primary LLM Provider", choices=["anthropic", "gemini", "openai", "groq"], default="anthropic")
        model = Prompt.ask("Primary Model Name", default="claude-3-5-sonnet-20241022" if provider == "anthropic" else "gemini-2.0-flash")

        # Save to settings.yaml
        try:
            from config.settings import load_settings
            try:
                cfg = load_settings(path=self.settings_path, validate=False)
            except Exception:
                cfg = {}

            if "trading" not in cfg or not isinstance(cfg["trading"], dict):
                cfg["trading"] = {}
            if "risk" not in cfg["trading"] or not isinstance(cfg["trading"]["risk"], dict):
                cfg["trading"]["risk"] = {}
            cfg["trading"]["risk"]["max_risk_per_trade_percent"] = max_risk
            cfg["trading"]["risk"]["max_daily_drawdown_percent"] = max_daily_dd

            cfg["paper_trading"] = {"enabled": is_paper}

            if "llm" not in cfg or not isinstance(cfg["llm"], dict):
                cfg["llm"] = {}
            if "task_roles" not in cfg["llm"] or not isinstance(cfg["llm"]["task_roles"], dict):
                cfg["llm"]["task_roles"] = {}
            cfg["llm"]["task_roles"]["general"] = {"provider": provider, "model": model}

            with open(self.settings_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

            console.print(f"\n{stamp_ok('SUCCESS')} Configuration saved to {self.settings_path}.")
            console.print(f"{stamp_info('NEXT')} Run `monika doctor` to verify your environment.")
            return True
        except Exception as e:
            console.print(f"\n{stamp_err('FAILED')} Failed to save settings: {e}")
            return False
