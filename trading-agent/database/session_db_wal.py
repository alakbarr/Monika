# ==============================================================================
# File: database/session_db_wal.py
# ==============================================================================

"""
High-Performance SQLite WAL Session Database with Bounded Read Pool & Lock Guards.
Institutional-grade state and turn persistence architecture.

Provides low-latency, zero-contention session storage for chat interactions,
turns, and tool call logs with WAL (Write-Ahead Logging) mode, bounded connection
read pooling, file descriptor headroom protection, and cross-platform file locking.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Database.SessionDbWal")

DEFAULT_SESSION_DB_PATH = Path("trading-agent/data/session_db.sqlite")

# Pool limits
_READ_POOL_MAX_PER_INSTANCE = 8
_READ_POOL_PROCESS_MAX = 24
_FD_RESERVE_HEADROOM = 64

# Global process-wide connection counter
_PROCESS_ACTIVE_READERS_LOCK = threading.Lock()
_PROCESS_ACTIVE_READERS = 0


def check_fd_headroom(reserve: int = _FD_RESERVE_HEADROOM) -> bool:
    """
    Check if the host operating system has enough file descriptor headroom.
    Returns True if headroom is sufficient or cannot be determined.
    """
    if sys.platform != "win32":
        try:
            import resource
            soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            if soft_limit != resource.RLIM_INFINITY:
                # Approximate open FDs by listing /proc/self/fd if available
                fd_dir = Path("/proc/self/fd")
                if fd_dir.exists():
                    open_count = len(list(fd_dir.iterdir()))
                    return (soft_limit - open_count) > reserve
        except Exception:
            return True
    return True


class FileLockGuard:
    """
    Cross-platform file locking guard for exclusive database operations.
    Supports Windows (msvcrt) and POSIX (fcntl).
    """

    def __init__(self, lock_path: Path, timeout: float = 5.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd: Optional[int] = None

    def __enter__(self) -> FileLockGuard:
        start_time = time.time()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR)

        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    # Lock 1 byte at position 0 non-blocking
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError):
                if time.time() - start_time >= self.timeout:
                    if self._fd is not None:
                        os.close(self._fd)
                        self._fd = None
                    raise TimeoutError(f"Could not acquire lock on {self.lock_path} within {self.timeout}s")
                time.sleep(0.05)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._fd is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl
                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                os.close(self._fd)
                self._fd = None


class SessionDbReadPool:
    """
    Bounded thread-safe read pool for SQLite WAL database.
    Prevents thread exhaustion and file descriptor leaks under high read concurrency.
    """

    def __init__(self, db_path: Path, max_connections: int = _READ_POOL_MAX_PER_INSTANCE):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_connections)
        self._allocated = 0
        self._lock = threading.Lock()
        self._closed = False

    def _create_connection(self) -> sqlite3.Connection:
        global _PROCESS_ACTIVE_READERS
        with _PROCESS_ACTIVE_READERS_LOCK:
            if _PROCESS_ACTIVE_READERS >= _READ_POOL_PROCESS_MAX:
                logger.warning(
                    f"[SessionDbReadPool] Process-wide reader limit ({_READ_POOL_PROCESS_MAX}) reached."
                )
            if not check_fd_headroom():
                logger.warning("[SessionDbReadPool] FD headroom critical; reader connection might fail.")
            _PROCESS_ACTIVE_READERS += 1

        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextlib.contextmanager
    def acquire_reader(self, timeout: float = 5.0) -> Generator[sqlite3.Connection, None, None]:
        """Acquire a read-only connection from the bounded pool."""
        if self._closed:
            raise RuntimeError("SessionDbReadPool is closed.")

        conn: Optional[sqlite3.Connection] = None
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._allocated < self.max_connections:
                    conn = self._create_connection()
                    self._allocated += 1

        if conn is None:
            try:
                conn = self._pool.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError(f"Timed out waiting for reader connection after {timeout}s")

        try:
            yield conn
        finally:
            if not self._closed and conn is not None:
                try:
                    self._pool.put_nowait(conn)
                except queue.Full:
                    self._close_conn(conn)
            elif conn is not None:
                self._close_conn(conn)

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        global _PROCESS_ACTIVE_READERS
        try:
            conn.close()
        except Exception:
            pass
        with _PROCESS_ACTIVE_READERS_LOCK:
            _PROCESS_ACTIVE_READERS = max(0, _PROCESS_ACTIVE_READERS - 1)

    def close(self) -> None:
        """Close all connections in the read pool."""
        self._closed = True
        with self._lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    self._close_conn(conn)
                except queue.Empty:
                    break
            self._allocated = 0


class SessionDbWal:
    """Thread-safe SQLite database manager running in WAL mode with read pooling."""

    def __init__(self, db_path: Optional[Path] = None, enable_read_pool: bool = True):
        self.db_path = db_path or DEFAULT_SESSION_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.db_path.with_suffix(".lock")
        self._local = threading.local()
        self._enable_read_pool = enable_read_pool
        self._read_pool: Optional[SessionDbReadPool] = None
        if self._enable_read_pool:
            self._read_pool = SessionDbReadPool(self.db_path)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite read-write connection with optimized WAL pragmas."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=15.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Configure high-performance WAL pragmas
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA journal_size_limit = 67108864;")  # 64MB WAL ceiling
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA cache_size = -64000;")  # 64MB page cache
            try:
                conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB mmap
            except sqlite3.OperationalError:
                pass
            self._local.conn = conn
        return self._local.conn

    def acquire_reader(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for obtaining a read-only pooled connection."""
        if self._read_pool is not None:
            return self._read_pool.acquire_reader()
        else:
            @contextlib.contextmanager
            def _fallback():
                yield self.get_connection()
            return _fallback()

    def _init_db(self) -> None:
        """Initialize schema tables and lineage metadata."""
        conn = self.get_connection()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at REAL,
                    updated_at REAL,
                    parent_session_id TEXT,
                    root_session_id TEXT,
                    end_reason TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS session_messages (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    carrier_marker TEXT,
                    created_at REAL NOT NULL,
                    turn_ordinal INTEGER NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_session_msg_lookup 
                ON session_messages(session_id, turn_ordinal);

                CREATE TABLE IF NOT EXISTS tool_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_ordinal INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT,
                    output_text TEXT,
                    is_error INTEGER DEFAULT 0,
                    has_side_effects INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tool_lookup 
                ON tool_records(session_id, turn_ordinal);
            """)

    def create_or_touch_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent_session_id: Optional[str] = None,
        root_session_id: Optional[str] = None,
        end_reason: Optional[str] = None,
    ) -> None:
        conn = self.get_connection()
        now = time.time()
        with conn:
            conn.execute("""
                INSERT INTO sessions (
                    session_id, title, created_at, updated_at, 
                    parent_session_id, root_session_id, end_reason, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    title = COALESCE(excluded.title, sessions.title),
                    parent_session_id = COALESCE(excluded.parent_session_id, sessions.parent_session_id),
                    root_session_id = COALESCE(excluded.root_session_id, sessions.root_session_id),
                    end_reason = COALESCE(excluded.end_reason, sessions.end_reason),
                    metadata_json = COALESCE(excluded.metadata_json, sessions.metadata_json);
            """, (
                session_id,
                title or "Session",
                now,
                now,
                parent_session_id,
                root_session_id or session_id,
                end_reason,
                json.dumps(metadata or {}),
            ))

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        turn_ordinal: int,
        carrier_marker: Optional[str] = None,
    ) -> int:
        self.create_or_touch_session(session_id)
        conn = self.get_connection()
        now = time.time()
        with conn:
            cursor = conn.execute("""
                INSERT INTO session_messages (session_id, role, content, carrier_marker, created_at, turn_ordinal)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (session_id, role, content, carrier_marker, now, turn_ordinal))
            return cursor.lastrowid

    def record_tool_execution(
        self,
        session_id: str,
        turn_ordinal: int,
        tool_name: str,
        arguments: Dict[str, Any],
        output: str,
        is_error: bool = False,
        has_side_effects: bool = False,
    ) -> int:
        conn = self.get_connection()
        now = time.time()
        with conn:
            cursor = conn.execute("""
                INSERT INTO tool_records (session_id, turn_ordinal, tool_name, arguments_json, output_text, is_error, has_side_effects, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                session_id,
                turn_ordinal,
                tool_name,
                json.dumps(arguments),
                output,
                1 if is_error else 0,
                1 if has_side_effects else 0,
                now,
            ))
            return cursor.lastrowid

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch all messages for session."""
        if self._read_pool:
            with self._read_pool.acquire_reader() as conn:
                cursor = conn.execute("""
                    SELECT row_id, session_id, role, content, carrier_marker, created_at, turn_ordinal
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY row_id ASC;
                """, (session_id,))
                return [dict(row) for row in cursor.fetchall()]
        else:
            conn = self.get_connection()
            cursor = conn.execute("""
                SELECT row_id, session_id, role, content, carrier_marker, created_at, turn_ordinal
                FROM session_messages
                WHERE session_id = ?
                ORDER BY row_id ASC;
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_tool_records(self, session_id: str, turn_ordinal: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch tool execution records for session."""
        sql = """
            SELECT id, session_id, turn_ordinal, tool_name, arguments_json, output_text, is_error, has_side_effects, created_at
            FROM tool_records
            WHERE session_id = ?
        """
        params: List[Any] = [session_id]
        if turn_ordinal is not None:
            sql += " AND turn_ordinal = ?"
            params.append(turn_ordinal)
        sql += " ORDER BY id ASC;"

        if self._read_pool:
            with self._read_pool.acquire_reader() as conn:
                cursor = conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        else:
            conn = self.get_connection()
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch session metadata."""
        sql = "SELECT * FROM sessions WHERE session_id = ?;"
        if self._read_pool:
            with self._read_pool.acquire_reader() as conn:
                cursor = conn.execute(sql, (session_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        else:
            conn = self.get_connection()
            cursor = conn.execute(sql, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def wal_checkpoint(self, mode: str = "PASSIVE") -> Tuple[int, int, int]:
        """
        Execute WAL checkpoint (PASSIVE, FULL, RESTART, TRUNCATE) with file lock protection.
        Returns (busy, log, checkpointed) page counts.
        """
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        target_mode = mode.upper()
        if target_mode not in valid_modes:
            raise ValueError(f"Invalid WAL checkpoint mode: {mode}")

        with FileLockGuard(self.lock_path):
            conn = self.get_connection()
            cursor = conn.execute(f"PRAGMA wal_checkpoint({target_mode});")
            res = cursor.fetchone()
            return (int(res[0]), int(res[1]), int(res[2])) if res else (0, 0, 0)

    def vacuum_into(self, destination: Path) -> None:
        """Atomic hot backup to a standalone SQLite database file."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        with FileLockGuard(self.lock_path):
            conn = self.get_connection()
            conn.execute("VACUUM INTO ?;", (str(destination),))

    def close(self) -> None:
        """Close connection and connection pool."""
        if self._read_pool is not None:
            self._read_pool.close()
            self._read_pool = None

        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
