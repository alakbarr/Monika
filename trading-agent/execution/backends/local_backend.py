# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.sandboxes.local_backend
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.sandboxes.local_backend"""

import sys
import monika.infrastructure.sandboxes.local_backend as _canonical

from monika.infrastructure.sandboxes.local_backend import (
    LocalTerminalBackend,
    _IS_WINDOWS,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "LocalTerminalBackend",
    "_IS_WINDOWS",
    "logger",
]
