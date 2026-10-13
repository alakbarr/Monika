# ==============================================================================
# File: interfaces/cli/main.py
# ==============================================================================

"""
Monika Algorithmic Trading Platform - Unified CLI Interface & Dispatcher.
Coordinates subcommands, interactive TUI, background daemon, and diagnostics.
"""

import argparse
import atexit
import logging
import os
import sys
import threading
import time
from typing import Any, Optional

# Ensure repo root and src directories are on path
_repo_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
for _p in (_repo_root, os.path.join(_repo_root, "src")):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

_parent_dir = _repo_root

from monika.application.bootstrap import install_bootstrap_hardening

install_bootstrap_hardening()


def _reset_terminal_modes() -> None:
    """Restore terminal mouse, bracketed paste, and cursor visibility on exit."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\x1b[?1000l\x1b[?2004l\x1b[?25h")
            sys.stdout.flush()
    except Exception:
        pass


atexit.register(_reset_terminal_modes)


def arm_exit_watchdog(timeout_s: float = 15.0) -> None:
    """Escort thread ensuring clean process termination if async loops hang during shutdown."""

    def _force_exit():
        time.sleep(timeout_s)
        _reset_terminal_modes()
        os._exit(0)

    t = threading.Thread(target=_force_exit, daemon=True, name="exit-watchdog")
    t.start()


from monika.interfaces.cli.platform_compat import apply_platform_fixes

apply_platform_fixes()

from monika.application import main as _root_main
from monika.core.config.settings import load_all_config, load_settings
from monika.infrastructure.database.db import close_db, get_session, init_db
from monika.infrastructure.database.models import PaperTradeRecord, Position, RiskState, SystemConfig
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    LEDGER_BOX,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
    get_console,
    stamp_err,
    stamp_exec,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

TradingAgent: Any = getattr(_root_main, "TradingAgent", None)
acquire_single_instance_lock: Any = getattr(_root_main, "acquire_single_instance_lock", None)
run_startup_checks: Any = getattr(_root_main, "run_startup_checks", None)

logger = logging.getLogger("TradingAgent.CLI")

from monika.interfaces.cli.context import (
    DEFAULT_API_URL,
    ensure_daemon_running,
    get_daemon_pid,
    get_pid_file_path,
    is_daemon_running,
    spawn_daemon_background,
)


# Re-exports of modular subcommand handlers and argument parser
from monika.interfaces.cli.commands import (
    MonikaArgumentParser,
    _acli_run,
    _cmd_analyze,
    _cmd_ask,
    _cmd_backtest,
    _cmd_backup,
    _cmd_benchmark,
    _cmd_benchmark_history,
    _cmd_benchmark_leaderboard,
    _cmd_benchmark_models,
    _cmd_benchmark_run,
    _cmd_benchmark_tasks,
    _cmd_chat,
    _cmd_config,
    _cmd_config_edit,
    _cmd_config_get,
    _cmd_config_set,
    _cmd_config_show,
    _cmd_config_unset,
    _cmd_doctor,
    _cmd_kill,
    _cmd_logs,
    _cmd_onboarding,
    _cmd_pause,
    _cmd_positions,
    _cmd_profile,
    _cmd_resume,
    _cmd_sessions,
    _cmd_setup,
    _cmd_status,
    _cmd_stop,
    _cmd_stress_test,
    _cmd_tui,
    _cmd_unsuspend,
    parse_args,
)


async def _dispatch_cli(args: Any) -> None:
    DAEMON_CLIENT_COMMANDS = {"status", "positions", "chat", "ask", "analyze"}
    if args.command in DAEMON_CLIENT_COMMANDS and not getattr(args, "no_daemon", False):
        ensure_daemon_running(args)

    try:
        if args.command == "status":
            await _cmd_status(args)
        elif args.command == "ask":
            await _cmd_ask(args)
        elif args.command == "analyze":
            await _cmd_analyze(args)
        elif args.command == "backtest":
            await _cmd_backtest(args)
        elif args.command == "pause":
            await _cmd_pause(args)
        elif args.command == "resume":
            await _cmd_resume(args)
        elif args.command == "unsuspend":
            await _cmd_unsuspend(args)
        elif args.command == "kill":
            await _cmd_kill(args)
        elif args.command == "stop":
            await _cmd_stop(args)
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
            from monika.application.analysis.mcp.server import MonikaMcpServer
            from monika.core.config.settings import load_settings

            cfg = load_settings(getattr(args, "config", None))
            server = MonikaMcpServer(settings=cfg)
            await server.run_stdio()
        elif args.command == "plugin":
            from monika.interfaces.cli.plugins import handle_plugin_command

            handle_plugin_command(args)
        elif args.command == "benchmark":
            await _cmd_benchmark(args)
        elif args.command in ("stress-test", "stresstest"):
            await _cmd_stress_test(args)
        elif args.command == "backup":
            await _cmd_backup(args)
        elif args.command in ("daemon", "simulation", "trading", "mcp", "runcard", "upgrade"):
            from monika.interfaces.cli.subcommands import AVAILABLE_SUBCOMMANDS

            for sc in AVAILABLE_SUBCOMMANDS:
                if sc.name == args.command:
                    code = await sc.execute(args)
                    if code is not None and isinstance(code, int) and code != 0:
                        sys.exit(code)
                    break
        else:
            # First-run interceptor for daemon execution
            from monika.infrastructure.infra.env_file_manager import EnvFileManager

            if not EnvFileManager.is_configured():
                if sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                    from rich.prompt import Confirm

                    from monika.interfaces.cli.theme import get_console, stamp_warn

                    console = get_console()
                    console.print(
                        f"\n{stamp_warn('NOT CONFIGURED')} Monika is not configured (minimum credentials: MT5, DB, or LLM not set)."
                    )
                    if Confirm.ask("Run Interactive Setup Wizard now?", default=True):
                        await _cmd_setup(args)
                        if not EnvFileManager.is_configured():
                            console.print(f"{stamp_warn('ABORT')} Configuration incomplete. Exiting process.\n")
                            return
                    else:
                        console.print("Run `python -m monika.interfaces.cli.main setup` to configure credentials.\n")
                        return
                else:
                    logger.critical(
                        "Monika is not configured (missing MT5_ACCOUNT, DATABASE_URL, or LLM keys). Run 'python -m monika.interfaces.cli.main setup' first."
                    )
                    sys.exit(1)

            print(f"Starting Monika (MT5 Trading Agent) in {getattr(args, 'mode', 'paper').upper()} mode...")
            await _acli_run(args)
    finally:
        try:
            await close_db()
        except Exception:
            pass


def run() -> None:
    args = parse_args()
    from monika.core.telemetry.activity_logger import setup_logging

    setup_logging(level=logging.INFO)

    DAEMON_CLIENT_COMMANDS = {"tui", "chat", "status", "positions", "ask", "analyze"}
    if args.command in DAEMON_CLIENT_COMMANDS and not getattr(args, "no_daemon", False):
        ensure_daemon_running(args)

    if args.command == "tui":
        from monika.interfaces.cli.tui import run_tui

        run_tui(
            api_url=getattr(args, "url", DEFAULT_API_URL),
            api_key=getattr(args, "token", None),
            refresh_interval=getattr(args, "refresh", 5),
            theme_name=getattr(args, "theme", None),
        )
        return

    from monika.infrastructure.infra.event_loop import run_async

    try:
        run_async(_dispatch_cli(args))
    except KeyboardInterrupt:
        logger.info("CLI execution terminated by user.")
    except Exception as e:
        logger.critical(f"CLI encountered fatal exception: {e}", exc_info=True)
        sys.exit(1)


main = run


if __name__ == "__main__":
    run()
