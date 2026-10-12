"""
Compatibility facade shim for legacy backtest.py.
Re-exports from canonical monika.interfaces.dashboard.routes.backtest.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.backtest as _canonical

from monika.interfaces.dashboard.routes.backtest import (
    BacktestRunRequest,
    backtest_router,
    get_backtest_run_details,
    list_backtest_runs,
    logger,
    trigger_backtest_run,
)

__all__ = ['BacktestRunRequest', 'backtest_router', 'get_backtest_run_details', 'list_backtest_runs', 'logger', 'trigger_backtest_run']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
