"""
Compatibility facade shim for legacy main.py.
Re-exports from canonical monika.interfaces.cli.main.
"""

from __future__ import annotations

import monika.interfaces.cli.main as _canonical

from monika.interfaces.cli.main import (
    DEFAULT_API_URL,
    MonikaArgumentParser,
    arm_exit_watchdog,
    ensure_daemon_running,
    get_daemon_pid,
    get_pid_file_path,
    is_daemon_running,
    logger,
    parse_args,
    run,
    spawn_daemon_background,
)

__all__ = ['DEFAULT_API_URL', 'MonikaArgumentParser', 'arm_exit_watchdog', 'ensure_daemon_running', 'get_daemon_pid', 'get_pid_file_path', 'is_daemon_running', 'logger', 'parse_args', 'run', 'spawn_daemon_background']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
