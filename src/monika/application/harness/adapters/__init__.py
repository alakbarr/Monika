"""
Backward-compatibility facade for harness adapters.
Canonical location: monika.application.plugins.engine.adapters
"""

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
