# ==============================================================================
# File: indicators/alpha_zoo/factors/academic/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors.academic
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors.academic
"""

import sys
import monika.domain.indicators.alpha_zoo.factors.academic as _canonical

sys.modules[__name__] = _canonical

__all__: list[str] = []
