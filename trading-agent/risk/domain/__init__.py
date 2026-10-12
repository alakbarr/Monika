# ==============================================================================
# File: risk/domain/__init__.py
# Description: Backward-compatibility shim for monika.domain.risk.instruments
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.instruments
"""

import sys
import monika.domain.risk.instruments as _canonical

from monika.domain.risk.instruments import (
    DEFAULT_INSTRUMENTS,
    InstrumentSpec,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_INSTRUMENTS",
    "InstrumentSpec",
]
