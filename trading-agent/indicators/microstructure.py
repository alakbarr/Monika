# ==============================================================================
# File: indicators/microstructure.py
# Description: Backward-compatibility shim for monika.domain.indicators.microstructure
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.microstructure
"""

import sys
import monika.domain.indicators.microstructure as _canonical

from monika.domain.indicators.microstructure import (
    AMIHUD_SYMBOLS,
    KYLE_SYMBOLS,
    MT5_CONTRACT_SIZES,
    VPIN_SYMBOLS,
    annotations,
    calculate_amihud_illiquidity_mt5,
    calculate_kyles_lambda_ols,
    calculate_roll_effective_spread,
    calculate_vpin_fractional,
    compute_amihud_illiquidity,
    compute_kyle_lambda,
    compute_roll_effective_spread,
    compute_vpin,
    get_microstructure_metrics,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AMIHUD_SYMBOLS",
    "KYLE_SYMBOLS",
    "MT5_CONTRACT_SIZES",
    "VPIN_SYMBOLS",
    "annotations",
    "calculate_amihud_illiquidity_mt5",
    "calculate_kyles_lambda_ols",
    "calculate_roll_effective_spread",
    "calculate_vpin_fractional",
    "compute_amihud_illiquidity",
    "compute_kyle_lambda",
    "compute_roll_effective_spread",
    "compute_vpin",
    "get_microstructure_metrics",
    "logger",
]
