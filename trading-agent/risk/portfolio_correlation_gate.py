# ==============================================================================
# File: risk/portfolio_correlation_gate.py
# Description: Backward-compatibility shim for monika.domain.risk.portfolio_correlation_gate
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.portfolio_correlation_gate
"""

import sys
import monika.domain.risk.portfolio_correlation_gate as _canonical

from monika.domain.risk.portfolio_correlation_gate import (
    GROUP_POSITION_LIMITS,
    _get_usd_directional_delta,
    compute_portfolio_correlation_matrix,
    filter_correlated_proposals,
    get_rolling_correlation,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "GROUP_POSITION_LIMITS",
    "_get_usd_directional_delta",
    "compute_portfolio_correlation_matrix",
    "filter_correlated_proposals",
    "get_rolling_correlation",
    "logger",
]
