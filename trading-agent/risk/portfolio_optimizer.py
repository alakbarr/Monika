# ==============================================================================
# File: risk/portfolio_optimizer.py
# Description: Backward-compatibility shim for monika.domain.risk.portfolio_optimizer
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.portfolio_optimizer
"""

import sys
import monika.domain.risk.portfolio_optimizer as _canonical

from monika.domain.risk.portfolio_optimizer import (
    DEFAULT_GROUP_CAPS,
    DEFAULT_GROUP_MAP,
    OptimizationResult,
    PortfolioOptimizer,
    annotations,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_GROUP_CAPS",
    "DEFAULT_GROUP_MAP",
    "OptimizationResult",
    "PortfolioOptimizer",
    "annotations",
    "logger",
]
