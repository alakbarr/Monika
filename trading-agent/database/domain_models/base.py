# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.domain_models.base
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.domain_models.base"""

import sys
import monika.infrastructure.database.domain_models.base as _canonical

from monika.infrastructure.database.domain_models.base import (
    Base,
    _utcnow,
)

sys.modules[__name__] = _canonical

__all__ = [
    "Base",
    "_utcnow",
]
