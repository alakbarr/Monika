# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.ml.timesfm_engine
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.ml.timesfm_engine"""

import sys
import monika.infrastructure.ml.timesfm_engine as _canonical

from monika.infrastructure.ml.timesfm_engine import (
    TimesFMEngine,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TimesFMEngine",
    "logger",
]
