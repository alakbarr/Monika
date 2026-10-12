# ==============================================================================
# File: indicators/alpha_zoo/factors/__init__.py
# Description: Backward-compatibility shim for monika.domain.indicators.alpha_zoo.factors
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.indicators.alpha_zoo.factors
"""

import sys
import monika.domain.indicators.alpha_zoo.factors as _canonical

sys.modules[__name__] = _canonical

__all__: list[str] = []
