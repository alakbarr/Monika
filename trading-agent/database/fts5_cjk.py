# ==============================================================================
# File: database/fts5_cjk.py
# ==============================================================================

"""
FTS5 Full-Text Search with CJK/Multilingual Bigram Tokenizer.
Institutional-grade engine turn protection architecture.

Provides fast full-text search across session transcripts, memories, and tool outputs.
Features a pure-Python CJK bigram tokenizer fallback that segments East Asian characters
into 2-character bi-grams, enabling flawless search on standard SQLite FTS5 (unicode61)
without requiring native C extensions.
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
    """Manages FTS5 virtual table for session messages and search queries."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._init_fts()

    def _init_fts(self) -> None:
        """Create FTS5 table if supported."""
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

    def index_message(self, row_id: int, session_id: str, role: str, content: str) -> None:
        """Index a message into FTS5 table with bigram tokenization."""
        tokens = tokenize_cjk_bigram(content)
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO session_messages_fts (row_id, session_id, role, search_tokens)
                VALUES (?, ?, ?, ?);
            """, (row_id, session_id, role, tokens))

    def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Execute FTS5 search query. Returns matching rows with rank.
        """
        search_tokens = tokenize_cjk_bigram(query)
        if not search_tokens.strip():
            return []

        # Format FTS5 query with prefix search
        terms = [t for t in search_tokens.split() if t]
        if not terms:
            return []
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
                "rank": r["rank"],
            })
        return results
