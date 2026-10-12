# ==============================================================================
# File: indicators/alpha_zoo/factors/worldquant_101/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.worldquant_101
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.worldquant_101
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.worldquant_101 as _canonical

sys.modules[__name__] = _canonical

__all__: list[str] = []
