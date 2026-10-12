# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repositories.position_repository
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repositories.position_repository"""

import sys
import monika.infrastructure.database.repositories.position_repository as _canonical

from monika.infrastructure.database.repositories.position_repository import (
    PositionRepository,
)

sys.modules[__name__] = _canonical

__all__ = [
    "PositionRepository",
]
