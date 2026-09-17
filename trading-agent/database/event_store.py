"""
Targeted Event Store — Append-only immutable event log for trading decisions.

Events emitted at key decision points with correlation/causation chain.
Supports post-mortem replay and audit trail queries.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import TradingEvent

logger = logging.getLogger("TradingAgent.EventStore")


class TradingEventStore:
    """Append-only event store with correlation/causation IDs."""

    @staticmethod
    async def emit(
        session: AsyncSession,
        event_type: str,
        payload: Dict[str, Any],
        correlation_id: str,
        causation_id: Optional[str] = None,
        actor: str = "system",
    ) -> str:
        """
        Append immutable event to store.

        Args:
            session: AsyncSession database session
            event_type: Dot-notation type (e.g. "cycle.started", "risk.verdict", "order.intent")
            payload: Event data (must be JSON-serializable)
            correlation_id: Workflow ID (typically cycle_id or trigger_id)
            causation_id: Direct parent event ID (for causal chain)
            actor: Who/what emitted this event

        Returns:
            Generated event_id (UUID)
        """
        event_id = str(uuid.uuid4())
        event = TradingEvent(
            id=event_id,
            event_type=event_type,
            correlation_id=str(correlation_id),
            causation_id=str(causation_id) if causation_id else None,
            payload=payload,
            actor=actor,
            ts_created=datetime.now(timezone.utc),
        )
        try:
            async with session.begin_nested():
                session.add(event)
                await session.flush()
        except Exception as e:
            logger.debug(f"Event flush failed: {e}")

        logger.debug(
            f"Event emitted: {event_type} (id={event_id[:8]}, "
            f"corr={str(correlation_id)[:8]}, cause={str(causation_id)[:8] if causation_id else 'root'})"
        )
        return event_id

    @staticmethod
    async def get_chain(
        session: AsyncSession,
        correlation_id: str,
    ) -> List[TradingEvent]:
        """Get all events in a correlation chain, ordered by creation time."""
        from sqlalchemy import select, asc
        q = (
            select(TradingEvent)
            .where(TradingEvent.correlation_id == str(correlation_id))
            .order_by(asc(TradingEvent.ts_created))
        )
        result = await session.execute(q)
        return list(result.scalars().all())
