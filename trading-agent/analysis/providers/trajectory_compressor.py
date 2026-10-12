# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.trajectory_compressor
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.trajectory_compressor"""

import sys
import monika.infrastructure.providers.trajectory_compressor as _canonical

from monika.infrastructure.providers.trajectory_compressor import (
    TrajectoryCompressor,
    _THINK_TAG_REGEX,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TrajectoryCompressor",
    "_THINK_TAG_REGEX",
    "logger",
]
