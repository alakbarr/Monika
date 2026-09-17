# ==============================================================================
# File: telegram_bot/topic_manager.py
# ==============================================================================

"""
Telegram Forum Topic Mode — maps topics to separate agent sessions.

User setup:
  1. Create Telegram group
  2. Group Settings -> enable "Topics"
  3. Invite bot to group with admin rights

Each forum topic maps to an independent ChatAgent session:
  (chat_id, topic_id) -> session_id (stored in DB)

Benefits:
  - Parallel conversations without context pollution
  - Separate topics for different assets, strategies, alerts
  - History preserved per-topic
"""

import logging
from typing import Optional, List, Any
from sqlalchemy import select, delete
from database.models import TelegramTopicBinding

logger = logging.getLogger("TradingAgent.TopicManager")


class TopicManager:
    """Maps Telegram forum topics to isolated ChatAgent sessions."""

    def __init__(self, session_factory: Optional[Any] = None):
        if session_factory is not None:
            self._session_factory = session_factory
        else:
            try:
                from database.async_db import AsyncSessionLocal
                self._session_factory = AsyncSessionLocal
            except ImportError:
                from database.db import AsyncSessionLocal
                self._session_factory = AsyncSessionLocal

    async def get_session_for_topic(
        self, chat_id: int, topic_id: Optional[int]
    ) -> Optional[str]:
        """Look up existing session ID for this topic."""
        if topic_id is None:
            return None
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramTopicBinding).where(
                    TelegramTopicBinding.chat_id == chat_id,
                    TelegramTopicBinding.topic_id == topic_id,
                )
            )
            binding = result.scalar_one_or_none()
            return binding.session_id if binding else None

    async def create_topic_session(
        self, chat_id: int, topic_id: int, topic_name: str = ""
    ) -> str:
        """Create new session for topic (or return existing), return session_id."""
        if topic_id is None:
            return f"tg_chat_{chat_id}"
        session_id = f"tg_topic_{chat_id}_{topic_id}"
        from sqlalchemy.exc import IntegrityError
        async with self._session_factory() as session:
            existing = (await session.execute(
                select(TelegramTopicBinding).where(
                    TelegramTopicBinding.chat_id == chat_id,
                    TelegramTopicBinding.topic_id == topic_id,
                )
            )).scalar_one_or_none()
            if existing:
                if topic_name and existing.topic_name != topic_name:
                    existing.topic_name = topic_name
                    await session.commit()
                return existing.session_id

            try:
                binding = TelegramTopicBinding(
                    chat_id=chat_id,
                    topic_id=topic_id,
                    topic_name=topic_name or f"Topic-{topic_id}",
                    session_id=session_id,
                )
                session.add(binding)
                await session.commit()
                logger.info(f"[TopicManager] Created session {session_id} for chat {chat_id} topic {topic_id}")
            except IntegrityError:
                await session.rollback()
                existing = (await session.execute(
                    select(TelegramTopicBinding).where(
                        TelegramTopicBinding.chat_id == chat_id,
                        TelegramTopicBinding.topic_id == topic_id,
                    )
                )).scalar_one_or_none()
                if existing:
                    return existing.session_id
        return session_id

    async def cleanup_deleted_topic(
        self, chat_id: int, topic_id: int
    ) -> None:
        """Prune binding when Telegram topic is deleted."""
        async with self._session_factory() as session:
            await session.execute(
                delete(TelegramTopicBinding).where(
                    TelegramTopicBinding.chat_id == chat_id,
                    TelegramTopicBinding.topic_id == topic_id,
                )
            )
            await session.commit()
            logger.info(f"[TopicManager] Cleaned up topic {topic_id} for chat {chat_id}")

    async def list_topics_for_chat(
        self, chat_id: int
    ) -> List[TelegramTopicBinding]:
        """List all topic bindings for a specific chat/group."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramTopicBinding).where(
                    TelegramTopicBinding.chat_id == chat_id
                ).order_by(TelegramTopicBinding.created_at.asc())
            )
            return list(result.scalars().all())
