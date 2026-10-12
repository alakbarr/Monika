# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.sandboxes.docker_backend
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.sandboxes.docker_backend"""

import sys
import monika.infrastructure.sandboxes.docker_backend as _canonical

from monika.infrastructure.sandboxes.docker_backend import (
    DockerTerminalBackend,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DockerTerminalBackend",
    "logger",
]
