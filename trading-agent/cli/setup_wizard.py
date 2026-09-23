"""
File: cli/setup_wizard.py
Interactive onboarding setup wizard for Monika (MT5 Trading Agent).
Provides guided terminal prompts to configure credentials, MT5 settings, live broker tests,
database connectivity, and risk limits with atomic comment-preserving persistence.
"""

import os
import sys
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("TradingAgent.CLI.SetupWizard")

_PASTE_CLEANER = re.compile(r"\x1b\[\s*200~|\x1b\[\s*201~")

def clean_terminal_input(val: str) -> str:
    """Strip bracketed paste escape sequences and surrounding whitespace."""
    if not val:
        return ""
    return _PASTE_CLEANER.sub("", str(val)).strip()


class SetupWizard:
    """Guided terminal configuration wizard with live broker handshake and atomic persistence."""

    def __init__(self, settings_path: Optional[str] = None):
        self.settings_path = settings_path or "config/settings.yaml"

    def _test_mt5_connection(self, account: str, password: str, server: str, path: str) -> bool:
        """Performs live MT5 terminal handshake and checks AlgoTrading status."""
        from cli.theme import get_console, stamp_ok, stamp_err, stamp_warn, stamp_info, BRASS, PAPER, MUTED
        console = get_console()
        try:
            import MetaTrader5 as _mt5
            mt5: Any = _mt5
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

    @staticmethod
    def get_missing_setup_items() -> Dict[str, bool]:
        """Detects missing environment or critical configuration items."""
        return {
            "mt5": not bool(os.environ.get("MT5_ACCOUNT") and os.environ.get("MT5_PASSWORD")),
            "db": not bool(os.environ.get("DATABASE_URL")),
            "llm": not any(os.environ.get(k) for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY")),
        }

    def _test_llm_connection(self, provider: str, api_key: str) -> bool:
        """Sends a 1-token lightweight completion to verify API key validity."""
        from cli.theme import get_console, stamp_ok, stamp_err, stamp_info
        console = get_console()
        console.print(f"{stamp_info('PROBE')} Testing {provider} API key validity...")
        try:
            if provider.lower() == "gemini":
                from google import genai  # type: ignore
                client = genai.Client(api_key=api_key)
                client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="ping",
                )
                console.print(f"{stamp_ok('LLM OK')} Gemini API key is valid.\n")
                return True
            elif provider.lower() == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
                console.print(f"{stamp_ok('LLM OK')} Anthropic API key is valid.\n")
                return True
            elif provider.lower() in ("openai", "groq"):
                import openai
                base_url = "https://api.groq.com/openai/v1" if provider.lower() == "groq" else None
                client = openai.OpenAI(api_key=api_key, base_url=base_url)
                model = "llama-3.1-8b-instant" if provider.lower() == "groq" else "gpt-4o-mini"
                client.chat.completions.create(
                    model=model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
                console.print(f"{stamp_ok('LLM OK')} {provider.title()} API key is valid.\n")
                return True
        except Exception as e:
            console.print(f"{stamp_err('LLM FAIL')} {provider} connection test failed: {e}\n")
            return False
        return True

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

        missing_items = self.get_missing_setup_items()
        if quick:
            console.print(f"{stamp_info('QUICK')} Mode cepat: memeriksa item konfigurasi yang belum diset...")
            for k, is_missing in missing_items.items():
                status_icon = stamp_warn('MISSING') if is_missing else stamp_ok('CONFIGURED')
                console.print(f"  {status_icon} Komponen {k.upper()}")

        def _ask_step(prompt_text: str, default: str = "", password: bool = False) -> str:
            val = Prompt.ask(prompt_text, default=default, password=password)
            return clean_terminal_input(val)

        current_step = 1
        max_step = 6

        while 1 <= current_step <= max_step:
            # ── STEP 1: METATRADER 5 CONFIGURATION & LIVE TEST ──
            if current_step == 1:
                if section not in ("all", "mt5"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 1/6')} [bold {BRASS}]MetaTrader 5 (MT5) Terminal Configuration[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")

                if sys.platform != "win32":
                    console.print(f"[{MUTED}]Linux/Unix host detected. MT5 typically runs via Remote Gateway, EA Bridge, or Wine.[/{MUTED}]")
                    use_gateway = Confirm.ask("Use Remote MT5 Gateway / EA Bridge adapter?", default=True)
                    if use_gateway:
                        gw_url = _ask_step("Remote Gateway URL", default="http://127.0.0.1:8080")
                        settings_updates.setdefault("execution", {})["adapter_type"] = "remote_gateway"
                        settings_updates["execution"]["remote_gateway_url"] = gw_url
                        console.print(f"{stamp_ok('GATEWAY')} Configured remote gateway adapter -> {gw_url}")
                        current_step += 1
                        continue

                curr_acc = os.environ.get("MT5_ACCOUNT", "")
                account = _ask_step("MT5 Account Number", default=curr_acc)
                if account.lower() in ("b", "back"):
                    console.print(f"[{MUTED}]Di langkah pertama. Ketik 'q' untuk keluar jika ingin membatalkan.[/{MUTED}]")
                    continue

                password = _ask_step("MT5 Account Password", password=True, default="")
                if password.lower() in ("b", "back"):
                    continue

                curr_server = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")
                server = _ask_step("MT5 Broker Server Name", default=curr_server)
                if server.lower() in ("b", "back"):
                    continue

                curr_path = os.environ.get("MT5_PATH", "")
                mt5_path = _ask_step("MT5 terminal64.exe path (leave blank for auto-detect)", default=curr_path)
                if mt5_path.lower() in ("b", "back"):
                    continue

                if account:
                    env_updates["MT5_ACCOUNT"] = str(account)
                if password:
                    env_updates["MT5_PASSWORD"] = str(password)
                if server:
                    env_updates["MT5_SERVER"] = str(server)
                if mt5_path:
                    env_updates["MT5_PATH"] = str(mt5_path)

                if account and password:
                    if Confirm.ask("Run live MT5 broker connection test now?", default=True):
                        self._test_mt5_connection(account, password, server, mt5_path)

                current_step += 1
                continue

            # ── STEP 2: DATABASE CONFIGURATION & STORAGE ──
            if current_step == 2:
                if section not in ("all", "db"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 2/6')} [bold {BRASS}]Database Connection & Storage Engine[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")
                curr_db = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_agent")
                db_url = _ask_step("PostgreSQL Connection URL (asyncpg format)", default=curr_db)
                if db_url.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                if db_url:
                    env_updates["DATABASE_URL"] = db_url
                    db_ok = True
                    if Confirm.ask("Test database connectivity now?", default=False):
                        db_ok = self._test_db_connection(db_url)

                    if not db_ok:
                        if Confirm.ask("PostgreSQL connection failed. Would you like to spawn a local PostgreSQL Docker container?", default=True):
                            try:
                                import subprocess
                                import time
                                console.print(f"{stamp_info('DOCKER')} Spawning PostgreSQL Docker container (monika-postgres)...")
                                run_res = subprocess.run([
                                    "docker", "run", "-d",
                                    "--name", "monika-postgres",
                                    "-e", "POSTGRES_PASSWORD=postgres",
                                    "-e", "POSTGRES_DB=trading_agent",
                                    "-p", "5432:5432",
                                    "postgres:16-alpine"
                                ], capture_output=True, text=True)
                                if run_res.returncode == 0:
                                    console.print(f"{stamp_ok('DOCKER')} Container monika-postgres started! Waiting 3s...")
                                    time.sleep(3)
                                    db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_agent"
                                    env_updates["DATABASE_URL"] = db_url
                                    self._test_db_connection(db_url)
                                else:
                                    console.print(f"{stamp_warn('DOCKER')} Docker failed: {run_res.stderr or run_res.stdout}")
                            except Exception as d_err:
                                console.print(f"{stamp_warn('DOCKER')} Could not run docker: {d_err}")

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

                current_step += 1
                continue

            # ── STEP 3: AI PROVIDERS & API KEYS ──
            if current_step == 3:
                if section not in ("all", "llm"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 3/6')} [bold {BRASS}]LLM Provider Credentials & Architecture[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")
                console.print(f"[{MUTED}]Masukkan API key provider (kosongkan jika sudah ada di environment):[/{MUTED}]")
                gemini_key = _ask_step("Google Gemini API Key", password=True, default="")
                if gemini_key.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                anthropic_key = _ask_step("Anthropic API Key", password=True, default="")
                if anthropic_key.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                openai_key = _ask_step("OpenAI API Key", password=True, default="")
                if openai_key.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                groq_key = _ask_step("Groq API Key", password=True, default="")
                if groq_key.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                if gemini_key:
                    env_updates["GEMINI_API_KEY"] = gemini_key
                    if Confirm.ask("Test Gemini API key validity now?", default=True):
                        self._test_llm_connection("gemini", gemini_key)
                if anthropic_key:
                    env_updates["ANTHROPIC_API_KEY"] = anthropic_key
                    if Confirm.ask("Test Anthropic API key validity now?", default=True):
                        self._test_llm_connection("anthropic", anthropic_key)
                if openai_key:
                    env_updates["OPENAI_API_KEY"] = openai_key
                    if Confirm.ask("Test OpenAI API key validity now?", default=True):
                        self._test_llm_connection("openai", openai_key)
                if groq_key:
                    env_updates["GROQ_API_KEY"] = groq_key
                    if Confirm.ask("Test Groq API key validity now?", default=True):
                        self._test_llm_connection("groq", groq_key)

                # Optional Model Preset
                console.print(f"\n[bold {BRASS}]Model Architecture Presets:[/]")
                console.print(f"  1. [bold {BRASS}]Budget / High-Efficiency Mode[/]: Gemini 3.8 Flash (hemat token, kecepatan tinggi)")
                console.print(f"  2. [bold {BRASS}]Institutional Performance Mode[/]: Claude 3.5/3.7 Sonnet + Gemini 3.8 Flash")
                console.print(f"  3. [bold {BRASS}]Keep Current Roles[/]: Pertahankan konfigurasi task_roles di settings.yaml")
                preset_choice = _ask_step("Pilih preset (1/2/3)", default="1")

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

                current_step += 1
                continue

            # ── STEP 4: RISK PROFILE & EXPOSURE GUARDRAILS ──
            if current_step == 4:
                if section not in ("all", "risk"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 4/6')} [bold {BRASS}]Risk Profile & Exposure Guardrails[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")
                console.print(f"[{MUTED}]Pilih profil toleransi risiko trading otomatis:[/{MUTED}]")
                console.print(f"  1. [bold green]Conservative / Prop-Firm Safe[/]: Risk 0.5%/trade, Max Daily DD 2.0%, Max 2 Open Positions")
                console.print(f"  2. [bold {BRASS}]Moderate / Standard Growth[/]: Risk 1.0%/trade, Max Daily DD 3.5%, Max 3 Open Positions")
                console.print(f"  3. [bold red]Aggressive / High Yield[/]: Risk 2.0%/trade, Max Daily DD 5.0%, Max 5 Open Positions")
                console.print(f"  4. [bold cyan]Custom Parameters[/]: Input manual parameter risiko")

                profile_choice = _ask_step("Pilih profil risiko (1/2/3/4)", default="2")
                if profile_choice.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                if profile_choice == "1":
                    risk_pct, max_dd, max_pos = 0.5, 2.0, 2
                elif profile_choice == "3":
                    risk_pct, max_dd, max_pos = 2.0, 5.0, 5
                elif profile_choice == "4":
                    r_str = _ask_step("Max risk per trade percent (e.g. 1.0)", default="1.0")
                    risk_pct = float(r_str) if r_str.replace(".", "", 1).isdigit() else 1.0
                    dd_str = _ask_step("Max daily drawdown percent (e.g. 3.5)", default="3.5")
                    max_dd = float(dd_str) if dd_str.replace(".", "", 1).isdigit() else 3.5
                    pos_str = _ask_step("Max concurrent open positions (e.g. 3)", default="3")
                    max_pos = int(pos_str) if pos_str.isdigit() else 3
                else:
                    risk_pct, max_dd, max_pos = 1.0, 3.5, 3

                settings_updates.setdefault("trading", {}).setdefault("risk", {})
                settings_updates["trading"]["risk"]["risk_percent_per_trade"] = risk_pct
                settings_updates["trading"]["risk"]["max_daily_drawdown_percent"] = max_dd
                settings_updates["trading"]["risk"]["max_open_positions"] = max_pos
                console.print(f"  {stamp_ok('RISK SET')} Risk: {risk_pct}% | Max DD: {max_dd}% | Max Positions: {max_pos}")

                current_step += 1
                continue

            # ── STEP 5: PAPER TRADING MODE & GRADUATION INVARIANT ──
            if current_step == 5:
                if section not in ("all", "paper"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 5/6')} [bold {BRASS}]Paper Trading Mode & Graduation Invariant[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")
                console.print(f"[{MUTED}]Sistem Monika mewajibkan paper trading sandbox sebelum live execution.[/{MUTED}]")

                is_paper_str = _ask_step("Aktifkan Paper Trading Mode? (y/n)", default="y")
                if is_paper_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                is_paper = is_paper_str.lower() in ("y", "yes", "true", "1")

                min_trades_str = _ask_step("Target minimum paper trades sebelum live graduation (default: 50)", default="50")
                if min_trades_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                min_trades = int(min_trades_str) if min_trades_str.isdigit() else 50

                min_wr_str = _ask_step("Target minimum win rate percent sebelum live (default: 55.0)", default="55.0")
                if min_wr_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                min_wr = float(min_wr_str) if min_wr_str.replace(".", "", 1).isdigit() else 55.0

                settings_updates["paper_trading"] = {
                    "enabled": is_paper,
                    "min_paper_trades_before_live": min_trades,
                    "min_paper_win_rate_pct": min_wr,
                }
                console.print(f"  {stamp_ok('PAPER GATE')} Paper Trading: {is_paper} | Gate: {min_trades} Trades @ {min_wr}% Win Rate")

                current_step += 1
                continue

            # ── STEP 6: TELEGRAM BOT & MOBILE OVERSIGHT ──
            if current_step == 6:
                if section not in ("all", "telegram"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 6/6')} [bold {BRASS}]Telegram Bot & Mobile Oversight[/] [{MUTED}('b' untuk kembali)[/{MUTED}]")
                console.print(f"[{MUTED}]Konfigurasi integrasi Telegram bot untuk notifikasi real-time & approval cards:[/{MUTED}]")

                curr_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                bot_token = _ask_step("Telegram Bot Token (kosongkan jika belum ada)", password=True, default=curr_bot_token)
                if bot_token.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                curr_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
                chat_id = _ask_step("Telegram Admin Chat ID", default=curr_chat_id)
                if chat_id.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                voice_str = _ask_step("Enable Voice Trading Notes? (y/n)", default="y")
                if voice_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                voice_enabled = voice_str.lower() in ("y", "yes", "true", "1")

                if bot_token:
                    env_updates["TELEGRAM_BOT_TOKEN"] = bot_token
                if chat_id:
                    env_updates["TELEGRAM_ADMIN_CHAT_ID"] = chat_id

                settings_updates.setdefault("telegram", {})["voice_enabled"] = voice_enabled
                console.print(f"  {stamp_ok('TELEGRAM')} Telegram oversight configured (Voice: {voice_enabled})")

                current_step += 1
                continue

        # ── ATOMIC PERSISTENCE ──
        console.print(f"\n{stamp_info('FINAL')} [bold {BRASS}]Saving Configuration & Credentials[/]")

        # 1. Update .env atomically
        if env_updates:
            env_ok = EnvFileManager.update_env_values(env_updates)
            if env_ok:
                console.print(f"{stamp_ok('ENV SAVED')} Credentials securely written to .env file.")
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
        console.print(f"  1. Trader Onboarding: [bold {BRASS}]python -m cli.main onboarding[/]")
        console.print(f"  2. Run diagnostics:   [bold {BRASS}]python -m cli.main doctor[/]")
        console.print(f"  3. Start agent:       [bold {BRASS}]python -m cli.main run --dry-run[/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")
        return True
