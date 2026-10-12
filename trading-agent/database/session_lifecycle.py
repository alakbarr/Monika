# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.session_lifecycle
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.session_lifecycle"""

import sys
import monika.infrastructure.database.session_lifecycle as _canonical

from monika.infrastructure.database.session_lifecycle import (
    EXPORT_SCHEMA_VERSION,
    SessionExportBundle,
    SessionLifecycleManager,
    derive_session_title,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "SessionExportBundle",
    "SessionLifecycleManager",
    "derive_session_title",
    "logger",
]
