# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.cleanup
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.cleanup"""

import sys
import monika.infrastructure.database.cleanup as _canonical

from monika.infrastructure.database.cleanup import (
    cleanup_old_data,
    drop_expired_partitions,
    logger,
    reset_paper_trading_history,
)

sys.modules[__name__] = _canonical

__all__ = [
    "cleanup_old_data",
    "drop_expired_partitions",
    "logger",
    "reset_paper_trading_history",
]
