# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repair_ledger
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repair_ledger"""

import sys
import monika.infrastructure.database.repair_ledger as _canonical

from monika.infrastructure.database.repair_ledger import (
    RepairLedger,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "RepairLedger",
    "logger",
]
