# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.async_db
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.async_db"""

import sys
import monika.infrastructure.database.async_db as _canonical

from monika.infrastructure.database.async_db import (
    AsyncSessionLocal,
    engine,
    get_canonical_db_path,
    get_engine,
    get_session,
    get_write_session,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AsyncSessionLocal",
    "engine",
    "get_canonical_db_path",
    "get_engine",
    "get_session",
    "get_write_session",
]
