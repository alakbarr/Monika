# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.db
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.db"""

import sys
import monika.infrastructure.database.db as _canonical

from monika.infrastructure.database.db import (
    AsyncSessionLocal,
    DATABASE_URL,
    _AsyncSessionLocalProxy,
    _IN_MEMORY_EXECUTION_LOCKS,
    _SQLITE_WRITE_LOCKS,
    _async_session_factory,
    _cur_dir,
    _engine_lock,
    _get_write_lock,
    close_db,
    engine,
    get_canonical_db_path,
    get_db,
    get_engine,
    get_session,
    get_sessionmaker,
    get_tier,
    get_write_session,
    init_db,
    is_running_under_test_suite,
    logger,
    transactional_advisory_lock,
    verify_safe_database_url,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AsyncSessionLocal",
    "DATABASE_URL",
    "_AsyncSessionLocalProxy",
    "_IN_MEMORY_EXECUTION_LOCKS",
    "_SQLITE_WRITE_LOCKS",
    "_async_session_factory",
    "_cur_dir",
    "_engine_lock",
    "_get_write_lock",
    "close_db",
    "engine",
    "get_canonical_db_path",
    "get_db",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "get_tier",
    "get_write_session",
    "init_db",
    "is_running_under_test_suite",
    "logger",
    "transactional_advisory_lock",
    "verify_safe_database_url",
]
