# ==============================================================================
# File: risk/trade_proposal.py
# Description: Backward-compatibility shim for monika.domain.risk.trade_proposal
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.trade_proposal
"""

import sys
import monika.domain.risk.trade_proposal as _canonical

from monika.domain.risk.trade_proposal import (
    FortressAdmissionValidator,
    TradeProposal,
    _utcnow,
)

sys.modules[__name__] = _canonical

__all__ = [
    "FortressAdmissionValidator",
    "TradeProposal",
    "_utcnow",
]
