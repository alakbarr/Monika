"""
File: cli/onboarding_trader.py
Trader onboarding personalization for Monika (MT5 Trading Agent).
Captures trader identity, style, risk parameters, and operational focus,
persisting them to Layer 0 memory (TRADING_SOUL.md) and profile state.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("TradingAgent.CLI.Onboarding")


@dataclass
class TraderProfile:
    trader_name: str
    trading_style: str  # scalper, day_trader, swing_trader
    risk_appetite: str  # conservative, moderate, aggressive
    risk_pct_per_trade: float
    max_daily_loss_pct: float
    primary_symbols: List[str]
    session_focus: List[str]
    notes: str = ""


class TraderOnboarding:
    """Manages trader personality discovery and persistent memory synchronization."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.profile_file = self.base_dir / "data" / "memory" / "trader_profile.json"
        self.soul_file = self.base_dir / "config" / "TRADING_SOUL.md"

    def run_interview(self) -> TraderProfile:
        """Executes terminal interview to establish trader persona."""
        from cli.theme import get_console, PHOSPHOR_AMBER, BRASS, stamp_ok, stamp_info, MUTED
        from rich.prompt import Prompt

        console = get_console()
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]       MONIKA — TRADER ONBOARDING & PERSONALIZATION         [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        console.print(f"{stamp_info('PROFILE')} Mari definisikan persona dan filosofi trading Anda.")

        name = Prompt.ask("Nama atau Call-sign Trader", default="Operator")

        console.print(f"\n[bold {BRASS}]Gaya Trading Utama:[/] ")
        console.print("  1. Intraday Scalper (M5 - M15, target 10-25 pips)")
        console.print("  2. Day Trader (M15 - H1, target 30-75 pips)")
        console.print("  3. Swing Trader (H1 - H4/D1, target 100+ pips)")
        style_choice = Prompt.ask("Pilih gaya trading (1/2/3)", choices=["1", "2", "3"], default="2")
        style_map = {"1": "scalper", "2": "day_trader", "3": "swing_trader"}
        trading_style = style_map[style_choice]

        console.print(f"\n[bold {BRASS}]Toleransi Risiko & Drawdown:[/] ")
        console.print("  1. Konservatif (Risk 0.5% / trade, Max Daily DD 2.0%)")
        console.print("  2. Moderat (Risk 1.0% / trade, Max Daily DD 3.0%)")
        console.print("  3. Agresif (Risk 1.5% / trade, Max Daily DD 5.0%)")
        risk_choice = Prompt.ask("Pilih profil risiko (1/2/3)", choices=["1", "2", "3"], default="2")

        if risk_choice == "1":
            risk_appetite = "conservative"
            risk_pct = 0.5
            daily_dd = 2.0
        elif risk_choice == "3":
            risk_appetite = "aggressive"
            risk_pct = 1.5
            daily_dd = 5.0
        else:
            risk_appetite = "moderate"
            risk_pct = 1.0
            daily_dd = 3.0

        syms_input = Prompt.ask(
            "Fokus Pasang Simbol (pisahkan koma)",
            default="XAUUSD, EURUSD, GBPUSD"
        )
        primary_symbols = [s.strip().upper() for s in syms_input.split(",") if s.strip()]

        sessions_input = Prompt.ask(
            "Sesi Trading Prioritas (misal: London, New York)",
            default="London, New York"
        )
        session_focus = [s.strip() for s in sessions_input.split(",") if s.strip()]

        profile = TraderProfile(
            trader_name=name,
            trading_style=trading_style,
            risk_appetite=risk_appetite,
            risk_pct_per_trade=risk_pct,
            max_daily_loss_pct=daily_dd,
            primary_symbols=primary_symbols,
            session_focus=session_focus
        )

        self.save_profile(profile)
        self.sync_to_trading_soul(profile)

        console.print(f"\n{stamp_ok('ONBOARDED')} Profil trader berhasil disimpan dan disinkronkan ke TRADING_SOUL.md!")
        return profile

    def save_profile(self, profile: TraderProfile) -> None:
        """Saves profile to local JSON storage."""
        self.profile_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profile_file, "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, indent=2)
        logger.info(f"Saved trader profile to {self.profile_file}")

    def load_profile(self) -> Optional[TraderProfile]:
        """Loads existing trader profile if present."""
        if not self.profile_file.exists():
            return None
        try:
            with open(self.profile_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TraderProfile(**data)
        except Exception as err:
            logger.warning(f"Failed to load trader profile: {err}")
            return None

    def sync_to_trading_soul(self, profile: TraderProfile) -> None:
        """Injects trader identity into TRADING_SOUL.md under dedicated section."""
        header_marker = "## Trader Persona & Operational Context"
        persona_content = (
            f"\n{header_marker}\n"
            f"- **Primary Trader:** {profile.trader_name}\n"
            f"- **Trading Style:** {profile.trading_style.replace('_', ' ').title()}\n"
            f"- **Risk Appetite:** {profile.risk_appetite.title()} "
            f"(Risk/Trade: {profile.risk_pct_per_trade}%, Max Daily DD: {profile.max_daily_loss_pct}%)\n"
            f"- **Primary Symbols:** {', '.join(profile.primary_symbols)}\n"
            f"- **Session Focus:** {', '.join(profile.session_focus)}\n"
        )

        if not self.soul_file.exists():
            self.soul_file.parent.mkdir(parents=True, exist_ok=True)
            self.soul_file.write_text(f"# TRADING SOUL\n{persona_content}", encoding="utf-8")
            return

        current_text = self.soul_file.read_text(encoding="utf-8")
        if header_marker in current_text:
            # Replace existing section up to next header or EOF
            parts = current_text.split(header_marker)
            rest = parts[1]
            next_header = rest.find("\n## ")
            after = rest[next_header:] if next_header != -1 else ""
            new_text = parts[0].rstrip() + persona_content + after.lstrip()
        else:
            new_text = current_text.rstrip() + "\n" + persona_content

        self.soul_file.write_text(new_text, encoding="utf-8")
        logger.info(f"Synchronized trader profile to {self.soul_file}")
