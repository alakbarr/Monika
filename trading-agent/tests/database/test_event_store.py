"""
Unit tests for Targeted Event Store (H5).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from database.event_store import TradingEventStore
from database.models import TradingEvent


@pytest.mark.asyncio
async def test_h5_event_store_emit():
    """H5: Emitting events writes to session with correct correlation and causation IDs."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    # emit() uses session.begin_nested() (SAVEPOINT) as async context manager
    nv = AsyncMock()
    nv.__aenter__ = AsyncMock(return_value=None)
    nv.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin_nested = MagicMock(return_value=nv)

    event_id1 = await TradingEventStore.emit(
        session=mock_session,
        event_type="cycle.started",
        payload={"cycle_id": "c_123", "symbols": ["EURUSD"]},
        correlation_id="c_123",
        actor="cycle_scheduler",
    )

    assert isinstance(event_id1, str)
    assert len(event_id1) == 36  # UUID length
    assert mock_session.add.call_count == 1
    added_event: TradingEvent = mock_session.add.call_args[0][0]
    assert added_event.id == event_id1
    assert added_event.event_type == "cycle.started"
    assert added_event.correlation_id == "c_123"
    assert added_event.causation_id is None
    assert added_event.actor == "cycle_scheduler"
    assert added_event.payload["symbols"] == ["EURUSD"]

    # Emit child event with causation_id pointing to event1
    event_id2 = await TradingEventStore.emit(
        session=mock_session,
        event_type="risk.verdict",
        payload={"approved": True, "recommended_lots": 0.15},
        correlation_id="c_123",
        causation_id=event_id1,
        actor="risk_gate",
    )

    assert mock_session.add.call_count == 2
    child_event: TradingEvent = mock_session.add.call_args[0][0]
    assert child_event.id == event_id2
    assert child_event.event_type == "risk.verdict"
    assert child_event.correlation_id == "c_123"
    assert child_event.causation_id == event_id1


@pytest.mark.asyncio
async def test_h5_event_store_get_chain():
    """H5: get_chain returns all events associated with a correlation_id."""
    mock_session = AsyncMock()
    mock_events = [
        TradingEvent(id="e1", event_type="cycle.started", correlation_id="c_999"),
        TradingEvent(id="e2", event_type="order.intent", correlation_id="c_999", causation_id="e1"),
    ]

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = mock_events
    mock_session.execute = AsyncMock(return_value=mock_res)

    chain = await TradingEventStore.get_chain(mock_session, correlation_id="c_999")
    assert len(chain) == 2
    assert chain[0].id == "e1"
    assert chain[1].id == "e2"
    assert chain[1].causation_id == "e1"
