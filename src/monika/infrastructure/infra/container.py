"""
Compatibility facade for canonical ServiceContainer.
Re-exports all symbols from monika.core.container.
"""

import sys
import monika.core.container as _canonical

from monika.core.container import (
    Context,
    ServiceContainer,
    get_container,
)

__all__ = [
    "Context",
    "ServiceContainer",
    "get_container",
]

sys.modules[__name__] = _canonical
