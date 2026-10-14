# ==============================================================================
# File: interfaces/cli/context.py
# ==============================================================================

"""
CLI Runtime Context and Daemon Process Management.
Provides environment setup, daemon process lifecycle, and shared infrastructure helpers
without circular dependencies on interfaces.cli.main.
"""

import logging
import os
import subprocess
import sys
import time
from typing import Any, Optional

_repo_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
_parent_dir = _repo_root

from monika.application import main as _root_main
from monika.core.config.settings import load_all_config, load_settings
from monika.infrastructure.database.db import close_db, get_session, init_db
from monika.interfaces.cli.theme import (
    MUTED,
    get_console,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

TradingAgent: Any = getattr(_root_main, "TradingAgent", None)
acquire_single_instance_lock: Any = getattr(_root_main, "acquire_single_instance_lock", None)
run_startup_checks: Any = getattr(_root_main, "run_startup_checks", None)

logger = logging.getLogger("TradingAgent.CLI.Context")

DEFAULT_API_URL = (
    os.environ.get("MONIKA_API_URL")
    or os.environ.get("TRADEAGENT_API_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8000"
)


def get_pid_file_path() -> str:
    """Resolve active or expected PID file path for the trading daemon."""
    pid_file = getattr(_root_main, "PID_FILE", None)
    if pid_file and os.path.exists(pid_file):
        return pid_file
    for cand in [
        os.path.join(_parent_dir, "logs", "trading_agent.pid"),
        os.path.join(os.getcwd(), "logs", "trading_agent.pid"),
        "logs/trading_agent.pid",
    ]:
        if os.path.exists(cand):
            return cand
    return os.path.join(_parent_dir, "logs", "trading_agent.pid")


def get_daemon_pid() -> Optional[int]:
    """Retrieve daemon PID if process is actively running."""
    import psutil

    pid_file = get_pid_file_path()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    pid = int(content)
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        if proc.is_running() and "python" in proc.name().lower():
                            return pid
        except Exception:
            pass
    return None


def is_daemon_running(api_url: Optional[str] = None) -> bool:
    """Check if Monika trading daemon is actively running."""
    main_mod = sys.modules.get("monika.interfaces.cli.main")
    pid_fn = getattr(main_mod, "get_daemon_pid", None) if main_mod is not None else None
    if pid_fn is None:
        pid_fn = get_daemon_pid
    if pid_fn() is not None:
        return True

    url = (api_url or DEFAULT_API_URL).rstrip("/")
    import urllib.request

    try:
        req = urllib.request.Request(f"{url}/api/overview", headers={"User-Agent": "Monika-CLI"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    return False


def spawn_daemon_background(mode: str = "paper", config_path: Optional[str] = None) -> Optional[int]:
    """Spawn the Monika trading daemon as a persistent background process."""
    cmd = [sys.executable, "-m", "monika.interfaces.cli.main", "run", "--mode", mode]
    if mode == "live":
        cmd.append("--confirm-live")
    if config_path:
        cmd.extend(["--config", config_path])

    log_dir = os.path.join(_parent_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    daemon_log_path = os.path.join(log_dir, "daemon.log")

    log_file = open(daemon_log_path, "a", encoding="utf-8")

    creationflags = 0
    start_new_session = False
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        start_new_session = True

    env = os.environ.copy()
    if _parent_dir not in env.get("PYTHONPATH", ""):
        env["PYTHONPATH"] = _parent_dir + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=_parent_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=start_new_session,
            close_fds=True,
            env=env,
        )
        return proc.pid
    finally:
        log_file.close()


def ensure_daemon_running(args: Any, console: Any = None) -> bool:
    """Ensure that Monika trading daemon is active before executing client commands."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True

    if getattr(args, "no_daemon", False) or getattr(args, "standalone", False) or getattr(args, "offline", False):
        return True

    api_url = getattr(args, "url", DEFAULT_API_URL)
    if is_daemon_running(api_url):
        return True

    try:
        from monika.infrastructure.infra.env_file_manager import EnvFileManager

        if not EnvFileManager.is_configured():
            return False
    except Exception:
        pass

    if console is None:
        console = get_console()

    mode = getattr(args, "mode", "paper")
    cfg_path = getattr(args, "config", None)

    console.print(f"{stamp_info('DAEMON')} Monika trading daemon is not running.")
    console.print(f"[{MUTED}]Starting Monika daemon in background (mode: {mode.upper()})...[/]")

    try:
        pid = spawn_daemon_background(mode=mode, config_path=cfg_path)
    except Exception as e:
        console.print(f"{stamp_err('DAEMON')} Failed to start background daemon: {e}")
        return False

    console.print(f"[{MUTED}]Waiting for daemon to initialize (PID: {pid})...[/]")

    start_t = time.time()
    ready = False
    while time.time() - start_t < 10.0:
        time.sleep(1.0)
        if is_daemon_running(api_url):
            ready = True
            break

    if ready:
        console.print(f"{stamp_ok('DAEMON')} Monika daemon aktif & siap (PID: {pid}).\n")
        return True
    else:
        console.print(
            f"{stamp_warn('DAEMON')} Daemon telah di-spawn (PID {pid}), log: logs/daemon.log. Melanjutkan perintah...\n"
        )
        return True


class CliMainProxy:
    """Transparent proxy for CLI command modules to access runtime context.

    If an attribute has been monkeypatched or defined on monika.interfaces.cli.main,
    that attribute is returned; otherwise falls back to context.py.
    This eliminates circular imports between interfaces.cli.commands and interfaces.cli.main
    while preserving test patch compatibility.
    """

    def __getattr__(self, name: str) -> Any:
        main_mod = sys.modules.get("monika.interfaces.cli.main")
        if main_mod is not None:
            main_dict = getattr(main_mod, "__dict__", {})
            if name in main_dict:
                return main_dict[name]
        ctx_mod = sys.modules.get("monika.interfaces.cli.context")
        if ctx_mod is not None:
            ctx_dict = getattr(ctx_mod, "__dict__", {})
            if name in ctx_dict:
                return ctx_dict[name]
        import monika.interfaces.cli.context as ctx

        if hasattr(ctx, name):
            return getattr(ctx, name)
        raise AttributeError(f"module 'monika.interfaces.cli.context' has no attribute '{name}'")


cli_main: Any = CliMainProxy()
