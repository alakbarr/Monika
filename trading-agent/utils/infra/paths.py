"""
Compatibility facade shim for legacy paths.py.
Re-exports from canonical monika.infrastructure.infra.paths.
"""

from __future__ import annotations

import monika.infrastructure.infra.paths as _canonical

from monika.infrastructure.infra.paths import (
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    REPO_ROOT,
    SUBAGENT_LOGS_DIR,
    TRADING_AGENT_DIR,
    get_data_dir,
    get_logs_dir,
    get_subagent_logs_dir,
    resolve_data_path,
)

__all__ = ['CONFIG_DIR', 'DATA_DIR', 'LOGS_DIR', 'REPO_ROOT', 'SUBAGENT_LOGS_DIR', 'TRADING_AGENT_DIR', 'get_data_dir', 'get_logs_dir', 'get_subagent_logs_dir', 'resolve_data_path']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
