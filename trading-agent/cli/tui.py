"""
Compatibility facade shim for legacy tui.py.
Re-exports from canonical monika.interfaces.cli.tui.
"""

from __future__ import annotations

import monika.interfaces.cli.tui as _canonical

from monika.interfaces.cli.tui import (
    COMMAND_SUGGESTIONS,
    DEFAULT_API_URL,
    DETERMINISTIC_RISK_CHECKS,
    KillConfirmModalScreen,
    LiveTickerBanner,
    StatusBar,
    TradingDashboard,
    logger,
    run_tui,
)

__all__ = ['COMMAND_SUGGESTIONS', 'DEFAULT_API_URL', 'DETERMINISTIC_RISK_CHECKS', 'KillConfirmModalScreen', 'LiveTickerBanner', 'StatusBar', 'TradingDashboard', 'logger', 'run_tui']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
