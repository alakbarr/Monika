# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.session_db_wal
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.session_db_wal"""

import sys
import monika.infrastructure.database.session_db_wal as _canonical

from monika.infrastructure.database.session_db_wal import (
    DEFAULT_SESSION_DB_PATH,
    FileLockGuard,
    SessionDbReadPool,
    SessionDbWal,
    _FD_RESERVE_HEADROOM,
    _PROCESS_ACTIVE_READERS,
    _PROCESS_ACTIVE_READERS_LOCK,
    _READ_POOL_MAX_PER_INSTANCE,
    _READ_POOL_PROCESS_MAX,
    check_fd_headroom,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "DEFAULT_SESSION_DB_PATH",
    "FileLockGuard",
    "SessionDbReadPool",
    "SessionDbWal",
    "_FD_RESERVE_HEADROOM",
    "_PROCESS_ACTIVE_READERS",
    "_PROCESS_ACTIVE_READERS_LOCK",
    "_READ_POOL_MAX_PER_INSTANCE",
    "_READ_POOL_PROCESS_MAX",
    "check_fd_headroom",
    "logger",
]
