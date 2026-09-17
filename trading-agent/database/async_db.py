# ==============================================================================
# File: database/async_db.py
# ==============================================================================

"""
Async Database Session Re-export module.
Provides AsyncSessionLocal and helper functions for async database sessions.
"""

from database.db import AsyncSessionLocal, get_session, engine


def get_engine():
    """Return the global async SQLAlchemy engine."""
    return engine


__all__ = ["AsyncSessionLocal", "get_session", "get_engine", "engine"]
