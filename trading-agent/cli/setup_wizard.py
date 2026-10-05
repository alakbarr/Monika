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

    @staticmethod
    def detect_mt5_path() -> Optional[str]:
        """Automatically find standard MetaTrader 5 terminal64.exe on host system."""
        if sys.platform != "win32":
            return None
        candidates = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\FBS MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\IC Markets MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c

        scan_dirs = []
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
            base = os.environ.get(env_var)
            if base and os.path.exists(base):
                scan_dirs.append(base)
                programs_sub = os.path.join(base, "Programs")
                if os.path.exists(programs_sub):
                    scan_dirs.append(programs_sub)

        for base in scan_dirs:
            try:
                for item in os.listdir(base):
                    full_item = os.path.join(base, item)
                    if os.path.isdir(full_item):
                        cand = os.path.join(full_item, "terminal64.exe")
                        if os.path.exists(cand):
                            return cand
            except Exception:
                pass
        return None

    @staticmethod
    def detect_9router_status() -> Dict[str, Any]:
        """Check if Node.js/npx and 9router AI Gateway are available on the system."""
        import shutil
        import urllib.request
        node_installed = shutil.which("node") is not None
        npx_installed = shutil.which("npx") is not None
        router_bin = shutil.which("9router") is not None

        running = False
        try:
            req = urllib.request.Request("http://localhost:20128/v1/models", headers={"User-Agent": "Monika-Setup"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    running = True
        except Exception:
            running = False

        return {
            "node": node_installed,
            "npx": npx_installed,
            "router_installed": router_bin or npx_installed,
            "running": running,
        }

    def _test_mt5_connection(self, account: str, password: str, server: str, path: str) -> bool:
        """Performs live MT5 terminal handshake and checks AlgoTrading status."""
        from cli.theme import get_console, stamp_ok, stamp_err, stamp_warn, stamp_info, BRASS, PAPER, MUTED
        console = get_console()
        try:
            from execution.mt5_compat import ensure_mt5_module
            mt5: Any = ensure_mt5_module()
        except ImportError:
            console.print(f"{stamp_err('MT5 PKG')} MetaTrader5 Python package or mt5linux bridge is not installed.")
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
                console.print(f"\n{stamp_warn('ALGO TRADING OFF')} 'Algo Trading' button in MT5 toolbar is currently DISABLED!")
                console.print(f"  [{MUTED}]Automated order execution requires Algo Trading. Click 'Algo Trading' in MT5 toolbar so it turns green.[/]")
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
            import concurrent.futures
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text

            async def _ping():
                engine = create_async_engine(db_url, pool_pre_ping=True)
                async with engine.connect() as conn:
                    res = await conn.execute(text("SELECT 1"))
                    res.scalar()
                await engine.dispose()

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(lambda: asyncio.run(_ping()))
                    future.result(timeout=10.0)
            else:
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
                    model="gemini-3.5-flash",
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
            stamp_ok, stamp_err, stamp_warn, stamp_info, MUTED, PAPER
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
            console.print(f"{stamp_info('QUICK')} Quick mode: checking unconfigured items...")
            for k, is_missing in missing_items.items():
                status_icon = stamp_warn('MISSING') if is_missing else stamp_ok('CONFIGURED')
                console.print(f"  {status_icon} Component {k.upper()}")

        def _ask_step(prompt_text: str, default: str = "", password: bool = False) -> str:
            val = Prompt.ask(prompt_text, default=default, password=password)
            return clean_terminal_input(val)

        # ── PACKAGE TIER SELECTION (Step 0) ──
        installed_tier = "trial"
        if section == "all":
            console.print(f"[bold {BRASS}]Select Installation Package Tier:[/]")
            console.print(f"  1. [bold green]🚀 Trial Package (Quick Start - Recommended)[/]")
            console.print(f"     • 100% Paper Trading Sandbox (zero financial risk)")
            console.print(f"     • Zero-Config SQLite Database (ready immediately, no DB install)")
            console.print(f"     • Google Gemini Free Tier (with multi-key rotation guidance)")
            console.print(f"     • CLI Control + Telegram oversight on your phone")
            console.print(f"     • Setup takes ~2 minutes!\n")
            console.print(f"  2. [bold {BRASS}]🔥 Full Package (All Advanced Features)[/]")
            console.print(f"     • PostgreSQL 16+ Database (production multi-process & live trading)")
            console.print(f"     • Full Web Dashboard (React 19 / Vite telemetry)")
            console.print(f"     • 9Router AI Gateway & multi-provider LLM rotation")
            console.print(f"     • TimesFM 3.0 neural volatility forecasting")
            console.print(f"     • Native or VPS Wine MetaTrader 5 broker connectivity\n")

            tier_sel = _ask_step("Choose Package [1=Trial (Recommended) / 2=Full]", default="1")
            installed_tier = "full" if tier_sel == "2" else "trial"
            settings_updates["installation_tier"] = installed_tier
            console.print(f"  {stamp_ok('PACKAGE SELECTED')} [bold {BRASS}]{installed_tier.upper()}[/] package configuration active.\n")
        else:
            from config.settings import get_installation_tier
            installed_tier = get_installation_tier(self.settings_path)

        current_step = 1
        max_step = 6

        while 1 <= current_step <= max_step:
            # ── STEP 1: METATRADER 5 CONFIGURATION & LIVE TEST ──
            if current_step == 1:
                if section not in ("all", "mt5"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 1/6')} [bold {BRASS}]MetaTrader 5 (MT5) Terminal Configuration[/] [{MUTED}]('b' to go back)[/]")
                console.print(f"  [{MUTED}]Monika streams real-time candlestick quotes and spread data directly from MT5.[/]")
                console.print(f"  [{MUTED}]For the Trial Package, a free [bold green]Demo Account[/] is recommended (zero financial risk).[/]\n")

                if sys.platform != "win32":
                    console.print(f"[{MUTED}]Linux/Unix host detected. MT5 typically runs via Remote Gateway, EA Bridge, or Wine.[/]")
                    use_gateway = Confirm.ask("Use Remote MT5 Gateway / EA Bridge adapter?", default=True)
                    if use_gateway:
                        gw_url = _ask_step("Remote Gateway URL", default="http://127.0.0.1:8080")
                        settings_updates.setdefault("execution", {})["adapter_type"] = "remote_gateway"
                        settings_updates["execution"]["remote_gateway_url"] = gw_url
                        console.print(f"{stamp_ok('GATEWAY')} Configured remote gateway adapter -> {gw_url}")
                        current_step += 1
                        continue

                detected_mt5 = self.detect_mt5_path()
                while not detected_mt5:
                    console.print(f"  {stamp_warn('MT5 NOT FOUND')} MetaTrader 5 was not detected in standard system directories.")
                    console.print(f"\n  [bold cyan]Quick MT5 Setup Guide (Free, ~2 minutes):[/]")
                    console.print(f"    1. Download MT5: [bold underline cyan]https://www.metatrader5.com/en/download[/]")
                    console.print(f"    2. Run the installer and complete MetaTrader 5 installation.")
                    console.print(f"    3. Open MT5 -> Menu [bold]File[/] -> [bold]Open an Account[/] -> select [bold]MetaQuotes-Demo[/].")
                    console.print(f"    4. Create a free demo account (Leverage 1:100, virtual balance).")
                    console.print(f"    5. Note down your Account Number ([bold]Login[/]) and [bold]Password[/].")
                    console.print(f"    6. In the MT5 toolbar, click [bold green]'Algo Trading'[/] so the icon turns green.\n")

                    action = _ask_step("Enter [r] to re-detect after installing MT5, or input custom terminal64.exe path", default="r")
                    if action.lower() in ("b", "back"):
                        current_step = 0
                        break
                    elif action.lower() == "r":
                        detected_mt5 = self.detect_mt5_path()
                        if detected_mt5:
                            console.print(f"  {stamp_ok('MT5 FOUND')} Detected at: [bold]{detected_mt5}[/]\n")
                            break
                        else:
                            console.print(f"  {stamp_warn('RETRY')} MT5 still not detected. Please verify installation completed.[/]\n")
                    elif os.path.exists(action):
                        detected_mt5 = action
                        console.print(f"  {stamp_ok('MT5 PATH')} Custom path accepted: [bold]{detected_mt5}[/]\n")
                        break
                    elif action.lower() in ("skip", "s"):
                        console.print(f"  {stamp_warn('SKIP')} MT5 skipped temporarily. Warning: market candlestick data will not update without MT5!\n")
                        break

                if current_step == 0:
                    current_step = 1
                    continue

                if detected_mt5:
                    console.print(f"  {stamp_ok('MT5 TERMINAL')} Terminal path: [bold]{detected_mt5}[/]")

                curr_acc = os.environ.get("MT5_ACCOUNT", "")
                account = _ask_step("MT5 Account Number (Demo or Live login)", default=curr_acc)
                if account.lower() in ("b", "back"):
                    continue

                password = _ask_step("MT5 Account Password", password=True, default="")
                if password.lower() in ("b", "back"):
                    continue

                curr_server = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")
                server = _ask_step("MT5 Broker Server Name", default=curr_server)
                if server.lower() in ("b", "back"):
                    continue

                mt5_path = detected_mt5 or os.environ.get("MT5_PATH", "")

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

                console.print(f"\n{stamp_info('STEP 2/6')} [bold {BRASS}]Database Connection & Storage Engine[/] [{MUTED}]('b' to go back)[/]")

                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_file = os.path.join(data_dir, "monika.db").replace("\\", "/")
                sqlite_url = f"sqlite+aiosqlite:///{db_file}"

                if installed_tier == "trial":
                    env_updates["DATABASE_URL"] = sqlite_url
                    console.print(f"  {stamp_ok('DATABASE')} [bold green]Zero-Config SQLite[/] selected for Trial Package.")
                    console.print(f"  [{MUTED}]Storage path: [bold]{db_file}[/][/]")
                    console.print(f"  [{MUTED}]No PostgreSQL server installation needed. Upgrade anytime via `python -m cli.main upgrade`.[/]\n")
                    current_step += 1
                    continue

                # Full Package database options
                console.print(f"  1. [bold green]SQLite (Zero-Config)[/]: Fast local file storage at {db_file}")
                console.print(f"  2. [bold {BRASS}]PostgreSQL 16+ (Production-Grade)[/]: Required for multi-process or live trading.")
                db_choice = _ask_step("Select database engine (1=SQLite / 2=PostgreSQL)", default="2")
                if db_choice.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                if db_choice == "2":
                    curr_db = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/monika_trading")
                    db_url = _ask_step("PostgreSQL Connection URL (asyncpg format)", default=curr_db)
                    if db_url.lower() in ("b", "back"):
                        current_step -= 1
                        continue
                else:
                    db_url = sqlite_url
                    console.print(f"  {stamp_ok('DATABASE')} Using zero-config SQLite: [bold]{db_file}[/]")

                if db_url:
                    env_updates["DATABASE_URL"] = db_url
                    db_ok = True
                    if db_choice == "2" and Confirm.ask("Test PostgreSQL connectivity now?", default=False):
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

                    if Confirm.ask("Run database migrations (alembic upgrade head) now?", default=True):
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

                console.print(f"\n{stamp_info('STEP 3/6')} [bold {BRASS}]LLM Provider Credentials & Multi-Key Setup[/] [{MUTED}]('b' to go back)[/]")
                console.print(f"  [{MUTED}]Monika requires an AI model to evaluate macro news, detect SMC structure, and conduct Bull/Bear debates.[/]")
                console.print(f"  [{MUTED}]Google Gemini Free Tier is recommended as a zero-cost option (no credit card required).[/]")
                console.print(f"  [{PAPER}]👉 Get a free Gemini API key: [bold cyan]https://aistudio.google.com/apikey[/][/]")
                console.print(f"  [{MUTED}]💡 Quota Tip: Flash-Lite provides ~500 RPD per key. Adding 2-3 keys enables automatic failover rotation.[/]\n")

                curr_gemini = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY", "")
                gemini_input = _ask_step("Google Gemini API Key(s) (comma-separated if multiple)", password=True, default=curr_gemini)
                if gemini_input.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                cleaned_gemini_keys = [k.strip() for k in gemini_input.split(",") if k.strip()]
                if len(cleaned_gemini_keys) == 1:
                    console.print(f"  [{MUTED}]1 Gemini API key registered. Adding 2-3 keys enables automatic failover rotation.[/]")
                    if Confirm.ask("Add a 2nd Gemini API key now for automatic failover?", default=False):
                        k2 = _ask_step("Paste 2nd Gemini API Key", password=True)
                        if k2.strip():
                            cleaned_gemini_keys.append(k2.strip())
                            if Confirm.ask("Add a 3rd Gemini API key now?", default=False):
                                k3 = _ask_step("Paste 3rd Gemini API Key", password=True)
                                if k3.strip():
                                    cleaned_gemini_keys.append(k3.strip())

                if cleaned_gemini_keys:
                    env_updates["GEMINI_API_KEYS"] = ",".join(cleaned_gemini_keys)
                    env_updates["GEMINI_API_KEY"] = cleaned_gemini_keys[0]
                    console.print(f"  {stamp_ok('GEMINI POOL')} Registered {len(cleaned_gemini_keys)} Gemini key(s) in active pool.")
                    if Confirm.ask("Test Gemini API key validity now (1-token completion)?", default=True):
                        valid_cnt = 0
                        for idx, key_cand in enumerate(cleaned_gemini_keys, 1):
                            masked = f"...{key_cand[-6:]}" if len(key_cand) > 6 else key_cand
                            console.print(f"    Testing key #{idx} ({masked})...", end=" ")
                            if self._test_llm_connection("gemini", key_cand):
                                valid_cnt += 1
                        console.print(f"  {stamp_ok('GEMINI CHECK')} {valid_cnt}/{len(cleaned_gemini_keys)} key(s) verified operational.\n")

                # Optional additional providers
                want_more_providers = False
                has_any_key = bool(cleaned_gemini_keys or os.environ.get("GEMINI_API_KEY"))
                if not has_any_key:
                    console.print(f"  {stamp_warn('NO GEMINI')} Gemini skipped. You must configure at least one alternative provider below.\n")
                    want_more_providers = True
                elif installed_tier == "full":
                    want_more_providers = True
                else:
                    want_more_providers = Confirm.ask("Configure additional AI providers (OpenRouter, Groq, Anthropic, OpenAI)?", default=False)

                openrouter_key = ""
                groq_key = ""
                anthropic_key = ""
                openai_key = ""

                if want_more_providers:
                    console.print(f"  [{MUTED}]Alternative Provider Options:[/]")
                    openrouter_key = _ask_step("OpenRouter API Key (https://openrouter.ai/keys)", password=True, default=os.environ.get("OPENROUTER_API_KEY", ""))
                    if openrouter_key.lower() in ("b", "back"):
                        current_step -= 1
                        continue

                    groq_key = _ask_step("Groq API Key (https://console.groq.com/keys)", password=True, default=os.environ.get("GROQ_API_KEY", ""))
                    if groq_key.lower() in ("b", "back"):
                        current_step -= 1
                        continue

                    anthropic_key = _ask_step("Anthropic Claude API Key (https://console.anthropic.com/)", password=True, default=os.environ.get("ANTHROPIC_API_KEY", ""))
                    if anthropic_key.lower() in ("b", "back"):
                        current_step -= 1
                        continue

                    openai_key = _ask_step("OpenAI API Key (https://platform.openai.com/api-keys)", password=True, default=os.environ.get("OPENAI_API_KEY", ""))
                    if openai_key.lower() in ("b", "back"):
                        current_step -= 1
                        continue

                if openrouter_key:
                    env_updates["OPENROUTER_API_KEY"] = openrouter_key
                if groq_key:
                    env_updates["GROQ_API_KEY"] = groq_key
                    if Confirm.ask("Test Groq API key validity now?", default=True):
                        self._test_llm_connection("groq", groq_key)
                if anthropic_key:
                    env_updates["ANTHROPIC_API_KEY"] = anthropic_key
                    if Confirm.ask("Test Anthropic API key validity now?", default=True):
                        self._test_llm_connection("anthropic", anthropic_key)
                if openai_key:
                    env_updates["OPENAI_API_KEY"] = openai_key
                    if Confirm.ask("Test OpenAI API key validity now?", default=True):
                        self._test_llm_connection("openai", openai_key)

                # Validate at least one key is configured
                all_candidate_keys = [
                    cleaned_gemini_keys,
                    openrouter_key or os.environ.get("OPENROUTER_API_KEY"),
                    groq_key or os.environ.get("GROQ_API_KEY"),
                    anthropic_key or os.environ.get("ANTHROPIC_API_KEY"),
                    openai_key or os.environ.get("OPENAI_API_KEY"),
                ]
                if not any(bool(k) for k in all_candidate_keys):
                    console.print(f"\n{stamp_err('KEY REQUIRED')} [bold red]At least one AI Provider API key is required for Monika to operate![/]")
                    console.print(f"  [{MUTED}]Obtain a free Gemini key at https://aistudio.google.com/apikey and try again.[/]\n")
                    continue

                # 9Router AI Gateway recommendation (Strongly recommended for ALL packages)
                console.print(f"\n  [bold cyan]⚡ 9Router AI Gateway (Strongly Recommended)[/]")
                console.print(f"  [{MUTED}]Functions as an intelligent local proxy on localhost:20128 for model load-balancing and failover.[/]")
                router_stat = self.detect_9router_status()
                if router_stat["running"]:
                    console.print(f"  {stamp_ok('9ROUTER')} 9Router AI Gateway detected active on localhost:20128.")
                    settings_updates.setdefault("llm", {}).setdefault("nine_router", {})["enabled"] = True
                elif router_stat["router_installed"]:
                    enable_9r = Confirm.ask("Enable 9Router AI Gateway (localhost:20128)?", default=True)
                    if enable_9r:
                        settings_updates.setdefault("llm", {}).setdefault("nine_router", {})["enabled"] = True
                        console.print(f"  {stamp_ok('9ROUTER')} 9Router AI Gateway enabled. Starts automatically with the launcher.\n")
                else:
                    console.print(f"  [{MUTED}]Node.js/npx not detected. 9Router skipped for now.[/]")
                    console.print(f"  [{PAPER}]Tip: Install Node.js from https://nodejs.org to enable 9Router later.[/]\n")

                # Model Architecture Profiles
                from config.profile_applicator import ProfileApplicator, PROFILE_METADATA
                console.print(f"\n[bold {BRASS}]Select Model Configuration Profile (Automatically Maps All 49 Task Roles):[/]")
                console.print(f"  1. [bold {BRASS}]High Analysis — High Frequency[/]: Scalping & intraday trading, deep multi-step reasoning")
                console.print(f"  2. [bold {BRASS}]High Analysis — Low Frequency[/]: Swing trading & macro, deep reasoning, conservative rate limits")
                console.print(f"  3. [bold {BRASS}]Simple Tasks — High Frequency[/]: Rapid signals, continuous polling, Flash-Lite (500 RPD)")
                console.print(f"  4. [bold {BRASS}]Simple Tasks — Low Frequency[/]: Passive monitoring 1-2x/day, minimal token usage")
                console.print(f"  5. [bold {BRASS}]Low Latency — Smart[/]: Swift reaction to price spikes with high-fidelity validation")
                console.print(f"  6. [bold green]Low Latency — Cost-Optimized (Default)[/]: Free-tier friendly, fast execution, ideal for testing")
                console.print(f"  7. [bold {MUTED}]Keep Current Configuration[/]: Retain existing task_roles in settings.yaml")
                default_profile_choice = "6" if installed_tier == "trial" else "5"
                preset_choice = _ask_step("Select profile (1-7)", default=default_profile_choice)

                profile_map = {
                    "1": "high_analysis_high_freq",
                    "2": "high_analysis_low_freq",
                    "3": "simple_task_high_freq",
                    "4": "simple_task_low_freq",
                    "5": "low_latency_smart",
                    "6": "low_latency_cheap",
                }

                if preset_choice in profile_map:
                    sel_prof = profile_map[preset_choice]
                    mock_env = {**os.environ, **env_updates}
                    detected_provs = ProfileApplicator.detect_available_providers(mock_env)
                    roles_dict = ProfileApplicator.build_task_roles_config(sel_prof, detected_provs)
                    settings_updates["llm"] = {
                        "active_profile": sel_prof,
                        "task_roles": roles_dict,
                    }
                    console.print(f"  {stamp_ok('PROFILE')} Successfully mapped all 49 task roles for profile '{sel_prof}'.")

                current_step += 1
                continue

            # ── STEP 4: RISK PROFILE & EXPOSURE GUARDRAILS ──
            if current_step == 4:
                if section not in ("all", "risk"):
                    current_step += 1
                    continue

                console.print(f"\n{stamp_info('STEP 4/6')} [bold {BRASS}]Risk Profile & Exposure Guardrails[/] [{MUTED}]('b' to go back)[/]")
                console.print(f"[{MUTED}]Select automated trading risk tolerance profile:[/]")
                console.print(f"  1. [bold green]Conservative / Prop-Firm Safe[/]: Risk 0.5%/trade, Max Daily DD 2.0%, Max 2 Open Positions")
                console.print(f"  2. [bold {BRASS}]Moderate / Standard Growth[/]: Risk 1.0%/trade, Max Daily DD 3.5%, Max 3 Open Positions")
                console.print(f"  3. [bold red]Aggressive / High Yield[/]: Risk 2.0%/trade, Max Daily DD 5.0%, Max 5 Open Positions")
                console.print(f"  4. [bold cyan]Custom Parameters[/]: Manual risk parameters input")

                profile_choice = _ask_step("Select risk profile (1/2/3/4)", default="2")
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

                console.print(f"\n{stamp_info('STEP 5/6')} [bold {BRASS}]Paper Trading Mode & Graduation Invariant[/] [{MUTED}]('b' to go back)[/]")
                console.print(f"[{MUTED}]Monika requires paper trading sandbox verification before live execution.[/]")

                is_paper_str = _ask_step("Enable Paper Trading Mode? (y/n)", default="y")
                if is_paper_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                is_paper = is_paper_str.lower() in ("y", "yes", "true", "1")

                min_trades_str = _ask_step("Minimum paper trades target before live graduation (default: 50)", default="50")
                if min_trades_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                min_trades = int(min_trades_str) if min_trades_str.isdigit() else 50

                min_wr_str = _ask_step("Minimum win rate percent target before live graduation (default: 55.0)", default="55.0")
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

                console.print(f"\n{stamp_info('STEP 6/6')} [bold {BRASS}]Telegram Bot & Mobile Oversight (Required)[/] [{MUTED}]('b' to go back)[/]")
                console.print(f"  [{MUTED}]Telegram is Monika's primary oversight interface for real-time telemetry, trade approval cards, and emergency halts.[/]")
                console.print(f"\n  [bold cyan]Quick Telegram Bot Setup (Free, ~1 minute):[/]")
                console.print(f"    1. Open Telegram and search for [bold cyan]@BotFather[/]")
                console.print(f"    2. Send [bold cyan]/newbot[/] and follow the prompts to name your bot")
                console.print(f"    3. Copy the [bold]HTTP API Token[/] provided by BotFather (e.g. 123456789:ABCdefGHI...)")
                console.print(f"    4. To get your numeric ID: search for [bold cyan]@userinfobot[/], send [bold cyan]/start[/], and copy your [bold]Id[/].\n")

                curr_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                bot_token = ""
                while not bot_token:
                    bot_token = _ask_step("Telegram Bot Token (required)", password=True, default=curr_bot_token)
                    if bot_token.lower() in ("b", "back"):
                        break
                    if not bot_token.strip():
                        console.print(f"  {stamp_err('REQUIRED')} Telegram Bot Token is required for trade proposals and system alerts.")

                if bot_token.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                curr_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
                chat_id = ""
                while not chat_id:
                    chat_id = _ask_step("Telegram Admin Chat ID (required, e.g. 987654321)", default=curr_chat_id)
                    if chat_id.lower() in ("b", "back"):
                        break
                    if not chat_id.strip():
                        console.print(f"  {stamp_err('REQUIRED')} Admin Chat ID is required to restrict commands exclusively to your account.")

                if chat_id.lower() in ("b", "back"):
                    current_step -= 1
                    continue

                voice_str = _ask_step("Enable Voice Trading Notes? (y/n)", default="y")
                if voice_str.lower() in ("b", "back"):
                    current_step -= 1
                    continue
                voice_enabled = voice_str.lower() in ("y", "yes", "true", "1")

                env_updates["TELEGRAM_BOT_TOKEN"] = bot_token
                env_updates["TELEGRAM_ADMIN_CHAT_ID"] = chat_id
                settings_updates.setdefault("telegram", {})["voice_enabled"] = voice_enabled
                console.print(f"  {stamp_ok('TELEGRAM')} Telegram bot configured (Admin ID: {chat_id}, Voice: {voice_enabled})\n")

                current_step += 1
                continue

        # ── PRE-FLIGHT READINESS CHECKLIST & SUMMARY ──
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]              PRE-FLIGHT READINESS CHECKLIST                  [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        db_type = "Zero-Config SQLite (WAL Mode)" if installed_tier == "trial" or "sqlite" in env_updates.get("DATABASE_URL", "") else "PostgreSQL 16+ Production"
        llm_providers = []
        if env_updates.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            llm_providers.append("Google Gemini")
        if env_updates.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
            llm_providers.append("OpenRouter")
        if env_updates.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY"):
            llm_providers.append("Groq")
        if env_updates.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
            llm_providers.append("Anthropic")
        if env_updates.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            llm_providers.append("OpenAI")
        llm_display = ", ".join(llm_providers) if llm_providers else "None"

        console.print(f"  {stamp_ok('PACKAGE')}  Tier: [bold {BRASS}]{installed_tier.upper()}[/] | Execution: [bold green]Paper Trading Sandbox[/]")
        console.print(f"  {stamp_ok('DATABASE')} Engine: [bold]{db_type}[/]")
        mt5_acc = env_updates.get("MT5_ACCOUNT") or os.environ.get("MT5_ACCOUNT", "Demo/Configured")
        console.print(f"  {stamp_ok('TERMINAL')} MetaTrader 5: Account [bold]{mt5_acc}[/] ({env_updates.get('MT5_SERVER', 'MetaQuotes-Demo')})")
        console.print(f"  {stamp_ok('AI FABRIC')} Models: [bold]{llm_display}[/]")
        tele_id = env_updates.get("TELEGRAM_ADMIN_CHAT_ID") or os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "Configured")
        console.print(f"  {stamp_ok('TELEGRAM')} Oversight: Admin ID [bold]{tele_id}[/]")
        nine_r_status = "Enabled (localhost:20128)" if settings_updates.get("llm", {}).get("nine_router", {}).get("enabled") else "Optional (Skipped)"
        console.print(f"  {stamp_info('9ROUTER')}  Gateway: [bold]{nine_r_status}[/]\n")

        # ── ATOMIC PERSISTENCE ──
        console.print(f"{stamp_info('PERSIST')} Saving configuration and credentials securely...")

        # 1. Update .env atomically
        if env_updates:
            env_ok = EnvFileManager.update_env_values(env_updates)
            if env_ok:
                console.print(f"  {stamp_ok('ENV SAVED')} Credentials securely written to .env.")
                for k, v in env_updates.items():
                    os.environ[k] = v
            else:
                console.print(f"  {stamp_err('ENV ERROR')} Failed to save credentials to .env file.")

        # 2. Update settings.yaml atomically
        try:
            AtomicConfigWriter.update_in_place(self.settings_path, settings_updates)
            console.print(f"  {stamp_ok('CONFIG SAVED')} Settings updated in {self.settings_path} (comments preserved).")
        except Exception as e:
            console.print(f"  {stamp_err('CONFIG ERROR')} Failed to update {self.settings_path}: {e}")
            return False

        # 3. Write .monika_tier marker in root directory
        try:
            root_cand = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if os.path.basename(root_cand) == "trading-agent":
                root_cand = os.path.dirname(root_cand)
            tier_marker = os.path.join(root_cand, ".monika_tier")
            with open(tier_marker, "w", encoding="utf-8") as f:
                f.write(installed_tier.strip().lower() + "\n")
        except Exception:
            pass

        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"{stamp_ok('SETUP COMPLETED')} Monika successfully configured ({installed_tier.upper()} Package)!")
        console.print(f"[{MUTED}]Next Recommended Steps:[/]")
        console.print(f"  1. System Diagnostics: [bold {BRASS}]python -m cli.main doctor[/]")
        console.print(f"  2. Trader Personality: [bold {BRASS}]python -m cli.main onboarding[/]")
        console.print(f"  3. Launch Monika:      [bold {BRASS}]python -m cli.main run[/] (or use the launcher)")
        if installed_tier == "trial":
            console.print(f"  4. Upgrade to Full:    [bold cyan]python -m cli.main upgrade[/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")
        return True
