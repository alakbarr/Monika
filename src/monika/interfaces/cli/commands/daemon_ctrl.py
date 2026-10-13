# ==============================================================================
# File: interfaces/cli/commands/daemon_ctrl.py
# ==============================================================================

"""
Daemon Lifecycle and Direct Control Commands for Monika.
Handles run, stop, pause, resume, unsuspend, kill, status, positions, tui, and chat.
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import aiohttp

from monika.interfaces.cli.context import cli_main
from monika.application.services.portfolio_service import PortfolioService
from monika.application.services.trading_service import TradingService
from monika.infrastructure.database.repositories.system_config_repository import SystemConfigRepository
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    LEDGER_BOX,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
    stamp_err,
    stamp_exec,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

logger = logging.getLogger("TradingAgent.CLI")


async def _cmd_status(args: Any) -> None:
    console = cli_main.get_console()
    await cli_main.init_db()
    async with cli_main.get_session() as session:
        # 1. System configs
        cfg_repo = SystemConfigRepository(session)
        cfgs = await cfg_repo.get_all()
        cfg_map = {c.key: c.value for c in cfgs}

        # 2. Positions
        open_real = await PortfolioService.get_open_positions(session, is_paper=False)
        open_paper = await PortfolioService.get_open_positions(session, is_paper=True)

        susp_raw = cfg_map.get("suspended_symbols") or "[]"
        import json as _json

        try:
            susp_data = _json.loads(susp_raw)
            susp_list = [str(s["symbol"]) for s in susp_data if isinstance(s, dict) and s.get("symbol")]
            susp_str = ", ".join(susp_list) if susp_list else "NONE"
        except Exception:
            susp_str = "NONE"

        from rich.table import Table

        tbl = Table(
            title=f"[{PHOSPHOR_AMBER}]AI TRADING AGENT STATUS[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}"
        )
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

        _flag_row("Emergency Kill Switch", cfg_map.get("kill_switch"), is_danger_when_true=True)
        _flag_row("System Paused", cfg_map.get("system_paused"), is_danger_when_true=True)
        _flag_row("Budget Paused", cfg_map.get("budget_pause"), is_danger_when_true=True)
        _flag_row("Auto-Execute Mode", cfg_map.get("auto_execute"), is_danger_when_true=False)
        tbl.add_row("Suspended Symbols", susp_str, stamp_warn("SUSPENDED") if susp_str != "NONE" else stamp_ok("CLEAR"))
        tbl.add_row(
            "Open Real Positions",
            str(len(open_real)),
            stamp_exec(f"{len(open_real)} LOT") if open_real else f"[{MUTED}][ 0 ][/]",
        )
        tbl.add_row(
            "Open Paper Positions",
            str(len(open_paper)),
            stamp_info(f"{len(open_paper)} POS") if open_paper else f"[{MUTED}][ 0 ][/]",
        )

        console.print()
        console.print(tbl)
        console.print()


async def _cmd_pause(args: Any) -> None:
    console = cli_main.get_console()
    await cli_main.init_db()
    async with cli_main.get_session() as session:
        await TradingService.pause_trading(session, reason="CLI pause command", actor="cli_admin")
    try:
        import aiohttp

        settings = cli_main.load_settings()
        port = settings.get("dashboard", {}).get("port", 8000)
        async with aiohttp.ClientSession() as http_sess:
            async with http_sess.post(
                f"http://127.0.0.1:{port}/api/actions/pause",
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as resp:
                if resp.status in (200, 201):
                    console.print(f"{stamp_ok('FORWARD')} Signal forwarded to running Dashboard daemon API.")
    except Exception:
        pass
    console.print(f"{stamp_ok('PAUSE')} System trading paused successfully.")


async def _cmd_resume(args: Any) -> None:
    console = cli_main.get_console()
    if not getattr(args, "yes", False):
        if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            conf = await asyncio.to_thread(
                input, f"{stamp_warn('CONFIRM')} Resume trading operations and clear all pause flags? Type 'RESUME': "
            )
            if conf.strip() != "RESUME":
                console.print(f"{stamp_err('ABORT')} Operation aborted by operator.")
                return
        else:
            console.print(
                f"{stamp_err('FAILED')} Resume command in non-interactive environment requires '-y' / '--yes' flag."
            )
            return

    await cli_main.init_db()
    async with cli_main.get_session() as session:
        await TradingService.resume_trading(session, actor="cli_admin")
    try:
        import aiohttp

        settings = cli_main.load_settings()
        port = settings.get("dashboard", {}).get("port", 8000)
        async with aiohttp.ClientSession() as http_sess:
            async with http_sess.post(
                f"http://127.0.0.1:{port}/api/actions/resume",
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as resp:
                if resp.status in (200, 201):
                    console.print(f"{stamp_ok('FORWARD')} Signal forwarded to running Dashboard daemon API.")
    except Exception:
        pass
    console.print(
        f"{stamp_ok('RESUME')} System trading resumed (all pause, kill-switch, and suspension flags cleared)."
    )


async def _cmd_unsuspend(args: Any) -> None:
    console = cli_main.get_console()
    await cli_main.init_db()
    is_all = getattr(args, "all", False) or not getattr(args, "symbol", None)
    sym = None if is_all else args.symbol.strip().upper()
    cleared: List[str] = []
    ok = False

    async with cli_main.get_session() as session:
        from monika.core.analytics.paper_tracker import PaperTracker

        tracker = PaperTracker()
        if is_all or not sym:
            cleared = await tracker.unsuspend_all(session)
        else:
            ok = await tracker.unsuspend_symbol(session, sym)

    try:
        import aiohttp

        settings = cli_main.load_settings()
        port = settings.get("dashboard", {}).get("port", 8000)
        async with aiohttp.ClientSession() as http_sess:
            async with http_sess.post(
                f"http://127.0.0.1:{port}/api/actions/unsuspend",
                json={"symbol": sym if not is_all else "ALL"},
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as resp:
                if resp.status in (200, 201):
                    console.print(f"{stamp_ok('FORWARD')} Signal forwarded to running Dashboard daemon API.")
    except Exception:
        pass

    if is_all:
        if cleared:
            console.print(
                f"{stamp_ok('UNSUSPEND')} Successfully lifted trading suspension on all instruments: {', '.join(cleared)}"
            )
        else:
            console.print(f"{stamp_info('STATUS')} No instruments currently suspended.")
    else:
        if ok:
            console.print(f"{stamp_ok('UNSUSPEND')} Successfully lifted trading suspension on symbol {sym}.")
        else:
            console.print(f"{stamp_info('STATUS')} Symbol {sym} not found in active suspension list.")


async def _cmd_kill(args: Any) -> None:
    console = cli_main.get_console()
    if not getattr(args, "yes", False):
        if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            conf = await asyncio.to_thread(
                input, f"{stamp_warn('KILL')} CRITICAL ALERT: Trigger EMERGENCY KILL SWITCH? Type 'KILL' to confirm: "
            )
            if conf.strip() != "KILL":
                console.print(f"{stamp_err('ABORT')} Operation aborted by operator.")
                return
        else:
            console.print(
                f"{stamp_err('FAILED')} Kill switch command in non-interactive environment requires '-y' / '--yes' flag."
            )
            return

    await cli_main.init_db()
    async with cli_main.get_session() as session:
        await TradingService.emergency_kill(session, reason="CLI Emergency Kill", actor="cli_admin")
    console.print(f"{stamp_err('EMERGENCY KILL SWITCH')} EMERGENCY KILL SWITCH FLAG SET TO TRUE.")

    # Route kill action through DB flag and Dashboard API safely (no second MT5Client instance)
    api_notified = False
    try:
        import aiohttp

        settings = cli_main.load_settings()
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
        console.print(
            f"{stamp_info('DATABASE')} Kill signal recorded in database. PositionGuardian will safely close all open positions."
        )

    console.print(f"{stamp_err('HALTED')} All trading operations permanently halted.")


async def _cmd_stop(args: Any) -> None:
    """Stop running Monika daemon gracefully."""
    console = cli_main.get_console()
    force = getattr(args, "force", False)

    pid = cli_main.get_daemon_pid()
    if not pid:
        console.print(f"{stamp_info('STOP')} No active Monika daemon found running.")
        return

    import psutil

    console.print(f"{stamp_info('STOP')} Stopping Monika daemon (PID: {pid})...")

    # Mark clean shutdown flag so auto-restart loop scripts won't loop
    try:
        from monika.application.agent.task_registry import mark_clean_shutdown

        mark_clean_shutdown()
    except Exception:
        pass

    # Try API shutdown first if API is up
    if not force:
        try:
            url = getattr(args, "url", cli_main.DEFAULT_API_URL).rstrip("/")
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{url}/api/actions/shutdown"):
                    pass
        except Exception:
            pass

    stopped = False
    try:
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if not force:
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                    stopped = True
                except psutil.TimeoutExpired:
                    pass
            if not stopped and psutil.pid_exists(pid):
                proc.kill()
                try:
                    proc.wait(timeout=3.0)
                    stopped = True
                except Exception:
                    pass
    except psutil.NoSuchProcess:
        stopped = True
    except Exception as e:
        console.print(f"{stamp_warn('STOP')} Catatan terminasi: {e}")

    pid_file = cli_main.get_pid_file_path()
    if pid_file and os.path.exists(pid_file):
        try:
            os.remove(pid_file)
        except Exception:
            pass

    console.print(f"{stamp_ok('STOP')} Monika daemon (PID {pid}) stopped successfully.")


async def _cmd_positions(args: Any) -> None:
    console = cli_main.get_console()
    await cli_main.init_db()
    async with cli_main.get_session() as session:
        open_real = await PortfolioService.get_open_positions(session, is_paper=False)
        open_paper = await PortfolioService.get_open_positions(session, is_paper=True)

        from rich.table import Table

        console.print()
        if open_real:
            tbl_real = Table(
                title=f"[{PHOSPHOR_AMBER}]OPEN REAL POSITIONS[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}"
            )
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
                    str(p.id or "-"),
                    str(getattr(p, "mt5_ticket", "N/A")),
                    str(p.symbol),
                    side_styled,
                    f"{float(p.volume):.2f}",
                    str(p.entry_price),
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
                lots_val = p.volume
                tbl_paper.add_row(
                    str(p.id or "-"),
                    str(p.symbol),
                    side_styled,
                    f"{float(lots_val):.2f}" if isinstance(lots_val, (int, float)) else str(lots_val),
                    str(p.entry_price),
                    str(p.sl or "-"),
                    str(p.tp or "-"),
                )
            console.print(tbl_paper)
        else:
            console.print(f"[{MUTED}]--- OPEN PAPER POSITIONS: No open paper positions. ---[/]")
        console.print()


async def _acli_run(args: Any) -> None:
    """Asynchronous CLI execution pipeline."""
    if not cli_main.acquire_single_instance_lock():
        logger.error("Another TradingAgent instance is currently active. Aborting.")
        sys.exit(1)

    # 1. Load config
    if getattr(args, "config", None):
        if not os.path.exists(args.config):
            logger.critical(f"Config file not found at: {args.config}")
            raise FileNotFoundError(f"Custom configuration file not found: {args.config}")
        settings = cli_main.load_all_config(settings_path=args.config)
    else:
        settings = cli_main.load_all_config()

    # 2. Configure Trading Mode & Tier
    mode = getattr(args, "mode", "paper")
    is_dry_run = mode == "paper"

    from monika.core.config.settings import get_installation_tier

    active_tier = get_installation_tier(settings)
    if active_tier == "trial" and mode != "live":
        from pathlib import Path

        data_dir = Path.cwd() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = (data_dir / "monika.db").resolve()
        os.environ["MONIKA_TIER"] = "trial"
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        os.environ["PAPER_TRADING_MODE"] = "true"

    if mode == "live":
        if not getattr(args, "confirm_live", False):
            if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                confirmation = await asyncio.to_thread(
                    input,
                    "CRITICAL WARNING: Live capital execution deployment requested. Type 'CONFIRM_LIVE' to proceed: ",
                )
                if confirmation.strip() != "CONFIRM_LIVE":
                    logger.warning("Live capital execution cancelled by operator. Aborting.")
                    sys.exit(0)
            else:
                logger.critical(
                    "Live capital execution requires explicit operator confirmation or '--confirm-live' flag. Aborting."
                )
                sys.exit(1)
        settings.setdefault("trading", {})["auto_execute"] = True
        logger.warning("[WARNING] Starting in LIVE execution mode. Real capital will be traded via MT5.")
    else:
        settings.setdefault("paper_trading", {})["enabled"] = True
        settings.setdefault("trading", {}).setdefault("paper_trading", {})["enabled"] = True
        logger.info(f"Starting in PAPER trading mode (simulation) [Tier: {active_tier.upper()}].")

    # Configure Gemini Rate Limiter limits from settings
    from monika.infrastructure.api.gemini_rate_limiter import configure_from_settings

    configure_from_settings(settings)

    # 3. Init DB & Health Checks
    logger.info("Initializing database...")
    await cli_main.init_db()

    logger.info("Running startup health checks...")
    checks_ok = await cli_main.run_startup_checks(settings)
    if not checks_ok:
        logger.critical("Startup checks failed. Aborting.")
        await cli_main.close_db()
        sys.exit(1)

    # 4. Instantiate & Start Agent
    agent = cli_main.TradingAgent(settings=settings, dry_run=is_dry_run)
    try:
        await agent.start()
    finally:
        await cli_main.close_db()


async def _cmd_tui(args: Any) -> None:
    """Launch rich Textual terminal dashboard."""
    from monika.interfaces.cli.tui import run_tui

    run_tui(
        api_url=getattr(args, "url", cli_main.DEFAULT_API_URL),
        api_key=getattr(args, "token", None),
        refresh_interval=getattr(args, "refresh", 5),
    )


async def _cmd_chat(args: Any) -> None:
    """Launch interactive REPL chat with agent."""
    from monika.interfaces.cli.tui_chat import run_cli_chat

    await run_cli_chat(
        api_url=getattr(args, "url", cli_main.DEFAULT_API_URL),
        api_key=getattr(args, "token", None),
        session_id=getattr(args, "session_id", None),
        offline=getattr(args, "offline", False),
        model=getattr(args, "model", "auto"),
    )
