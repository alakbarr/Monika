import argparse
import asyncio
import logging
import os
import sys

# Add parent directory to path
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from bootstrap import install_bootstrap_hardening
install_bootstrap_hardening()

import atexit
import threading
import time

def _reset_terminal_modes():
    """Restore terminal mouse, bracketed paste, and cursor visibility on exit."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\x1b[?1000l\x1b[?2004l\x1b[?25h")
            sys.stdout.flush()
    except Exception:
        pass

atexit.register(_reset_terminal_modes)

def arm_exit_watchdog(timeout_s: float = 15.0):
    """Escort thread ensuring clean process termination if async loops hang during shutdown."""
    def _force_exit():
        time.sleep(timeout_s)
        _reset_terminal_modes()
        os._exit(0)
    t = threading.Thread(target=_force_exit, daemon=True, name="exit-watchdog")
    t.start()

from cli.platform_compat import apply_platform_fixes
apply_platform_fixes()

from typing import Any, Dict, List, Optional
import aiohttp
from config.settings import load_all_config, load_settings
from database.db import init_db, get_session, close_db
from database.models import Position, PaperTradeRecord, SystemConfig, RiskState
from sqlalchemy import select

from cli.theme import (
    get_console,
    LEDGER_BOX,
    PHOSPHOR_AMBER,
    BRASS,
    BULL_PROFIT,
    BEAR_LOSS,
    MUTED,
    PAPER,
    stamp_ok,
    stamp_err,
    stamp_warn,
    stamp_info,
    stamp_exec,
)

import main as _root_main

TradingAgent: Any = getattr(_root_main, "TradingAgent", None)
acquire_single_instance_lock: Any = getattr(_root_main, "acquire_single_instance_lock", None)
run_startup_checks: Any = getattr(_root_main, "run_startup_checks", None)

logger = logging.getLogger("TradingAgent.CLI")

DEFAULT_API_URL = os.environ.get("MONIKA_API_URL") or os.environ.get("TRADEAGENT_API_URL") or os.environ.get("DASHBOARD_URL") or "http://127.0.0.1:8000"

async def _cmd_status(args):
    console = get_console()
    await init_db()
    async with get_session() as session:
        # 1. System configs
        cfgs = (await session.execute(select(SystemConfig))).scalars().all()
        cfg_map = {c.key: c.value for c in cfgs}
        
        # 2. Positions
        open_real = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
        open_paper = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == 'open'))).scalars().all()
        
        susp_raw = cfg_map.get('suspended_symbols') or "[]"
        import json as _json
        try:
            susp_data = _json.loads(susp_raw)
            susp_list = [str(s['symbol']) for s in susp_data if isinstance(s, dict) and s.get('symbol')]
            susp_str = ", ".join(susp_list) if susp_list else "NONE"
        except Exception:
            susp_str = "NONE"

        from rich.table import Table
        tbl = Table(title=f"[{PHOSPHOR_AMBER}]AI TRADING AGENT STATUS[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}")
        tbl.add_column("Parameter", style=f"bold {BRASS}")
        tbl.add_column("State", style=PAPER)
        tbl.add_column("Indicator", justify="center")

        def _flag_row(param: str, raw_val: Any, is_danger_when_true: bool = True):
            val_bool = str(raw_val).lower() == "true"
            if val_bool:
                badge = stamp_err("ACTIVE") if is_danger_when_true else stamp_ok("ACTIVE")
                state_str = f"[bold {'#8B261E' if is_danger_when_true else '#2D5A27'}]TRUE[/]"
            else:
                badge = stamp_ok("INACTIVE") if is_danger_when_true else stamp_info("STANDBY")
                state_str = f"[{MUTED}]FALSE[/]"
            tbl.add_row(param, state_str, badge)

        _flag_row("Emergency Kill Switch", cfg_map.get('kill_switch'), is_danger_when_true=True)
        _flag_row("System Paused", cfg_map.get('system_paused'), is_danger_when_true=True)
        _flag_row("Budget Paused", cfg_map.get('budget_pause'), is_danger_when_true=True)
        _flag_row("Auto-Execute Mode", cfg_map.get('auto_execute'), is_danger_when_true=False)
        tbl.add_row("Suspended Symbols", susp_str, stamp_warn("SUSPENDED") if susp_str != "NONE" else stamp_ok("CLEAR"))
        tbl.add_row("Open Real Positions", str(len(open_real)), stamp_exec(f"{len(open_real)} LOT") if open_real else f"[{MUTED}][ 0 ][/]")
        tbl.add_row("Open Paper Positions", str(len(open_paper)), stamp_info(f"{len(open_paper)} POS") if open_paper else f"[{MUTED}][ 0 ][/]")

        console.print()
        console.print(tbl)
        console.print()


async def _cmd_pause(args):
    console = get_console()
    await init_db()
    async with get_session() as session:
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == "system_paused"))).scalar_one_or_none()
        if cfg:
            cfg.value = "true"
        else:
            session.add(SystemConfig(key="system_paused", value="true"))
        await session.commit()
    console.print(f"{stamp_ok('PAUSE')} System trading paused successfully.")


async def _cmd_resume(args):
    console = get_console()
    if not getattr(args, "yes", False):
        if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            conf = await asyncio.to_thread(input, f"{stamp_warn('CONFIRM')} Resume trading operations and clear all pause flags? Type 'RESUME': ")
            if conf.strip() != "RESUME":
                console.print(f"{stamp_err('ABORT')} Operation aborted by operator.")
                return
        else:
            console.print(f"{stamp_err('FAILED')} Resume command in non-interactive environment requires '-y' / '--yes' flag.")
            return

    await init_db()
    async with get_session() as session:
        susp = (await session.execute(select(SystemConfig).where(SystemConfig.key == "suspended_symbols"))).scalar_one_or_none()
        if susp:
            susp.value = "[]"
        for key in ("kill_switch", "system_paused", "budget_pause", "trading_paused", "manual_trading_paused"):
            cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
            if cfg:
                cfg.value = "false"
        await session.commit()
    console.print(f"{stamp_ok('RESUME')} System trading resumed (all pause, kill-switch, and suspension flags cleared).")


async def _cmd_unsuspend(args):
    console = get_console()
    await init_db()
    is_all = getattr(args, "all", False) or not getattr(args, "symbol", None)
    sym = None if is_all else args.symbol.strip().upper()
    cleared = []
    ok = False

    async with get_session() as session:
        from utils.analytics.paper_tracker import PaperTracker
        tracker = PaperTracker()
        if is_all or not sym:
            cleared = await tracker.unsuspend_all(session)
        else:
            ok = await tracker.unsuspend_symbol(session, sym)

    if is_all:
        if cleared:
            console.print(f"{stamp_ok('UNSUSPEND')} Successfully lifted trading suspension on all instruments: {', '.join(cleared)}")
        else:
            console.print(f"{stamp_info('STATUS')} No instruments currently suspended.")
    else:
        if ok:
            console.print(f"{stamp_ok('UNSUSPEND')} Successfully lifted trading suspension on symbol {sym}.")
        else:
            console.print(f"{stamp_info('STATUS')} Symbol {sym} not found in active suspension list.")


async def _cmd_kill(args):
    console = get_console()
    if not getattr(args, "yes", False):
        if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            conf = await asyncio.to_thread(input, f"{stamp_warn('KILL')} CRITICAL ALERT: Trigger EMERGENCY KILL SWITCH? Type 'KILL' to confirm: ")
            if conf.strip() != "KILL":
                console.print(f"{stamp_err('ABORT')} Operation aborted by operator.")
                return
        else:
            console.print(f"{stamp_err('FAILED')} Kill switch command in non-interactive environment requires '-y' / '--yes' flag.")
            return

    await init_db()
    async with get_session() as session:
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == "kill_switch"))).scalar_one_or_none()
        if cfg:
            cfg.value = "true"
        else:
            session.add(SystemConfig(key="kill_switch", value="true"))
        await session.commit()
    console.print(f"{stamp_err('EMERGENCY KILL SWITCH')} EMERGENCY KILL SWITCH FLAG SET TO TRUE.")

    # Route kill action through DB flag and Dashboard API safely (no second MT5Client instance)
    api_notified = False
    try:
        import aiohttp
        settings = load_settings()
        port = settings.get("dashboard", {}).get("port", 8000)
        async with aiohttp.ClientSession() as http_sess:
            async with http_sess.post(
                f"http://127.0.0.1:{port}/api/actions/emergency-kill",
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as resp:
                if resp.status in (200, 201):
                    api_notified = True
                    console.print(f"{stamp_ok('FORWARD')} Signal forwarded to running Dashboard daemon API.")
    except Exception:
        pass

    if not api_notified:
        console.print(f"{stamp_info('DATABASE')} Kill signal recorded in database. PositionGuardian will safely close all open positions.")

    console.print(f"{stamp_err('HALTED')} All trading operations permanently halted.")


async def _cmd_positions(args):
    console = get_console()
    await init_db()
    async with get_session() as session:
        open_real = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
        open_paper = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == 'open'))).scalars().all()
        
        from rich.table import Table
        console.print()
        if open_real:
            tbl_real = Table(title=f"[{PHOSPHOR_AMBER}]OPEN REAL POSITIONS[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}")
            tbl_real.add_column("ID", style=MUTED)
            tbl_real.add_column("Ticket", style=f"bold {PAPER}")
            tbl_real.add_column("Symbol", style=f"bold {PHOSPHOR_AMBER}")
            tbl_real.add_column("Side", justify="center")
            tbl_real.add_column("Lots", justify="right")
            tbl_real.add_column("Open Price", justify="right")
            tbl_real.add_column("Stop Loss", justify="right")
            tbl_real.add_column("Take Profit", justify="right")
            for p in open_real:
                side = p.direction.upper()
                side_styled = f"[bold {BULL_PROFIT}]BUY[/]" if side == "BUY" else f"[bold {BEAR_LOSS}]SELL[/]"
                tbl_real.add_row(
                    str(p.id),
                    str(getattr(p, 'mt5_ticket', getattr(p, 'ticket', 'N/A'))),
                    str(p.symbol),
                    side_styled,
                    f"{float(p.volume):.2f}",
                    str(getattr(p, 'entry_price', getattr(p, 'open_price', 'N/A'))),
                    str(p.sl or "-"),
                    str(p.tp or "-"),
                )
            console.print(tbl_real)
        else:
            console.print(f"[{MUTED}]--- OPEN REAL POSITIONS: No open real positions. ---[/]")

        console.print()
        if open_paper:
            tbl_paper = Table(title=f"[{BRASS}]OPEN PAPER POSITIONS[/]", box=LEDGER_BOX, header_style=f"bold {BRASS}")
            tbl_paper.add_column("ID", style=MUTED)
            tbl_paper.add_column("Symbol", style=f"bold {PHOSPHOR_AMBER}")
            tbl_paper.add_column("Side", justify="center")
            tbl_paper.add_column("Lots/Risk", justify="right")
            tbl_paper.add_column("Entry Price", justify="right")
            tbl_paper.add_column("Stop Loss", justify="right")
            tbl_paper.add_column("Take Profit", justify="right")
            for p in open_paper:
                side = p.direction.upper()
                side_styled = f"[bold {BULL_PROFIT}]BUY[/]" if side == "BUY" else f"[bold {BEAR_LOSS}]SELL[/]"
                lots_val = getattr(p, 'lots', getattr(p, 'risk_pct', 'N/A'))
                tbl_paper.add_row(
                    str(p.id),
                    str(p.symbol),
                    side_styled,
                    f"{float(lots_val):.2f}" if isinstance(lots_val, (int, float)) else str(lots_val),
                    str(p.entry_price),
                    str(getattr(p, 'stop_loss', getattr(p, 'sl', '-'))),
                    str(getattr(p, 'take_profit', getattr(p, 'tp', '-'))),
                )
            console.print(tbl_paper)
        else:
            console.print(f"[{MUTED}]--- OPEN PAPER POSITIONS: No open paper positions. ---[/]")
        console.print()


async def _acli_run(args):
    """Asynchronous CLI execution pipeline."""
    if not acquire_single_instance_lock():
        logger.error("Another TradingAgent instance is currently active. Aborting.")
        sys.exit(1)

    # 1. Load config
    if getattr(args, "config", None):
        if not os.path.exists(args.config):
            logger.critical(f"Config file not found at: {args.config}")
            raise FileNotFoundError(f"Custom configuration file not found: {args.config}")
        settings = load_all_config(settings_path=args.config)
    else:
        settings = load_all_config()

    # 2. Configure Trading Mode
    mode = getattr(args, "mode", "paper")
    is_dry_run = (mode == "paper")
    if mode == "live":
        if not getattr(args, "confirm_live", False):
            if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                confirmation = await asyncio.to_thread(input, "CRITICAL WARNING: Live capital execution deployment requested. Type 'CONFIRM_LIVE' to proceed: ")
                if confirmation.strip() != "CONFIRM_LIVE":
                    logger.warning("Live capital execution cancelled by operator. Aborting.")
                    sys.exit(0)
            else:
                logger.critical("Live capital execution requires explicit operator confirmation or '--confirm-live' flag. Aborting.")
                sys.exit(1)
        settings.setdefault("trading", {})["auto_execute"] = True
        logger.warning("⚠️ Starting in LIVE execution mode. Real capital will be traded via MT5.")
    else:
        settings.setdefault("paper_trading", {})["enabled"] = True
        settings.setdefault("trading", {}).setdefault("paper_trading", {})["enabled"] = True
        logger.info("Starting in PAPER trading mode (simulation).")

    # Configure Gemini Rate Limiter limits from settings
    from utils.api.gemini_rate_limiter import configure_from_settings
    configure_from_settings(settings)

    # 3. Init DB & Health Checks
    logger.info("Initializing database...")
    await init_db()

    logger.info("Running startup health checks...")
    checks_ok = await run_startup_checks(settings)
    if not checks_ok:
        logger.critical("Startup checks failed. Aborting.")
        await close_db()
        sys.exit(1)

    # 4. Instantiate & Start Agent
    agent = TradingAgent(settings=settings, dry_run=is_dry_run)
    try:
        await agent.start()
    finally:
        await close_db()


async def _cmd_tui(args):
    """Launch rich Textual terminal dashboard."""
    from cli.tui import run_tui
    run_tui(
        api_url=getattr(args, "url", DEFAULT_API_URL),
        api_key=getattr(args, "token", None),
        refresh_interval=getattr(args, "refresh", 5),
    )


async def _cmd_chat(args):
    """Launch interactive REPL chat with agent."""
    from cli.tui_chat import run_cli_chat
    await run_cli_chat(
        api_url=getattr(args, "url", DEFAULT_API_URL),
        api_key=getattr(args, "token", None),
        session_id=getattr(args, "session_id", None),
        offline=getattr(args, "offline", False),
        model=getattr(args, "model", "auto"),
    )


async def _cmd_config_show(args):
    """Show system configuration or section."""
    from rich.syntax import Syntax
    import yaml
    console = get_console()

    url = getattr(args, "url", DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")
    section = getattr(args, "section", None)
    is_json = getattr(args, "json", False)

    settings = None
    try:
        headers = {"X-API-Key": token} if token else {}
        timeout = aiohttp.ClientTimeout(total=2.0)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
            res = await sess.get(f"{url.rstrip('/')}/api/config/settings")
            if res.status == 200:
                body = await res.json()
                settings = body.get("settings")
    except Exception:
        settings = None

    if settings is None:
        settings = load_settings()

    target = settings
    if section:
        parts = section.split(".")
        for p in parts:
            if isinstance(target, dict) and p in target:
                target = target[p]
            else:
                console.print(f"{stamp_err('ERROR')} Configuration path '{section}' not found.")
                return

    if is_json:
        import json as _json
        formatted = _json.dumps(target, indent=2)
        syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
    else:
        formatted = yaml.dump(target, default_flow_style=False, sort_keys=False, allow_unicode=True)
        syntax = Syntax(formatted, "yaml", theme="monokai", line_numbers=False)

    console.print(f"[bold {PHOSPHOR_AMBER}]── Configuration: {section or 'Full settings.yaml'} ──[/]")
    console.print(syntax)


async def _cmd_config_set(args):
    """Update configuration parameter via API or local settings.yaml with validation."""
    console = get_console()
    assignments = getattr(args, "assignments", [])
    reason = getattr(args, "reason", "Updated via CLI")
    url = getattr(args, "url", DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")

    if not assignments:
        console.print(f"{stamp_warn('CONFIG')} No configuration parameter specified.")
        return

    update_dict: Dict[str, Any] = {}
    for item in assignments:
        if "=" not in item:
            console.print(f"{stamp_err('CONFIG')} Invalid assignment '{item}'. Expected format 'path.to.key=value'.")
            return
        key_path, raw_val = item.split("=", 1)
        key_path = key_path.strip()
        raw_val = raw_val.strip()

        val: Any
        if raw_val.lower() == "true":
            val = True
        elif raw_val.lower() == "false":
            val = False
        elif raw_val.lower() in ("none", "null"):
            val = None
        elif raw_val.startswith(("[", "{")) and raw_val.endswith(("]", "}")):
            import json as _json
            try:
                val = _json.loads(raw_val)
            except Exception:
                val = raw_val
        else:
            try:
                if "." in raw_val:
                    val = float(raw_val)
                else:
                    val = int(raw_val)
            except ValueError:
                val = raw_val

        from config.key_validator import validate_config_key
        key_err = validate_config_key(key_path)
        if key_err:
            console.print(f"{stamp_err('KEY')} {key_err}")
            return

        keys = key_path.split(".")
        cur = update_dict
        for k in keys[:-1]:
            if k not in cur:
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = val

    # Try API first (unless custom local config path is explicitly provided)
    api_success = False
    if not getattr(args, "config", None):
        try:
            headers = {"X-API-Key": token} if token else {}
            timeout = aiohttp.ClientTimeout(total=3.0)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
                res = await sess.put(
                    f"{url.rstrip('/')}/api/config/settings",
                    json={"settings": update_dict, "reason": reason},
                )
                if res.status == 200:
                    console.print(f"{stamp_ok('CONFIG')} Configuration successfully updated via API ({reason}).")
                    api_success = True
                elif res.status == 422:
                    err = await res.json()
                    console.print(f"{stamp_err('VALIDATION')} {err.get('message', 'Invalid value')}")
                    return
                elif res.status in (401, 403):
                    console.print(f"{stamp_err('ACCESS')} Permission denied: Updating configuration via API requires Admin role. Check API token.")
                    return
                else:
                    err_text = await res.text()
                    console.print(f"{stamp_err('API')} Server returned error ({res.status}): {err_text[:200]}")
                    return
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError, aiohttp.ClientConnectionError):
            api_success = False
        except Exception as ex:
            if getattr(args, "url", None) and args.url != DEFAULT_API_URL:
                console.print(f"{stamp_err('CONNECTION')} Failed to connect to {url}: {ex}")
                return
            api_success = False

    if not api_success:
        import shutil
        import yaml
        from config.settings import validate_config, _deep_merge
        from database.models import ActivityLog

        settings_path = getattr(args, "config", None)
        if not settings_path:
            for cand in (
                os.path.join(_parent_dir, "config", "settings.yaml"),
                "trading-agent/config/settings.yaml",
                "config/settings.yaml",
            ):
                if os.path.exists(cand):
                    settings_path = cand
                    break
        if not settings_path:
            settings_path = "trading-agent/config/settings.yaml"

        existing = load_settings(settings_path)
        merged = _deep_merge(existing, update_dict)

        try:
            validate_config(merged)
        except Exception as e:
            console.print(f"{stamp_err('VALIDATION')} {e}")
            return

        from config.atomic_writer import AtomicConfigWriter
        try:
            AtomicConfigWriter.update_in_place(settings_path, update_dict, create_backup=True)
        except Exception as e:
            console.print(f"{stamp_err('CONFIG')} Failed to update configuration: {e}")
            return

        try:
            await init_db()
            async with get_session() as session:
                session.add(ActivityLog(
                    category="system",
                    description=f"Config updated via CLI: {assignments} ({reason})",
                    actor="cli_operator",
                ))
                await session.commit()
        except Exception:
            pass

        console.print(f"{stamp_ok('CONFIG')} Configuration updated and verified in {settings_path}! (Backup created)")


async def _cmd_config_get(args):
    """Retrieve and display a specific configuration value."""
    console = get_console()
    key_path = getattr(args, "key", "")
    is_raw = getattr(args, "raw", False)
    if not key_path:
        console.print(f"{stamp_warn('CONFIG')} No configuration key specified.")
        return

    from config.settings import load_settings
    settings = load_settings(getattr(args, "config", None))
    parts = key_path.split(".")
    val = settings
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found in configuration.")
            return

    val_str = str(val)
    if not is_raw and any(s in key_path.lower() for s in ("key", "password", "secret", "token")):
        val_str = "********" if val else ""

    console.print(f"[bold {BRASS}]{key_path}[/]: {val_str}")


async def _cmd_config_unset(args):
    """Remove a configuration key."""
    console = get_console()
    key_path = getattr(args, "key", "")
    if not key_path:
        console.print(f"{stamp_warn('CONFIG')} No configuration key specified.")
        return

    from config.settings import load_settings, validate_config
    from config.atomic_writer import AtomicConfigWriter

    settings_path = getattr(args, "config", None) or "config/settings.yaml"
    settings = load_settings(settings_path)
    parts = key_path.split(".")
    cur = settings
    for p in parts[:-1]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found.")
            return

    if isinstance(cur, dict) and parts[-1] in cur:
        del cur[parts[-1]]
        try:
            validate_config(settings)
            import yaml
            with open(settings_path, "w", encoding="utf-8") as f:
                yaml.dump(settings, f, default_flow_style=False)
            console.print(f"{stamp_ok('CONFIG')} Successfully unset '{key_path}'.")
        except Exception as e:
            console.print(f"{stamp_err('CONFIG')} Failed to unset '{key_path}': {e}")
    else:
        console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found.")


async def _cmd_config_edit(args):
    """Open settings.yaml in default editor and validate upon close."""
    import subprocess
    console = get_console()
    settings_path = getattr(args, "config", None) or "config/settings.yaml"
    if not os.path.exists(settings_path):
        for cand in ("trading-agent/config/settings.yaml", "config/settings.yaml"):
            if os.path.exists(cand):
                settings_path = cand
                break

    editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "nano")
    console.print(f"{stamp_info('EDIT')} Opening {settings_path} with {editor}...")
    try:
        res = subprocess.run([editor, settings_path])
        if res.returncode == 0:
            from config.settings import load_settings, validate_config
            try:
                cfg = load_settings(settings_path)
                validate_config(cfg)
                console.print(f"{stamp_ok('VALIDATED')} Configuration file is valid and ready.")
            except Exception as val_err:
                console.print(f"{stamp_err('INVALID')} Configuration error detected: {val_err}")
    except Exception as e:
        console.print(f"{stamp_err('EDIT')} Failed to launch editor: {e}")


async def _cmd_onboarding(args):
    """Launch trader onboarding personalization wizard."""
    from cli.onboarding_trader import TraderOnboarding
    onboarding = TraderOnboarding()
    onboarding.run_interview()


async def _cmd_config(args):
    """Handle config subcommand routing."""
    action = getattr(args, "config_action", None)
    if action == "show":
        await _cmd_config_show(args)
    elif action == "set":
        await _cmd_config_set(args)
    elif action == "get":
        await _cmd_config_get(args)
    elif action == "unset":
        await _cmd_config_unset(args)
    elif action == "edit":
        await _cmd_config_edit(args)
    else:
        await _cmd_config_show(args)


async def _cmd_sessions(args):
    """List conversation sessions with metadata."""
    from rich.table import Table
    console = get_console()

    url = getattr(args, "url", DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")
    source = getattr(args, "source", "all")
    limit = getattr(args, "limit", 20)

    sessions_data = None
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            headers = {"X-API-Key": token} if token else {}
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
                q = f"?limit={limit}"
                if source != "all":
                    q += f"&source={source}"
                res = await sess.get(f"{url.rstrip('/')}/api/sessions{q}")
                if res.status == 200:
                    sessions_data = await res.json()
        except Exception:
            sessions_data = None

    if sessions_data is None:
        from database.models import TelegramConversation
        from sqlalchemy import func, desc

        await init_db()
        async with get_session() as session:
            query = (
                select(
                    TelegramConversation.telegram_user_id,
                    func.count(TelegramConversation.id).label("message_count"),
                    func.max(TelegramConversation.timestamp).label("last_active"),
                )
                .group_by(TelegramConversation.telegram_user_id)
                .order_by(desc("last_active"))
                .limit(limit)
            )
            if source == "dashboard":
                query = query.where(TelegramConversation.telegram_user_id.like("dash%"))
            elif source == "cli":
                query = query.where(TelegramConversation.telegram_user_id.like("cli%"))
            elif source == "telegram":
                query = query.where(
                    ~TelegramConversation.telegram_user_id.like("dash%"),
                    ~TelegramConversation.telegram_user_id.like("cli%"),
                )

            rows = (await session.execute(query)).all()
            sessions_data = []
            for r in rows:
                uid = str(r.telegram_user_id)
                latest = (await session.execute(
                    select(TelegramConversation.message)
                    .where(TelegramConversation.telegram_user_id == uid)
                    .order_by(TelegramConversation.timestamp.desc())
                    .limit(1)
                )).first()
                sessions_data.append({
                    "session_id": uid,
                    "source": "dashboard" if uid.startswith("dash") else ("cli" if uid.startswith("cli") else "telegram"),
                    "message_count": r.message_count,
                    "last_active": r.last_active.isoformat() if r.last_active else "N/A",
                    "last_message": latest[0][:80] if latest else "",
                })

    table = Table(title=f"[{PHOSPHOR_AMBER}]Conversation Sessions[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}")
    table.add_column("Session ID", style=PAPER)
    table.add_column("Source", justify="center")
    table.add_column("Messages", justify="right", style=f"bold {BRASS}")
    table.add_column("Last Active", style=MUTED)
    table.add_column("Last Message", style=PAPER)

    if not sessions_data:
        console.print(f"[{MUTED}]No active conversation sessions found.[/]")
        return

    for s in sessions_data:
        src = s.get("source", "unknown").upper()
        if src == "DASHBOARD":
            src_badge = stamp_ok("DASHBOARD")
        elif src == "CLI":
            src_badge = stamp_exec("CLI")
        else:
            src_badge = stamp_info("TELEGRAM")

        table.add_row(
            str(s.get("session_id", "N/A")),
            src_badge,
            str(s.get("message_count", 0)),
            str(s.get("last_active", "N/A"))[:19].replace("T", " "),
            str(s.get("last_message", "")),
        )

    console.print()
    console.print(table)
    console.print()


async def _cmd_logs(args):
    """Stream or tail live activity logs."""
    console = get_console()

    lines = getattr(args, "lines", 20)
    follow = getattr(args, "follow", False)
    category = getattr(args, "category", None)
    severity = getattr(args, "severity", None)

    from database.models import ActivityLog

    await init_db()

    def _render_log(log_item: Dict[str, Any]):
        ts = log_item.get("timestamp") or ""
        if "T" in ts:
            ts = ts.split("T")[1][:8]
        cat = str(log_item.get("category", "system")).lower()
        actor = str(log_item.get("actor", "agent"))
        desc = str(log_item.get("description", ""))

        if cat in ("error", "critical"):
            cat_badge = stamp_err("ERROR")
        elif cat in ("warn", "warning", "risk"):
            cat_badge = stamp_warn("RISK")
        elif cat in ("trade", "trading", "order"):
            cat_badge = stamp_exec("TRADE")
        elif cat in ("analysis", "debate"):
            cat_badge = stamp_info("ANALYSIS")
        else:
            cat_badge = f"[{MUTED}][ SYSTEM ][/]"

        console.print(f"[{MUTED}]{ts}[/] {cat_badge} [bold {BRASS}]{actor}:[/] [{PAPER}]{desc}[/]")

    last_seen_id = 0
    async with get_session() as session:
        q = select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(lines)
        if category:
            q = q.where(ActivityLog.category == category)
        if severity:
            sev_lower = severity.lower()
            q = q.where(
                ActivityLog.category.ilike(f"%{sev_lower}%") |
                ActivityLog.description.ilike(f"%{sev_lower}%")
            )
        items = (await session.execute(q)).scalars().all()
        for item in reversed(items):
            last_seen_id = max(last_seen_id, item.id)
            _render_log({
                "id": item.id,
                "timestamp": item.timestamp.isoformat() if item.timestamp else "",
                "category": item.category,
                "actor": item.actor,
                "description": item.description,
            })

    if not follow:
        return

    console.print(f"[{MUTED}]Streaming real-time system activity logs (Press Ctrl+C to terminate)...[/]")
    try:
        while True:
            await asyncio.sleep(1.5)
            async with get_session() as session:
                q = select(ActivityLog).where(ActivityLog.id > last_seen_id).order_by(ActivityLog.timestamp.asc())
                if category:
                    q = q.where(ActivityLog.category == category)
                if severity:
                    sev_lower = severity.lower()
                    q = q.where(
                        ActivityLog.category.ilike(f"%{sev_lower}%") |
                        ActivityLog.description.ilike(f"%{sev_lower}%")
                    )
                new_items = (await session.execute(q)).scalars().all()
                for item in new_items:
                    last_seen_id = max(last_seen_id, item.id)
                    _render_log({
                        "id": item.id,
                        "timestamp": item.timestamp.isoformat() if item.timestamp else "",
                        "category": item.category,
                        "actor": item.actor,
                        "description": item.description,
                    })
    except (asyncio.CancelledError, KeyboardInterrupt):
        console.print(f"\n[{MUTED}]Log stream terminated by operator.[/]")


async def _cmd_doctor(args):
    from cli.doctor import SystemDoctor
    doc = SystemDoctor(
        fix=getattr(args, "fix", False),
        live_probes=not getattr(args, "offline", False),
        verbose=getattr(args, "verbose", False)
    )
    await doc.run_diagnostics()
    code = doc.render_report()
    if code != 0 and not getattr(args, "fix", False):
        sys.exit(code)


async def _cmd_setup(args):
    from cli.setup_wizard import SetupWizard
    wizard = SetupWizard(settings_path=getattr(args, "config", None))
    section = getattr(args, "section", "all")
    quick = getattr(args, "quick", False)
    wizard.run_wizard(section=section, quick=quick)


async def _cmd_profile(args):
    from cli.profile_manager import ProfileManager
    from cli.theme import (
        get_console, stamp_ok, stamp_err, stamp_info, stamp_warn,
        PHOSPHOR_AMBER, BRASS, LEDGER_BOX, PAPER, MUTED
    )
    from rich.table import Table

    pm = ProfileManager()
    console = get_console()
    action = getattr(args, "profile_action", "list") or "list"

    if action == "list":
        profiles = pm.list_profiles()
        tbl = Table(title=f"[{PHOSPHOR_AMBER}]MONIKA PROFILES[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}")
        tbl.add_column("Profile", style=f"bold {BRASS}")
        tbl.add_column("Status", justify="center")
        tbl.add_column("Config Path", style=PAPER)

        for p in profiles:
            status = stamp_ok("ACTIVE") if p.is_active else f"[{MUTED}]STANDBY[/]"
            tbl.add_row(p.name, status, p.path)
        console.print()
        console.print(tbl)
        console.print()
    elif action == "use":
        name = getattr(args, "name", "default")
        try:
            pm.set_active_profile(name)
            console.print(f"{stamp_ok('PROFILE')} Switched active profile to: [bold {BRASS}]{name}[/]")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to switch profile: {e}")
    elif action == "create":
        name = getattr(args, "name", "")
        clone = getattr(args, "clone", None)
        try:
            p_dir = pm.create_profile(name, clone_from=clone)
            console.print(f"{stamp_ok('PROFILE')} Created profile [bold {BRASS}]{name}[/] at {p_dir}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to create profile: {e}")
    elif action == "delete":
        name = getattr(args, "name", "")
        try:
            pm.delete_profile(name)
            console.print(f"{stamp_ok('PROFILE')} Deleted profile [bold {BRASS}]{name}[/]")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to delete profile: {e}")
    elif action == "export":
        name = getattr(args, "name", "")
        zip_path = getattr(args, "zip_path", f"{name}.zip")
        try:
            out_path = pm.export_profile(name, zip_path)
            console.print(f"{stamp_ok('PROFILE')} Exported profile [bold {BRASS}]{name}[/] to {out_path}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to export profile: {e}")
    elif action == "import":
        zip_path = getattr(args, "zip_path", "")
        name = getattr(args, "name", None)
        try:
            target_dir = pm.import_profile(zip_path, new_name=name)
            console.print(f"{stamp_ok('PROFILE')} Imported profile to {target_dir}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to import profile: {e}")


async def _cmd_ask(args):
    console = get_console()
    question = " ".join(args.question) if isinstance(args.question, list) else str(args.question)
    if not question.strip():
        console.print(f"{stamp_err('ASK')} No question provided.")
        return

    is_raw = getattr(args, "raw", False)
    if not is_raw:
        console.print(f"{stamp_info('ASK')} Querying Monika: [bold]{question}[/]")

    from telegram_bot.chat_agent import ChatAgent
    from config.settings import load_all_config
    settings = load_all_config()
    agent = ChatAgent(settings, user_id="cli_user", is_admin=True)

    reply_text, pending = await agent.handle(question)
    if is_raw:
        print(reply_text)
    else:
        console.print(f"\n{reply_text}\n")
        if pending:
            console.print(f"{stamp_warn('PROPOSAL')} Proposed action: {pending.description} (Action ID: {pending.action_id})")

    out_json = getattr(args, "output_json", None)
    if out_json:
        import json as _json
        payload = {
            "query": question,
            "response": reply_text,
            "has_pending_action": pending is not None,
            "pending_action": pending.to_dict() if pending and hasattr(pending, "to_dict") else None,
        }
        try:
            with open(out_json, "w", encoding="utf-8") as f:
                _json.dump(payload, f, indent=2)
            if not is_raw:
                console.print(f"{stamp_ok('EXPORT')} Saved query output to: {out_json}")
        except Exception as e:
            if not is_raw:
                console.print(f"{stamp_err('EXPORT')} Failed to write output JSON: {e}")


async def _cmd_analyze(args):
    console = get_console()
    symbol = args.symbol.strip().upper().replace("/", "")
    context = getattr(args, "context", "")
    console.print(f"{stamp_info('ANALYZE')} Running ad-hoc analysis for [bold {BRASS}]{symbol}[/]...")

    from agent.agent_loop import SystemAgentLoop
    from config.settings import load_all_config
    settings = load_all_config()
    agent_loop = SystemAgentLoop(settings=settings)

    def _progress(msg):
        console.print(f"  [{MUTED}]• {msg}[/]")

    res = await agent_loop.execute_ad_hoc_analysis(
        symbol=symbol,
        progress_callback=_progress,
        custom_context=context or f"Ad-hoc analysis requested via CLI for {symbol}"
    )
    summary = res.get("formatted_summary") or f"Analysis for {symbol} completed."
    console.print(f"\n{summary}\n")



class MonikaArgumentParser(argparse.ArgumentParser):
    """Custom argument parser providing fuzzy suggestions for command typos."""
    def error(self, message):
        import difflib
        import re
        m = re.search(r"invalid choice:\s*'([^']+)'\s*\(choose from (.*?)\)", message)
        if m:
            typo = m.group(1)
            choices = [c.strip().strip("'") for c in m.group(2).split(",")]
            matches = difflib.get_close_matches(typo, choices, n=2, cutoff=0.5)
            suggestion = f"\nDid you mean: {', '.join(matches)}?" if matches else ""
            sys.stderr.write(f"monika: error: '{typo}' is not a valid command.{suggestion}\nRun 'python -m cli.main --help' to view all commands.\n")
            sys.exit(2)
        super().error(message)


def parse_args(args_list=None):
    parser = MonikaArgumentParser(description="AI Trading Agent CLI Interface")
    parser.add_argument("-p", "--profile", type=str, default=None, help="Target isolated environment profile (e.g. paper, live, propfirm)")
    subparsers = parser.add_subparsers(dest="command", help="Administrative subcommands")

    # Command: run (default)
    run_parser = subparsers.add_parser("run", help="Start the trading agent daemon")
    run_parser.add_argument("--mode", type=str, choices=["live", "paper"], default="paper", help="Trading execution mode")
    run_parser.add_argument("--confirm-live", action="store_true", default=False, help="Explicit acknowledgement for live trading mode")
    run_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Command: status
    subparsers.add_parser("status", help="Show system status, flags, and open positions")

    # Command: pause
    subparsers.add_parser("pause", help="Pause all new trading proposals")

    # Command: resume
    resume_parser = subparsers.add_parser("resume", help="Resume trading (clears pause flags)")
    resume_parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation")

    # Command: kill
    kill_parser = subparsers.add_parser("kill", help="Trigger emergency kill switch")
    kill_parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation")

    # Command: positions
    subparsers.add_parser("positions", help="List all open positions (real & paper)")

    # Command: unsuspend
    unsuspend_parser = subparsers.add_parser("unsuspend", help="Unsuspend symbols blocked by streak losses")
    unsuspend_parser.add_argument("--symbol", type=str, default=None, help="Specific symbol to unsuspend (e.g. EURUSD)")
    unsuspend_parser.add_argument("--all", action="store_true", default=False, help="Unsuspend all symbols")

    # Command: tui
    tui_parser = subparsers.add_parser("tui", help="Launch rich Textual terminal dashboard")
    tui_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    tui_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    tui_parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds")
    tui_parser.add_argument("--theme", type=str, default=None, choices=["retro_vintage", "modern_dark", "high_contrast", "daylight"], help="TUI color theme")

    # Command: chat
    chat_parser = subparsers.add_parser("chat", help="Interactive REPL chat with agent")
    chat_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    chat_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    chat_parser.add_argument("--session-id", type=str, default=None, help="Conversation session ID")
    chat_parser.add_argument("--offline", action="store_true", default=False, help="Force direct local engine (bypasses API server)")
    chat_parser.add_argument("--model", type=str, default="auto", choices=["auto", "fast", "medium", "analyze", "research"], help="Model routing preference")

    # Command: config
    config_parser = subparsers.add_parser("config", help="Inspect and update system configuration")
    config_sub = config_parser.add_subparsers(dest="config_action", help="Config actions: show, set")

    show_parser = config_sub.add_parser("show", help="Show current configuration or a specific section")
    show_parser.add_argument("section", nargs="?", default=None, help="Specific section path (e.g. trading.risk)")
    show_parser.add_argument("--json", action="store_true", default=False, help="Output in JSON format")
    show_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    show_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    show_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    set_parser = config_sub.add_parser("set", help="Update configuration parameter (e.g. trading.risk.max_daily_drawdown_percent=4.0)")
    set_parser.add_argument("assignments", nargs="+", help="One or more key=value assignments")
    set_parser.add_argument("--reason", type=str, default="Updated via CLI", help="Audit reason for config change")
    set_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    set_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    set_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    get_parser = config_sub.add_parser("get", help="Retrieve specific configuration parameter")
    get_parser.add_argument("key", type=str, help="Parameter key path (e.g. trading.risk.risk_percent_per_trade)")
    get_parser.add_argument("--raw", action="store_true", default=False, help="Show raw unmasked value")
    get_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    unset_parser = config_sub.add_parser("unset", help="Unset a configuration parameter")
    unset_parser.add_argument("key", type=str, help="Parameter key path to remove")
    unset_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    edit_parser = config_sub.add_parser("edit", help="Open settings.yaml in default editor and validate upon exit")
    edit_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Command: onboarding
    subparsers.add_parser("onboarding", help="Launch trader personalization and risk style onboarding interview")

    # Command: sessions
    sessions_parser = subparsers.add_parser("sessions", help="List conversation sessions with metadata")
    sessions_parser.add_argument("--source", type=str, choices=["all", "telegram", "dashboard", "cli"], default="all", help="Filter by conversation source")
    sessions_parser.add_argument("--limit", type=int, default=20, help="Max sessions to display")
    sessions_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    sessions_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")

    # Command: logs
    logs_parser = subparsers.add_parser("logs", help="Stream activity logs (tail -f style)")
    logs_parser.add_argument("-n", "--lines", type=int, default=20, help="Initial number of log lines to show")
    logs_parser.add_argument("-f", "--follow", action="store_true", default=False, help="Follow log output in real time")
    logs_parser.add_argument("--category", type=str, default=None, help="Filter by category (e.g. trading, risk, system, analysis)")
    logs_parser.add_argument("--level", "--severity", dest="severity", type=str, default=None, help="Filter by severity")
    logs_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    logs_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")

    # Command: doctor
    doctor_parser = subparsers.add_parser("doctor", help="Run comprehensive system diagnostics with optional auto-fix")
    doctor_parser.add_argument("--fix", action="store_true", default=False, help="Attempt to auto-fix recoverable issues")
    doctor_parser.add_argument("--offline", action="store_true", default=False, help="Skip live database and model connection probes")
    doctor_parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Show verbose diagnostic details")

    # Command: setup
    setup_parser = subparsers.add_parser("setup", help="Launch interactive onboarding setup wizard")
    setup_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")
    setup_parser.add_argument("--section", type=str, choices=["all", "mt5", "db", "llm", "risk"], default="all", help="Configure specific section only")
    setup_parser.add_argument("--quick", action="store_true", default=False, help="Quick setup with sensible defaults")

    # Command: profile
    profile_parser = subparsers.add_parser("profile", help="Manage isolated trading environments and profiles")
    prof_sub = profile_parser.add_subparsers(dest="profile_action", help="Profile actions: list, use, create, delete, export, import")
    prof_sub.add_parser("list", help="List all trading profiles")
    use_p = prof_sub.add_parser("use", help="Switch active profile")
    use_p.add_argument("name", type=str, help="Name of the profile to activate")
    create_p = prof_sub.add_parser("create", help="Create new isolated profile")
    create_p.add_argument("name", type=str, help="Name of the new profile")
    create_p.add_argument("--clone", type=str, default=None, help="Optional source profile to clone configuration from")
    del_p = prof_sub.add_parser("delete", help="Delete an isolated profile")
    del_p.add_argument("name", type=str, help="Name of the profile to delete")
    exp_p = prof_sub.add_parser("export", help="Export profile to zip archive")
    exp_p.add_argument("name", type=str, help="Name of the profile to export")
    exp_p.add_argument("zip_path", type=str, help="Output path for zip archive")
    imp_p = prof_sub.add_parser("import", help="Import profile from zip archive")
    imp_p.add_argument("zip_path", type=str, help="Path to zip archive")
    imp_p.add_argument("--name", type=str, default=None, help="Optional new profile name")

    # Command: ask (one-shot question to agent)
    ask_parser = subparsers.add_parser("ask", help="Send a single question or command to Monika chat agent")
    ask_parser.add_argument("question", nargs="*", type=str, help="Question or instruction for Monika")
    ask_parser.add_argument("-r", "--raw", action="store_true", default=False, help="Print raw response without Rich styling or stamps")
    ask_parser.add_argument("--output-json", type=str, default=None, help="Save query result and proposal metadata to JSON file")

    # Command: analyze (one-shot ad-hoc analysis for symbol)
    analyze_parser = subparsers.add_parser("analyze", help="Trigger ad-hoc multi-timeframe analysis for a symbol")
    analyze_parser.add_argument("symbol", type=str, help="Symbol to analyze (e.g. EURUSD, XAUUSD)")
    analyze_parser.add_argument("--context", type=str, default="", help="Optional custom analytical context")

    # Command: mcp-serve (Launch Model Context Protocol server)
    mcp_parser = subparsers.add_parser("mcp-serve", help="Launch Monika as a Model Context Protocol (MCP) server over stdio")
    mcp_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Backward compatibility and top-level headless query flag
    parser.add_argument("-q", "--query", type=str, default=None, help="Execute single one-shot query to Monika and exit")
    parser.add_argument("-r", "--raw", action="store_true", default=False, help="Print raw response without formatting")
    parser.add_argument("--output-json", type=str, default=None, help="Save one-shot query result to JSON file")
    parser.add_argument("--mode", type=str, choices=["live", "paper"], default="paper", help="Trading execution mode")
    parser.add_argument("--confirm-live", action="store_true", default=False, help="Explicit acknowledgement for live trading mode")
    parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    parsed = parser.parse_args(args_list)

    # Intercept root-level -q / --query flag and redirect to 'ask' command
    if getattr(parsed, "query", None):
        parsed.command = "ask"
        parsed.question = [parsed.query]

    if getattr(parsed, "profile", None):
        from cli.profile_manager import ProfileManager
        pm = ProfileManager()
        pm.set_active_profile(parsed.profile)
        p_cfg = pm.get_settings_path_for_active()
        if p_cfg and not getattr(parsed, "config", None):
            parsed.config = p_cfg
        # Isolate MT5 common files directory per profile
        if os.environ.get("MT5_COMMON_FILES_PATH"):
            os.environ["MT5_COMMON_FILES_PATH"] = os.path.join(
                os.environ["MT5_COMMON_FILES_PATH"], "profiles", parsed.profile
            )

    if not parsed.command:
        parsed.command = "status"
    return parsed


async def _dispatch_cli(args):
    try:
        if args.command == "status":
            await _cmd_status(args)
        elif args.command == "ask":
            await _cmd_ask(args)
        elif args.command == "analyze":
            await _cmd_analyze(args)
        elif args.command == "pause":
            await _cmd_pause(args)
        elif args.command == "resume":
            await _cmd_resume(args)
        elif args.command == "unsuspend":
            await _cmd_unsuspend(args)
        elif args.command == "kill":
            await _cmd_kill(args)
        elif args.command == "positions":
            await _cmd_positions(args)
        elif args.command == "chat":
            await _cmd_chat(args)
        elif args.command == "config":
            await _cmd_config(args)
        elif args.command == "sessions":
            await _cmd_sessions(args)
        elif args.command == "logs":
            await _cmd_logs(args)
        elif args.command == "doctor":
            await _cmd_doctor(args)
        elif args.command == "setup":
            await _cmd_setup(args)
        elif args.command == "onboarding":
            await _cmd_onboarding(args)
        elif args.command == "profile":
            await _cmd_profile(args)
        elif args.command in ("mcp-serve", "mcp_serve"):
            from analysis.mcp.server import MonikaMcpServer
            from config.settings import load_settings
            cfg = load_settings(getattr(args, "config", None))
            server = MonikaMcpServer(settings=cfg)
            await server.run_stdio()
        else:
            # First-run interceptor for daemon execution
            from utils.infra.env_file_manager import EnvFileManager
            if not EnvFileManager.is_configured():
                if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                    from rich.prompt import Confirm
                    from cli.theme import get_console, stamp_warn
                    console = get_console()
                    console.print(f"\n{stamp_warn('NOT CONFIGURED')} Monika belum terkonfigurasi (kredensial minimum MT5, DB, atau LLM belum lengkap).")
                    if Confirm.ask("Jalankan Interactive Setup Wizard sekarang?", default=True):
                        await _cmd_setup(args)
                        if not EnvFileManager.is_configured():
                            console.print(f"{stamp_warn('ABORT')} Konfigurasi belum selesai. Menutup proses.\n")
                            return
                    else:
                        console.print("Jalankan `python -m cli.main setup` untuk mengonfigurasi kredensial.\n")
                        return
                else:
                    logger.critical("Monika is not configured (missing MT5_ACCOUNT, DATABASE_URL, or LLM keys). Run 'python -m cli.main setup' first.")
                    sys.exit(1)

            print(f"Starting Monika (MT5 Trading Agent) in {getattr(args, 'mode', 'paper').upper()} mode...")
            await _acli_run(args)
    finally:
        try:
            await close_db()
        except Exception:
            pass


def run():
    args = parse_args()
    from logging_observability.activity_logger import setup_logging
    setup_logging(level=logging.INFO)

    if args.command == "tui":
        from cli.tui import run_tui
        run_tui(
            api_url=getattr(args, "url", DEFAULT_API_URL),
            api_key=getattr(args, "token", None),
            refresh_interval=getattr(args, "refresh", 5),
            theme_name=getattr(args, "theme", None),
        )
        return

    from utils.infra.event_loop import run_async

    try:
        run_async(_dispatch_cli(args))
    except KeyboardInterrupt:
        logger.info("CLI execution terminated by user.")
    except Exception as e:
        logger.critical(f"CLI encountered fatal exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()

