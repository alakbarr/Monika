"""
File: cli/setup_wizard.py
Interactive onboarding setup wizard for Monika (MT5 Trading Agent).
Provides guided terminal prompts to configure credentials, MT5 settings, live broker tests,
database connectivity, and risk limits with atomic comment-preserving persistence.
"""

import os
import sys
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("TradingAgent.CLI.SetupWizard")


class SetupWizard:
    """Guided terminal configuration wizard with live broker handshake and atomic persistence."""

    def __init__(self, settings_path: Optional[str] = None):
        self.settings_path = settings_path or "config/settings.yaml"

    def _test_mt5_connection(self, account: str, password: str, server: str, path: str) -> bool:
        """Performs live MT5 terminal handshake and checks AlgoTrading status."""
        from cli.theme import get_console, stamp_ok, stamp_err, stamp_warn, stamp_info, BRASS, PAPER, MUTED
        console = get_console()
        try:
            import MetaTrader5 as mt5
        except ImportError:
            console.print(f"{stamp_err('MT5 PKG')} MetaTrader5 Python package is not installed.")
            return False

        init_kwargs: Dict[str, Any] = {}
        if path and os.path.exists(path):
            init_kwargs["path"] = path

        console.print(f"{stamp_info('PROBE')} Initializing MetaTrader 5 terminal...")
        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            console.print(f"{stamp_err('INIT FAIL')} MT5 initialize failed: {err}")
            return False

        if account and password:
            try:
                acc_num = int(account)
                authorized = mt5.login(login=acc_num, password=password, server=server)
                if not authorized:
                    err = mt5.last_error()
                    console.print(f"{stamp_err('LOGIN FAIL')} Login failed for account {acc_num} on server '{server}': {err}")
                    mt5.shutdown()
                    return False
            except ValueError:
                console.print(f"{stamp_err('INVALID ACC')} Account number must be integer.")
                mt5.shutdown()
                return False

        acc_info = mt5.account_info()
        term_info = mt5.terminal_info()

        if acc_info:
            trade_mode = "DEMO" if acc_info.trade_mode == 0 else ("CONTEST" if acc_info.trade_mode == 1 else "REAL")
            console.print(f"\n  [bold {BRASS}]Broker:[/] {acc_info.company} ({server})")
            console.print(f"  [bold {BRASS}]Account:[/] {acc_info.login} [{trade_mode}]")
            console.print(f"  [bold {BRASS}]Balance:[/] {acc_info.balance:.2f} {acc_info.currency} (Leverage 1:{acc_info.leverage})")

        if term_info:
            if not term_info.trade_allowed:
                console.print(f"\n{stamp_warn('ALGO TRADING OFF')} Tombol 'Algo Trading' di toolbar MT5 sedang NONAKTIF!")
                console.print(f"  [{MUTED}]Agent tidak dapat mengeksekusi order jika Algo Trading nonaktif. Klik tombol 'Algo Trading' di MT5 agar berwarna hijau.[/{MUTED}]")
            else:
                console.print(f"{stamp_ok('ALGO TRADING')} Automated trading is enabled in MT5 terminal.")

        # Probe key symbol
        probe_sym = "EURUSD" if mt5.symbol_info("EURUSD") else ("XAUUSD" if mt5.symbol_info("XAUUSD") else None)
        if probe_sym:
            s_info = mt5.symbol_info(probe_sym)
            if s_info:
                spread = s_info.spread
                console.print(f"{stamp_ok('MARKET WATCH')} Symbol {probe_sym} active (Spread: {spread} points, Bid: {s_info.bid}, Ask: {s_info.ask})")

        mt5.shutdown()
        console.print(f"{stamp_ok('HANDSHAKE')} MT5 Broker connection test successful!\n")
        return True

    def _test_db_connection(self, db_url: str) -> bool:
        """Tests database connection string with simple SELECT 1."""
        from cli.theme import get_console, stamp_ok, stamp_err, stamp_info
        console = get_console()
        console.print(f"{stamp_info('PROBE')} Testing database connectivity...")
        try:
            import asyncio
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text

            async def _ping():
                engine = create_async_engine(db_url, pool_pre_ping=True)
                async with engine.connect() as conn:
                    res = await conn.execute(text("SELECT 1"))
                    res.scalar()
                await engine.dispose()

            asyncio.run(_ping())
            console.print(f"{stamp_ok('DATABASE')} Database connection successful (SELECT 1 OK).\n")
            return True
        except Exception as e:
            console.print(f"{stamp_err('DB FAIL')} Database connection failed: {e}\n")
            return False

    def run_wizard(self, section: str = "all", quick: bool = False) -> bool:
        from cli.theme import (
            get_console, PHOSPHOR_AMBER, BRASS,
            stamp_ok, stamp_err, stamp_warn, stamp_info, MUTED
        )
        from rich.prompt import Prompt, Confirm
        from config.atomic_writer import AtomicConfigWriter
        from utils.infra.env_file_manager import EnvFileManager

        console = get_console()
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]       MONIKA (MT5 TRADING AGENT) — SETUP WIZARD             [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        # Headless check
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            console.print(f"{stamp_warn('HEADLESS')} Non-interactive environment detected. Use `monika config set` or environment variables.")
            return False

        env_updates: Dict[str, str] = {}
        settings_updates: Dict[str, Any] = {}

        # ── STEP 1: TRADING MODE & SAFETY LIMITS ──
        if section in ("all", "risk"):
            console.print(f"{stamp_info('STEP 1/5')} [bold {BRASS}]Trading Mode & Risk Limits[/]")
            if quick:
                is_paper = True
                max_risk = 1.0
                max_daily_dd = 3.0
                console.print(f"  [{MUTED}]Quick mode: Paper Trading=True, Risk/Trade=1.0%, Max DD=3.0%[/{MUTED}]")
            else:
                is_paper = Confirm.ask("Enable Paper Trading Mode (recommended for evaluation)?", default=True)
                max_risk = float(Prompt.ask("Max risk per trade percent (e.g. 1.0)", default="1.0"))
                max_daily_dd = float(Prompt.ask("Max daily drawdown percent (e.g. 3.0)", default="3.0"))

            settings_updates["paper_trading"] = {"enabled": is_paper}
            settings_updates["trading"] = {
                "risk": {
                    "risk_percent_per_trade": max_risk,
                    "max_daily_drawdown_percent": max_daily_dd,
                }
            }

        # ── STEP 2: METATRADER 5 CONFIGURATION & LIVE TEST ──
        if section in ("all", "mt5"):
            console.print(f"\n{stamp_info('STEP 2/5')} [bold {BRASS}]MetaTrader 5 (MT5) Terminal Configuration[/]")
            curr_acc = os.environ.get("MT5_ACCOUNT", "")
            account = Prompt.ask("MT5 Account Number", default=curr_acc)
            password = Prompt.ask("MT5 Account Password", password=True, default="")
            curr_server = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")
            server = Prompt.ask("MT5 Broker Server Name", default=curr_server)
            curr_path = os.environ.get("MT5_PATH", "")
            mt5_path = Prompt.ask("MT5 terminal64.exe path (leave blank for auto-detect)", default=curr_path)

            if account:
                env_updates["MT5_ACCOUNT"] = str(account)
            if password:
                env_updates["MT5_PASSWORD"] = str(password)
            if server:
                env_updates["MT5_SERVER"] = str(server)
            if mt5_path:
                env_updates["MT5_PATH"] = str(mt5_path)

            # Optional live handshake
            if account and password:
                if Confirm.ask("Run live MT5 broker connection test now?", default=True):
                    self._test_mt5_connection(account, password, server, mt5_path)

        # ── STEP 3: DATABASE CONFIGURATION ──
        if section in ("all", "db"):
            console.print(f"\n{stamp_info('STEP 3/5')} [bold {BRASS}]Database Connection & Storage[/]")
            curr_db = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_agent")
            db_url = Prompt.ask("PostgreSQL Connection URL (asyncpg format)", default=curr_db)
            if db_url:
                env_updates["DATABASE_URL"] = db_url
                if Confirm.ask("Test database connectivity now?", default=False):
                    self._test_db_connection(db_url)

                if Confirm.ask("Run database migrations (alembic upgrade head) now?", default=False):
                    try:
                        import subprocess
                        console.print(f"{stamp_info('ALEMBIC')} Running database migrations...")
                        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        res = subprocess.run(["alembic", "upgrade", "head"], cwd=base_dir, capture_output=True, text=True)
                        if res.returncode == 0:
                            console.print(f"{stamp_ok('MIGRATION')} Database schema migrated to latest head.")
                        else:
                            console.print(f"{stamp_warn('MIGRATION')} Alembic warning/error: {res.stderr or res.stdout}")
                    except Exception as mig_err:
                        console.print(f"{stamp_warn('MIGRATION')} Could not execute alembic automatically: {mig_err}")

        # ── STEP 4: AI PROVIDERS & API KEYS ──
        if section in ("all", "llm"):
            console.print(f"\n{stamp_info('STEP 4/5')} [bold {BRASS}]LLM Provider Credentials[/]")
            console.print(f"[{MUTED}]Masukkan API key provider yang Anda miliki (kosongkan jika sudah ada di environment):[/{MUTED}]")
            gemini_key = Prompt.ask("Google Gemini API Key", password=True, default="")
            anthropic_key = Prompt.ask("Anthropic API Key", password=True, default="")
            openai_key = Prompt.ask("OpenAI API Key", password=True, default="")
            groq_key = Prompt.ask("Groq API Key", password=True, default="")

            if gemini_key:
                env_updates["GEMINI_API_KEY"] = gemini_key
            if anthropic_key:
                env_updates["ANTHROPIC_API_KEY"] = anthropic_key
            if openai_key:
                env_updates["OPENAI_API_KEY"] = openai_key
            if groq_key:
                env_updates["GROQ_API_KEY"] = groq_key

            # Optional Model Preset
            console.print(f"\n[bold {BRASS}]Model Architecture Presets:[/]")
            console.print(f"  1. [bold {BRASS}]Budget / High-Efficiency Mode[/]: Gemini 3.8 Flash (hemat token, kecepatan tinggi)")
            console.print(f"  2. [bold {BRASS}]Institutional Performance Mode[/]: Claude 3.5/3.7 Sonnet (Stage 1/2) + Gemini 3.8 Flash (Subagents)")
            console.print(f"  3. [bold {BRASS}]Keep Current Roles[/]: Pertahankan konfigurasi task_roles di settings.yaml")
            preset_choice = Prompt.ask("Pilih preset (1/2/3)", choices=["1", "2", "3"], default="1")

            if preset_choice == "1":
                settings_updates["llm"] = {
                    "task_roles": {
                        "stage1_fundamental": {"primary": "gemini-3.8-flash"},
                        "stage2_per_asset_primary": {"primary": "gemini-3.8-flash"},
                        "stage2_per_asset_secondary": {"primary": "gemini-3.8-flash"},
                        "debate_judge": {"primary": "gemini-3.8-flash"},
                        "trade_reflection": {"primary": "gemini-3.8-flash"},
                    }
                }
            elif preset_choice == "2":
                settings_updates["llm"] = {
                    "task_roles": {
                        "stage1_fundamental": {"primary": "claude-3-5-sonnet"},
                        "stage2_per_asset_primary": {"primary": "claude-3-5-sonnet"},
                        "stage2_per_asset_secondary": {"primary": "claude-3-5-sonnet"},
                        "debate_judge": {"primary": "claude-3-5-sonnet"},
                        "trade_reflection": {"primary": "gemini-3.8-flash"},
                    }
                }

        # ── STEP 5: ATOMIC PERSISTENCE ──
        console.print(f"\n{stamp_info('STEP 5/5')} [bold {BRASS}]Saving Configuration & Credentials[/]")

        # 1. Update .env atomically
        if env_updates:
            env_ok = EnvFileManager.update_env_values(env_updates)
            if env_ok:
                console.print(f"{stamp_ok('ENV SAVED')} Credentials securely written to .env file.")
                # Update runtime os.environ as well
                for k, v in env_updates.items():
                    os.environ[k] = v
            else:
                console.print(f"{stamp_err('ENV ERROR')} Failed to save credentials to .env file.")

        # 2. Update settings.yaml atomically
        try:
            AtomicConfigWriter.update_in_place(self.settings_path, settings_updates)
            console.print(f"{stamp_ok('CONFIG SAVED')} Settings atomically updated in {self.settings_path} (comments preserved).")
        except Exception as e:
            console.print(f"{stamp_err('CONFIG ERROR')} Failed to update {self.settings_path}: {e}")
            return False

        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"{stamp_ok('SETUP COMPLETED')} Monika successfully configured!")
        console.print(f"[{MUTED}]Next Recommended Steps:[/{MUTED}]")
        console.print(f"  1. Run diagnostics:  [bold {BRASS}]python -m cli.main doctor[/]")
        console.print(f"  2. Start agent:      [bold {BRASS}]python -m cli.main run --dry-run[/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")
        return True
