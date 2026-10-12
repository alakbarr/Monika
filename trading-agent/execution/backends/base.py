# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.sandboxes.base
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.sandboxes.base"""

import sys
import monika.infrastructure.sandboxes.base as _canonical

from monika.infrastructure.sandboxes.base import (
    BaseTerminalBackend,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BaseTerminalBackend",
]
