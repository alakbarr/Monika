# ==============================================================================
# File: indicators/alpha_zoo/factors/microsoft_qlib_158/percentile_price_rank_5.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.percentile_price_rank_5
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.percentile_price_rank_5
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.percentile_price_rank_5 as _canonical

__alpha_meta__ = {
    'id': 'qlib158_rank5',
    'theme': ['momentum'],
    'formula_latex': '\\\\mathrm{ts\\\\_rank}(\\\\mathrm{close}, 5)',
    'columns_required': ['close'],
    'universe': ['equity_us', 'equity_cn', 'equity_hk', 'equity_in', 'equity_kr'],
    'frequency': ['1d'],
    'decay_horizon': 5,
    'min_warmup_bars': 5,
}

from monika.domain.indicators.alpha_zoo.factors.microsoft_qlib_158.percentile_price_rank_5 import (
    annotations,
    compute,
    rank,
    ts_rank,
)

sys.modules[__name__] = _canonical

__all__ = [
    "annotations",
    "compute",
    "rank",
    "ts_rank",
]
