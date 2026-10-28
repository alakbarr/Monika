# ==============================================================================
# File: application/agent/chat/history.py
# ==============================================================================

"""
Conversation history persistence, session timeout pruning, and failed turn closure.
"""

from __future__ import annotations

import json
import re
from monika.infrastructure.database.db import get_session
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import delete, select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import TelegramConversation
from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.agent.chat.constants import (
    HISTORY_WINDOW,
    MAX_HISTORY_CHARS,
    SESSION_TIMEOUT_HOURS,
)


class HistoryMixin(_ChatAgentMixinBase):
    """Mixin managing database persistence and context window history loading."""

    async def _close_durable_failed_turn(
        self, session_id: Optional[str] = None, reason: str = "Turn aborted before completion"
    ) -> None:
        """Appends a synthetic assistant boundary to session messages in DB if the last message was from user, preserving role alternation."""
        try:
            async with get_session() as session:
                history = await self._load_history(session, session_id=session_id)
                if history and history[-1].get("role") == "user":
                    notice = f"[System Notice: {reason}]"
                    await self._save_message(session, "assistant", notice, session_id=session_id)
                    logger.debug(
                        f"[ChatAgent] Sealed durable failed turn with synthetic assistant boundary for session: {session_id}"
                    )
        except Exception as e:
            logger.warning(f"[ChatAgent] Failed to close durable failed turn: {e}")

    async def _save_message(
        self, session: AsyncSession, role: str, message: str, session_id: Optional[str] = None
    ) -> None:
        """Simpan obrolan ke DB."""
        try:
            uid_str = str(session_id) if session_id else str(self.user_id)
            session.add(
                TelegramConversation(
                    telegram_user_id=uid_str,  # DB field is String
                    role=role,
                    message=message[:4000],
                )
            )
            await session.commit()
        except Exception as e:
            logger.debug(f"Save message failed (non-fatal): {e}")

    async def reset_session(self, session_id: Optional[Union[str, int]] = None, hard_delete: bool = True) -> int:
        """Membersihkan atau mereset riwayat percakapan sesi dari basis data dan SessionDbWal."""
        import asyncio

        uid_str = str(session_id) if session_id is not None else str(self.user_id)
        deleted_count = 0
        try:
            async with get_session() as session:
                if hard_delete:
                    stmt = delete(TelegramConversation).where(
                        TelegramConversation.telegram_user_id == cast(uid_str, String)
                    )
                    res = await session.execute(stmt)
                    deleted_count = int(getattr(res, "rowcount", 0) or 0)
                    await session.commit()
                    logger.info(f"[ChatAgent] Purged {deleted_count} messages for session '{uid_str}' from database.")
        except Exception as e:
            logger.error(f"[ChatAgent] Failed resetting session '{uid_str}' in database: {e}")

        # Close/reset in SessionDbWal & SessionLifecycle if active
        try:
            from monika.infrastructure.database.session_db_wal import DEFAULT_SESSION_DB_PATH, SessionDbWal
            from monika.infrastructure.database.session_lifecycle import SessionLifecycleManager

            if DEFAULT_SESSION_DB_PATH.exists():

                def _close_wal():
                    wal_db = SessionDbWal(DEFAULT_SESSION_DB_PATH)
                    lifecycle = SessionLifecycleManager(wal_db)
                    lifecycle.mark_session_closed(uid_str, reason="user_reset")

                await asyncio.to_thread(_close_wal)
        except Exception as wal_err:
            logger.debug(f"[ChatAgent] SessionDbWal reset notification skipped: {wal_err}")

        return deleted_count

    async def _load_history(self, session: AsyncSession, session_id: Optional[str] = None) -> list[dict]:
        """Muat obrolan terakhir dalam format message list dengan session timeout dan truncation terbaru."""
        from sqlalchemy import String, cast

        uid_str = str(session_id) if session_id else str(self.user_id)
        rows = (
            (
                await session.execute(
                    select(TelegramConversation)
                    .filter(TelegramConversation.telegram_user_id == cast(uid_str, String))
                    .order_by(TelegramConversation.timestamp.desc())
                    .limit(HISTORY_WINDOW)
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            return []

        # Filter time decay: jika ada jeda waktu > SESSION_TIMEOUT_HOURS antar pesan berurutan, putus history
        valid_rows = []
        now = datetime.now(timezone.utc)
        last_ts = now

        for r in rows:
            r_ts = r.timestamp
            if r_ts is not None:
                if r_ts.tzinfo is None:
                    r_ts = r_ts.replace(tzinfo=timezone.utc)
                diff_hours = (last_ts - r_ts).total_seconds() / 3600.0
                if diff_hours > SESSION_TIMEOUT_HOURS:
                    break
                last_ts = r_ts
            valid_rows.append(r)

        # Akumulasi karakter dari pesan terbaru ke pesan lama
        selected_rows = []
        total_chars = 0
        for row in valid_rows:
            content = row.message or ""
            # Bersihkan footer model lama dari teks riwayat
            cleaned_content = re.sub(
                r"(\n\n_?\[?[\w\.\-:]+\s*\|\s*\d+\s*in,\s*\d+\s*out\]?_?|\n\n_?\[?[\w\.\-:]+\]?_?)$", "", content
            ).strip()
            if not cleaned_content:
                continue
            if total_chars + len(cleaned_content) > MAX_HISTORY_CHARS:
                break
            selected_rows.append((row.role, cleaned_content))
            total_chars += len(cleaned_content)

        # Balik ke urutan kronologis (oldest -> newest)
        selected_rows = list(reversed(selected_rows))

        messages = [{"role": role, "content": content} for role, content in selected_rows]
        from monika.application.agent.chat_compaction import ChatMicroCompactor

        compactor = ChatMicroCompactor(max_history_tokens=MAX_HISTORY_CHARS // 4)
        messages = compactor.compact_history(messages)
        return messages
