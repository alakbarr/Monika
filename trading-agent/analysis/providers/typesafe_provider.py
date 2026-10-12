# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.providers.typesafe_provider
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.providers.typesafe_provider"""

import sys
import monika.infrastructure.providers.typesafe_provider as _canonical

from monika.infrastructure.providers.typesafe_provider import (
    TypeSafeProvider,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "TypeSafeProvider",
    "logger",
]
