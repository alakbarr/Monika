# ==============================================================================
# File: indicators/smc_advanced.py
# Description: Backward-compatibility shim for monika.domain.indicators.smc_advanced
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.smc_advanced
"""

import sys
import monika.domain.indicators.smc_advanced as _canonical

from monika.domain.indicators.smc_advanced import (
    BreakerBlockResult,
    EqualPoolResult,
    InducementResult,
    InvertedFVGResult,
    JudasSwingResult,
    compute_ob_fvg_confluence,
    detect_breaker_blocks,
    detect_equal_highs_lows,
    detect_inducement,
    detect_inverted_fvg,
    detect_judas_swing,
    detect_smt_divergence,
    find_wick_to_wick_fvg,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "BreakerBlockResult",
    "EqualPoolResult",
    "InducementResult",
    "InvertedFVGResult",
    "JudasSwingResult",
    "compute_ob_fvg_confluence",
    "detect_breaker_blocks",
    "detect_equal_highs_lows",
    "detect_inducement",
    "detect_inverted_fvg",
    "detect_judas_swing",
    "detect_smt_divergence",
    "find_wick_to_wick_fvg",
    "logger",
]
