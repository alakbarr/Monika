# ==============================================================================
# File: harness/adapters/__init__.py
# ==============================================================================

"""
Plugin adapters and bridges for standalone functional script plugins.
"""

from harness.adapters.functional_adapter import (
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
