# ==============================================================================
# File: indicators/alpha_zoo/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo
"""

import sys
import monika.domain.indicators.alpha_zoo as _canonical

from monika.domain.indicators.alpha_zoo import (
    AlphaCategory,
    AlphaDirection,
    AlphaMeta,
    FactorRegistry,
    FactorSignal,
    RegistryError,
    VectorFactorEngine,
    VectorFactorResult,
    load_alpha_meta_from_py,
)

# Auto-register standard formulations
import indicators.alpha_zoo.qlib158  # noqa: F401
import indicators.alpha_zoo.alpha101  # noqa: F401
import indicators.alpha_zoo.academic_factors  # noqa: F401
import indicators.alpha_zoo.microstructure_factors  # noqa: F401
import indicators.alpha_zoo.fundamental_factors  # noqa: F401

__all__ = [
    "AlphaCategory",
    "AlphaDirection",
    "AlphaMeta",
    "FactorRegistry",
    "FactorSignal",
    "RegistryError",
    "VectorFactorEngine",
    "VectorFactorResult",
    "load_alpha_meta_from_py",
]
