# ==============================================================================
# File: database/fts5_cjk.py
# ==============================================================================

"""
FTS5 Full-Text Search with CJK/Multilingual Bigram Tokenizer and Fail-Open Fallback.
Institutional-grade state and turn persistence architecture.

Provides fast full-text search across session transcripts, memories, and tool outputs.
Features a pure-Python CJK bigram tokenizer fallback that segments East Asian characters
into 2-character bi-grams, enabling search on standard SQLite FTS5 (unicode61).
Includes fail-open resilience that gracefully degrades to SQL LIKE queries if FTS5 MATCH fails.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Database.Fts5Cjk")

# Unicode ranges for CJK Unified Ideographs, Hiragana, Katakana, Hangul
_CJK_REGEX = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)

# Characters that break SQLite FTS5 MATCH queries
_FTS5_SPECIAL_CHARS = re.compile(r'["*^():\-+?{}[\]~]')


def sanitize_fts5_term(term: str) -> str:
    """Strip special FTS5 query characters to prevent syntax errors."""
    cleaned = _FTS5_SPECIAL_CHARS.sub(" ", term)
    return " ".join(cleaned.split())


def tokenize_cjk_bigram(text: str) -> str:
    """
    Transforms text by extracting 2-character bi-grams from CJK sequences
    while preserving standard whitespace-delimited Latin/alphanumeric tokens.
    
    Example:
        'EURUSD 突破 策略' -> 'EURUSD 突破 策略'
        '今天天气很好' -> '今天 天天 天气 气很 很好'
    """
    if not text:
        return ""

    tokens: List[str] = []
    current_latin: List[str] = []
    cjk_buffer: List[str] = []

    def flush_latin():
        if current_latin:
            word = "".join(current_latin).strip()
            if word:
                tokens.append(word)
            current_latin.clear()

    def flush_cjk():
        if cjk_buffer:
            chars = cjk_buffer
            if len(chars) == 1:
                tokens.append(chars[0])
            else:
                for i in range(len(chars) - 1):
                    tokens.append(chars[i] + chars[i + 1])
            cjk_buffer.clear()

    for ch in text:
        if _CJK_REGEX.match(ch):
            flush_latin()
            cjk_buffer.append(ch)
        elif ch.isalnum() or ch in "_-.:":
            flush_cjk()
            current_latin.append(ch)
        else:
            flush_latin()
            flush_cjk()

    flush_latin()
    flush_cjk()

    return " ".join(tokens)


class Fts5SessionSearch:
    """
    Manages FTS5 virtual table for session messages and search queries.
    Provides fail-open degradation to standard SQL LIKE matching upon syntax errors.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_fts()

    def _init_fts(self) -> None:
        """Create FTS5 table if supported."""
        try:
            with self.conn:
                self.conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts USING fts5(
                        row_id UNINDEXED,
                        session_id UNINDEXED,
                        role UNINDEXED,
                        search_tokens,
                        tokenize='unicode61'
                    );
                """)
        except sqlite3.OperationalError as e:
            logger.warning(f"[Fts5SessionSearch] FTS5 virtual table init failed: {e}. Will rely on LIKE fallback.")

    def index_message(self, row_id: int, session_id: str, role: str, content: str) -> None:
        """Index a message into FTS5 table with bigram tokenization."""
        tokens = tokenize_cjk_bigram(content)
        try:
            with self.conn:
                self.conn.execute("""
                    INSERT OR REPLACE INTO session_messages_fts (row_id, session_id, role, search_tokens)
                    VALUES (?, ?, ?, ?);
                """, (row_id, session_id, role, tokens))
        except sqlite3.OperationalError as e:
            logger.debug(f"[Fts5SessionSearch] Failed to index row {row_id} in FTS5: {e}")

    def reindex_all_messages(self) -> int:
        """Reindex all messages from session_messages into session_messages_fts."""
        count = 0
        try:
            cursor = self.conn.execute("SELECT row_id, session_id, role, content FROM session_messages;")
            rows = cursor.fetchall()
            with self.conn:
                self.conn.execute("DELETE FROM session_messages_fts;")
                for r in rows:
                    tokens = tokenize_cjk_bigram(r["content"])
                    self.conn.execute("""
                        INSERT INTO session_messages_fts (row_id, session_id, role, search_tokens)
                        VALUES (?, ?, ?, ?);
                    """, (r["row_id"], r["session_id"], r["role"], tokens))
                    count += 1
        except Exception as e:
            logger.error(f"[Fts5SessionSearch] Reindex failed: {e}")
        return count

    def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Execute full-text search query.
        Tries FTS5 MATCH first; automatically fails open to SQL LIKE on syntax/engine error.
        """
        raw_query = query.strip()
        if not raw_query:
            return []

        search_tokens = tokenize_cjk_bigram(query)
        if not search_tokens.strip():
            return []

        # Try FTS5
        try:
            terms = [sanitize_fts5_term(t) for t in search_tokens.split() if t]
            terms = [t for t in terms if t]
            if not terms:
                return self._fallback_like_search(raw_query, session_id, limit)

            fts_query = " AND ".join(f'"{t}"*' for t in terms)

            sql = """
                SELECT row_id, session_id, role, rank
                FROM session_messages_fts
                WHERE session_messages_fts MATCH ?
            """
            params: List[Any] = [fts_query]

            if session_id:
                sql += " AND session_id = ?"
                params.append(session_id)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor = self.conn.execute(sql, params)
            results = []
            for r in cursor.fetchall():
                results.append({
                    "row_id": r["row_id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "rank": float(r["rank"]) if r["rank"] is not None else 0.0,
                    "engine": "fts5",
                })
            return results
        except sqlite3.OperationalError as err:
            logger.warning(
                f"[Fts5SessionSearch] FTS5 query failed ('{query}'): {err}. Degrading to LIKE fallback."
            )
            return self._fallback_like_search(raw_query, session_id, limit)

    def _fallback_like_search(
        self,
        raw_query: str,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fail-open search using SQL LIKE on session_messages table."""
        words = raw_query.split()
        if not words:
            return []

        like_clauses = ["content LIKE ?"] * len(words)
        where_expr = " AND ".join(like_clauses)
        params: List[Any] = [f"%{w}%" for w in words]

        sql = f"""
            SELECT row_id, session_id, role
            FROM session_messages
            WHERE {where_expr}
        """
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)

        sql += " ORDER BY row_id DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = self.conn.execute(sql, params)
            results = []
            for r in cursor.fetchall():
                results.append({
                    "row_id": r["row_id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "rank": 0.0,
                    "engine": "like_fallback",
                })
            return results
        except Exception as e:
            logger.error(f"[Fts5SessionSearch] Fallback LIKE search also failed: {e}")
            return []
