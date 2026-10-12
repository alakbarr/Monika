# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.sandboxes
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.sandboxes"""

import sys
import monika.infrastructure.sandboxes as _canonical

from monika.infrastructure.sandboxes import (
    BaseTerminalBackend,
    DockerTerminalBackend,
    LocalTerminalBackend,
)

__all__ = [
    "BaseTerminalBackend",
    "DockerTerminalBackend",
    "LocalTerminalBackend",
]
