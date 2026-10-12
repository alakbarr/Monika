# ==============================================================================
# File: indicators/alpha_zoo/vector_factor_engine.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.vector_factor_engine
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.vector_factor_engine
"""

import sys
import monika.domain.indicators.alpha_zoo.vector_factor_engine as _canonical

from monika.domain.indicators.alpha_zoo.vector_factor_engine import (
    AlphaCategory,
    FactorRegistry,
    FactorSignal,
    VectorFactorEngine,
    VectorFactorResult,
    _GLOBAL_VECTOR_FACTOR_ENGINE,
    annotations,
    get_vector_factor_engine,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AlphaCategory",
    "FactorRegistry",
    "FactorSignal",
    "VectorFactorEngine",
    "VectorFactorResult",
    "_GLOBAL_VECTOR_FACTOR_ENGINE",
    "annotations",
    "get_vector_factor_engine",
    "logger",
]
