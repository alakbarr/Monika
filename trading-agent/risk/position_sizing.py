# ==============================================================================
# File: risk/position_sizing.py
# Description: Backward-compatibility shim for monika.domain.risk.position_sizing
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.position_sizing
"""

import sys
import monika.domain.risk.position_sizing as _canonical

from monika.domain.risk.position_sizing import (
    DEFAULT_INSTRUMENTS,
    InstrumentSpec,
    PositionSizer,
    SizingResult,
    calculate_lot_size,
    get_instrument_spec,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_INSTRUMENTS",
    "InstrumentSpec",
    "PositionSizer",
    "SizingResult",
    "calculate_lot_size",
    "get_instrument_spec",
    "logger",
]
