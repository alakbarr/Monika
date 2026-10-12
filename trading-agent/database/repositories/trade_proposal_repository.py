# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repositories.trade_proposal_repository
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repositories.trade_proposal_repository"""

import sys
import monika.infrastructure.database.repositories.trade_proposal_repository as _canonical

from monika.infrastructure.database.repositories.trade_proposal_repository import (
    TradeProposalRepository,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TradeProposalRepository",
]
