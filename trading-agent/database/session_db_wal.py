# ==============================================================================
# File: database/session_db_wal.py
# ==============================================================================

"""
High-Performance SQLite WAL Session Database.
Institutional-grade engine turn protection architecture.

Provides low-latency, zero-contention session storage for chat interactions,
turns, and tool call logs with WAL (Write-Ahead Logging) mode, busy timeout,
and normal synchronous pragma configuration.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Database.SessionDbWal")

DEFAULT_SESSION_DB_PATH = Path("trading-agent/data/session_db.sqlite")


class SessionDbWal:
    """Thread-safe SQLite database manager running in WAL mode."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_SESSION_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection with optimized WAL pragmas."""
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
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Initialize schema tables."""
        conn = self.get_connection()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at REAL,
                    updated_at REAL,
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

    def create_or_touch_session(self, session_id: str, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        conn = self.get_connection()
        now = time.time()
        with conn:
            conn.execute("""
                INSERT INTO sessions (session_id, title, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    title = COALESCE(excluded.title, sessions.title),
                    metadata_json = COALESCE(excluded.metadata_json, sessions.metadata_json);
            """, (session_id, title or "Session", now, now, json.dumps(metadata or {})))

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
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT row_id, session_id, role, content, carrier_marker, created_at, turn_ordinal
            FROM session_messages
            WHERE session_id = ?
            ORDER BY row_id ASC;
        """, (session_id,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
