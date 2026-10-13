"""
Backward-compatibility facade for PluginEngine.
Canonical location: monika.application.plugins.engine.engine
"""

import sys
import monika.application.plugins.engine.engine as _canonical

from monika.application.plugins.engine.engine import (
    CircularDependencyError,
    FunctionalPluginAdapter,
    LIFECYCLE_TIMEOUT_CONFIG_RELOAD,
    LIFECYCLE_TIMEOUT_PREFLIGHT,
    LIFECYCLE_TIMEOUT_RECOVERY,
    LIFECYCLE_TIMEOUT_REGISTER,
    LIFECYCLE_TIMEOUT_START,
    LIFECYCLE_TIMEOUT_STOP,
    MissingDependencyError,
    PluginDependencyError,
    PluginEngine,
    get_plugin_engine,
    topological_sort_plugins,
)

__all__ = [
    "PluginEngine",
    "FunctionalPluginAdapter",
    "get_plugin_engine",
    "topological_sort_plugins",
    "PluginDependencyError",
    "MissingDependencyError",
    "CircularDependencyError",
    "LIFECYCLE_TIMEOUT_REGISTER",
    "LIFECYCLE_TIMEOUT_PREFLIGHT",
    "LIFECYCLE_TIMEOUT_RECOVERY",
    "LIFECYCLE_TIMEOUT_START",
    "LIFECYCLE_TIMEOUT_STOP",
    "LIFECYCLE_TIMEOUT_CONFIG_RELOAD",
]

# Alias in sys.modules so dynamic monkeypatching targets canonical module directly
sys.modules[__name__] = _canonical
