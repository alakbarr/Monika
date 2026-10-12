# ==============================================================================
# File: risk/domain/instruments.py
# Description: Backward-compatibility shim for monika.domain.risk.instruments.instruments
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.instruments.instruments
"""

import sys
import monika.domain.risk.instruments.instruments as _canonical

from monika.domain.risk.instruments.instruments import (
    DEFAULT_INSTRUMENTS,
    InstrumentSpec,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_INSTRUMENTS",
    "InstrumentSpec",
]
