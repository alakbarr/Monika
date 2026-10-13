# ==============================================================================
# File: interfaces/cli/tui_app/mixins/__init__.py
# Description: Mixins package for Monika TUI Terminal Dashboard
# ==============================================================================

from monika.interfaces.cli.tui_app.mixins.actions import ActionsMixin
from monika.interfaces.cli.tui_app.mixins.data_sync import DataSyncMixin
from monika.interfaces.cli.tui_app.mixins.navigation import NavigationMixin
from monika.interfaces.cli.tui_app.mixins.plugins_benchmark import PluginsBenchmarkMixin
from monika.interfaces.cli.tui_app.mixins.websocket import WebSocketMixin

__all__ = [
    "ActionsMixin",
    "DataSyncMixin",
    "NavigationMixin",
    "PluginsBenchmarkMixin",
    "WebSocketMixin",
]
