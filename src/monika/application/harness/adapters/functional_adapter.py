"""
Backward-compatibility facade for functional_adapter.
Canonical location: monika.application.plugins.engine.adapters.functional_adapter
"""

import sys
import monika.application.plugins.engine.adapters.functional_adapter as _canonical

from monika.application.plugins.engine.adapters.functional_adapter import (
    FunctionalPluginBridge,
    install_compatibility_shims,
    script_constants,
    tools,
)

__all__ = [
    "FunctionalPluginBridge",
    "install_compatibility_shims",
    "script_constants",
    "tools",
]

sys.modules[__name__] = _canonical
