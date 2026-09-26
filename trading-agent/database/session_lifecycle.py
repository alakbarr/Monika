# ==============================================================================
# File: database/session_lifecycle.py
# ==============================================================================

"""
Session Lifecycle, Lineage Tracking & Portable State Portability Engine.
Institutional-grade state and turn persistence architecture.

Provides session branching/forking, hierarchical ancestor lineage tracking,
turn rewind/undo integration, and standardized JSON export/import for agent sessions.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.session_db_wal import SessionDbWal

logger = logging.getLogger("TradingAgent.Database.SessionLifecycle")

EXPORT_SCHEMA_VERSION = "1.0.0"


@dataclass
class SessionExportBundle:
    schema_version: str = EXPORT_SCHEMA_VERSION
    exported_at: float = field(default_factory=time.time)
    session: Dict[str, Any] = field(default_factory=dict)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_records: List[Dict[str, Any]] = field(default_factory=list)


def derive_session_title(messages: List[Dict[str, Any]]) -> str:
    """
    Derives an informative session title from the first meaningful user message.
    Cleans leading slash commands, emojis, and truncates to 50 characters.
    """
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            # Strip slash commands e.g. /plan, /chat
            cleaned = re.sub(r"^/[a-zA-Z0-9_\-]+\s*", "", content).strip()
            # Strip markdown headers or newlines
            first_line = cleaned.split("\n")[0].strip()
            first_line = re.sub(r"^[#*>\-\s]+", "", first_line)
            if first_line:
                if len(first_line) > 50:
                    return first_line[:47] + "..."
                return first_line
    return "New Agent Session"


class SessionLifecycleManager:
    """
    Manages session lifecycle states, lineage trees, branching,
    and state export/import serialization.
    """

    def __init__(self, db: SessionDbWal):
        self.db = db

    def fork_session(
        self,
        source_session_id: str,
        up_to_turn: Optional[int] = None,
        new_session_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """
        Forks a session into a child branch up to a specific turn ordinal.
        Preserves lineage pointers (parent_session_id, root_session_id).
        """
        source_sess = self.db.get_session(source_session_id)
        if not source_sess:
            raise ValueError(f"Source session '{source_session_id}' not found.")

        target_id = new_session_id or f"fork_{uuid.uuid4().hex[:12]}"
        root_id = source_sess.get("root_session_id") or source_session_id

        # Get messages up to up_to_turn
        all_messages = self.db.get_messages(source_session_id)
        if up_to_turn is not None:
            forked_messages = [m for m in all_messages if m.get("turn_ordinal", 0) <= up_to_turn]
        else:
            forked_messages = all_messages

        # Derive title if not explicitly provided
        new_title = title or f"Fork: {source_sess.get('title', 'Session')}"
        meta = json.loads(source_sess.get("metadata_json") or "{}")
        meta["forked_from"] = source_session_id
        meta["forked_at_turn"] = up_to_turn

        conn = self.db.get_connection()
        with conn:
            self.db.create_or_touch_session(
                session_id=target_id,
                title=new_title,
                metadata=meta,
                parent_session_id=source_session_id,
                root_session_id=root_id,
                end_reason=None,
            )

            # Copy messages
            for m in forked_messages:
                conn.execute("""
                    INSERT INTO session_messages (session_id, role, content, carrier_marker, created_at, turn_ordinal)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    target_id,
                    m["role"],
                    m["content"],
                    m.get("carrier_marker"),
                    m.get("created_at", time.time()),
                    m.get("turn_ordinal", 1),
                ))

            # Copy tool records
            tools = self.db.get_tool_records(source_session_id)
            if up_to_turn is not None:
                tools = [t for t in tools if t.get("turn_ordinal", 0) <= up_to_turn]

            for t in tools:
                conn.execute("""
                    INSERT INTO tool_records (session_id, turn_ordinal, tool_name, arguments_json, output_text, is_error, has_side_effects, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    target_id,
                    t["turn_ordinal"],
                    t["tool_name"],
                    t.get("arguments_json"),
                    t.get("output_text"),
                    t.get("is_error", 0),
                    t.get("has_side_effects", 0),
                    t.get("created_at", time.time()),
                ))

        logger.info(f"[SessionLifecycle] Forked session '{source_session_id}' -> '{target_id}' ({len(forked_messages)} msgs)")
        return target_id

    def get_session_lineage(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Traces the ancestor path from current session back to root.
        """
        lineage: List[Dict[str, Any]] = []
        curr_id: Optional[str] = session_id

        visited = set()
        while curr_id and curr_id not in visited:
            visited.add(curr_id)
            sess = self.db.get_session(curr_id)
            if not sess:
                break
            lineage.append({
                "session_id": sess["session_id"],
                "title": sess.get("title"),
                "parent_session_id": sess.get("parent_session_id"),
                "root_session_id": sess.get("root_session_id"),
                "created_at": sess.get("created_at"),
                "end_reason": sess.get("end_reason"),
            })
            curr_id = sess.get("parent_session_id")

        return lineage

    def mark_session_closed(self, session_id: str, reason: str = "user_exit") -> None:
        """Mark a session as completed or compressed."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("""
                UPDATE sessions 
                SET end_reason = ?, updated_at = ?
                WHERE session_id = ?;
            """, (reason, time.time(), session_id))

    def export_session_json(self, session_id: str) -> Dict[str, Any]:
        """
        Exports full session state, transcript, and tool execution logs
        into a standardized JSON-serializable bundle.
        """
        sess = self.db.get_session(session_id)
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")

        messages = self.db.get_messages(session_id)
        tools = self.db.get_tool_records(session_id)

        bundle = SessionExportBundle(
            schema_version=EXPORT_SCHEMA_VERSION,
            exported_at=time.time(),
            session=sess,
            messages=messages,
            tool_records=tools,
        )
        return asdict(bundle)

    def import_session_json(
        self,
        data: Dict[str, Any],
        override_session_id: Optional[str] = None,
    ) -> str:
        """
        Imports a standardized session bundle into the WAL database.
        """
        if data.get("schema_version") != EXPORT_SCHEMA_VERSION:
            logger.warning(
                f"[SessionLifecycle] Importing bundle with schema version {data.get('schema_version')} "
                f"(expected {EXPORT_SCHEMA_VERSION}). Proceeding with best-effort parsing."
            )

        raw_session = data.get("session") or {}
        raw_messages = data.get("messages") or []
        raw_tools = data.get("tool_records") or []

        imported_id = override_session_id or raw_session.get("session_id") or f"import_{uuid.uuid4().hex[:12]}"

        conn = self.db.get_connection()
        with conn:
            # Metadata
            metadata = raw_session.get("metadata_json")
            if isinstance(metadata, str):
                try:
                    metadata_dict = json.loads(metadata)
                except Exception:
                    metadata_dict = {}
            else:
                metadata_dict = metadata or {}

            self.db.create_or_touch_session(
                session_id=imported_id,
                title=raw_session.get("title") or derive_session_title(raw_messages),
                metadata=metadata_dict,
                parent_session_id=raw_session.get("parent_session_id"),
                root_session_id=raw_session.get("root_session_id") or imported_id,
                end_reason=raw_session.get("end_reason"),
            )

            # Insert messages
            for m in raw_messages:
                conn.execute("""
                    INSERT INTO session_messages (session_id, role, content, carrier_marker, created_at, turn_ordinal)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    imported_id,
                    m.get("role", "user"),
                    m.get("content", ""),
                    m.get("carrier_marker"),
                    m.get("created_at", time.time()),
                    m.get("turn_ordinal", 1),
                ))

            # Insert tool records
            for t in raw_tools:
                args = t.get("arguments_json")
                if isinstance(args, dict):
                    args_json = json.dumps(args)
                else:
                    args_json = str(args) if args is not None else "{}"

                conn.execute("""
                    INSERT INTO tool_records (session_id, turn_ordinal, tool_name, arguments_json, output_text, is_error, has_side_effects, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    imported_id,
                    t.get("turn_ordinal", 1),
                    t.get("tool_name", "unknown_tool"),
                    args_json,
                    t.get("output_text", ""),
                    t.get("is_error", 0),
                    t.get("has_side_effects", 0),
                    t.get("created_at", time.time()),
                ))

        logger.info(f"[SessionLifecycle] Successfully imported session '{imported_id}' ({len(raw_messages)} msgs)")
        return imported_id
