# ==============================================================================
# File: interfaces/cli/tui.py
# Description: Rich Terminal Dashboard (TUI) for Monika AI Trading Agent (Facade)
# ==============================================================================

"""
Rich Terminal Dashboard (TUI) for Monika AI Trading Agent built using Textual.
Backward-compatible facade delegating to modular `monika.interfaces.cli.tui_app`.
"""

import sys
import types
from typing import Any, List, Optional, Tuple

import monika.interfaces.cli.tui_app as _tui_app_pkg
import monika.interfaces.cli.tui_app.constants as _constants_mod
import monika.interfaces.cli.tui_app.dashboard as _dashboard_mod
import monika.interfaces.cli.tui_app.entrypoints as _entrypoints_mod
import monika.interfaces.cli.tui_app.widgets as _widgets_mod
from monika.interfaces.cli.tui_app import (
    COMMAND_SUGGESTIONS,
    DEFAULT_API_URL,
    DETERMINISTIC_RISK_CHECKS,
    KillConfirmModalScreen,
    LiveTickerBanner,
    StatusBar,
    TradingAgentApp,
    TradingDashboard,
    run_tui,
)

__all__: List[str] = [
    "COMMAND_SUGGESTIONS",
    "DEFAULT_API_URL",
    "DETERMINISTIC_RISK_CHECKS",
    "KillConfirmModalScreen",
    "LiveTickerBanner",
    "StatusBar",
    "TradingAgentApp",
    "TradingDashboard",
    "run_tui",
]


class _TuiFacadeModule(types.ModuleType):
    """Module proxy forwarding attribute mutations to submodules for transparent monkeypatching."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for submodule in (
            _tui_app_pkg,
            _constants_mod,
            _widgets_mod,
            _dashboard_mod,
            _entrypoints_mod,
        ):
            if hasattr(submodule, name):
                setattr(submodule, name, value)


_current_mod = sys.modules[__name__]
_proxy_mod = _TuiFacadeModule(__name__, __doc__)
_proxy_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _proxy_mod

if __name__ == "__main__":
    run_tui()
