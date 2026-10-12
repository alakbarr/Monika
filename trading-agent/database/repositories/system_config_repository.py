# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.repositories.system_config_repository
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.repositories.system_config_repository"""

import sys
import monika.infrastructure.database.repositories.system_config_repository as _canonical

from monika.infrastructure.database.repositories.system_config_repository import (
    SystemConfigRepository,
)

sys.modules[__name__] = _canonical

__all__ = [
    "SystemConfigRepository",
]
