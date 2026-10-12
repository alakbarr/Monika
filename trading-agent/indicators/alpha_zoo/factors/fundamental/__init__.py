# ==============================================================================
# File: indicators/alpha_zoo/factors/fundamental/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.fundamental
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.fundamental
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.fundamental as _canonical

sys.modules[__name__] = _canonical

__all__: list[str] = []
