# ==============================================================================
# File: risk/correlation_matrix.py
# Description: Backward-compatibility shim for monika.domain.risk.correlation_matrix
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.correlation_matrix
"""

import sys
import monika.domain.risk.correlation_matrix as _canonical

from monika.domain.risk.correlation_matrix import (
    DynamicCorrelationMatrix,
    compute_portfolio_correlation_matrix,
    filter_correlated_proposals,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DynamicCorrelationMatrix",
    "compute_portfolio_correlation_matrix",
    "filter_correlated_proposals",
    "logger",
]
