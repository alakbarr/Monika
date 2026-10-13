# ==============================================================================
# File: database/async_db.py
# ==============================================================================

"""
Async Database Session Re-export module.
Provides AsyncSessionLocal and helper functions for async database sessions.
"""

from monika.infrastructure.database.db import (
    AsyncSessionLocal,
    engine,
    get_canonical_db_path,
    get_session,
    get_write_session,
)
from monika.infrastructure.database.db import (
    get_engine as _get_db_engine,
)


def get_engine():
    """Return the global async SQLAlchemy engine."""
    return _get_db_engine()


__all__ = [
    "AsyncSessionLocal",
    "get_session",
    "get_write_session",
    "get_canonical_db_path",
    "get_engine",
    "engine",
]
