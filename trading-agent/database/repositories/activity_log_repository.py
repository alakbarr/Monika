# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repositories.activity_log_repository
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repositories.activity_log_repository"""

import sys
import monika.infrastructure.database.repositories.activity_log_repository as _canonical

from monika.infrastructure.database.repositories.activity_log_repository import (
    ActivityLogRepository,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ActivityLogRepository",
]
