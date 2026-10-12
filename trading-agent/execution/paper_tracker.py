# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.brokers.paper_tracker
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.brokers.paper_tracker"""

import sys
import monika.infrastructure.brokers.paper_tracker as _canonical

from monika.infrastructure.brokers.paper_tracker import (
    PaperTracker,
    _group_by_symbol,
    _group_by_symbol_direction,
)

sys.modules[__name__] = _canonical

__all__ = [
    "PaperTracker",
    "_group_by_symbol",
    "_group_by_symbol_direction",
]
