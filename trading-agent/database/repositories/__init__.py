# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repositories
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repositories"""

import sys
import monika.infrastructure.database.repositories as _canonical

from monika.infrastructure.database.repositories import (
    ActivityLogRepository,
    PositionRepository,
    SystemConfigRepository,
    TradeProposalRepository,
)

__all__ = [
    "ActivityLogRepository",
    "PositionRepository",
    "SystemConfigRepository",
    "TradeProposalRepository",
]
