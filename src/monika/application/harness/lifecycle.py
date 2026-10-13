"""
Backward-compatibility facade for plugin lifecycle.
Canonical location: monika.application.plugins.engine.lifecycle
"""

import sys
import monika.application.plugins.engine.lifecycle as _canonical

from monika.application.plugins.engine.lifecycle import (
    ComponentDrainingError,
    ReplacementCoordinator,
    ReplacementLease,
    ReplacementTimeoutError,
    get_plugin_storage_dir,
    get_replacement_coordinator,
    safe_dispatch_hook,
)

__all__ = [
    "ReplacementTimeoutError",
    "ComponentDrainingError",
    "ReplacementLease",
    "ReplacementCoordinator",
    "safe_dispatch_hook",
    "get_plugin_storage_dir",
    "get_replacement_coordinator",
]

sys.modules[__name__] = _canonical
