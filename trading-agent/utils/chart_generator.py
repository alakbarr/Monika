"""
Compatibility facade shim for legacy chart_generator.py.
Re-exports from canonical monika.core.analytics.chart_generator.
"""

from __future__ import annotations

import monika.core.analytics.chart_generator as _canonical

from monika.core.analytics.chart_generator import (
    DARK_STYLE,
    generate_candlestick_chart,
    generate_candlestick_chart_async,
    generate_equity_curve_chart,
    generate_smc_candlestick_chart,
)

__all__ = ['DARK_STYLE', 'generate_candlestick_chart', 'generate_candlestick_chart_async', 'generate_equity_curve_chart', 'generate_smc_candlestick_chart']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
