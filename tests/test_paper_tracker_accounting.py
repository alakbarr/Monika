"""Phase 0 regression tests: realized R must use the entry-time risk anchor.

The historical bug used ``abs(entry - stop_loss)`` with the *current* stop,
which TrailingStopManager had already moved. A stop moved past entry therefore
became a smaller denominator and produced an overstated loss (or an overstated
profit). These tests pin realized PnL to the immutable ``initial_stop_loss``.
"""

from datetime import UTC, datetime, timedelta

import pytest

from monika.core.analytics.paper_tracker import PaperTracker
from monika.infrastructure.database.models import (
    AssetAnalysis,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
)


def _bar(
    symbol: str,
    timeframe: str,
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> PriceOHLCV:
    return PriceOHLCV(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
    )


@pytest.mark.asyncio
async def test_trailing_stop_profit_is_measured_against_initial_risk(db_session):
    """A sell whose trailing stop moved below entry keeps the original 0.00306 risk."""
    now = datetime.now(UTC)
    trade = PaperTradeRecord(
        symbol="GBPUSD",
        direction="sell",
        entry_price=1.33444,
        stop_loss=1.334266,  # trailing stop locked in profit, moved below entry
        take_profit=1.32800,
        initial_stop_loss=1.33750,  # immutable entry anchor
        initial_risk_pct=1.0,
        risk_pct=1.0,
        opened_at=now - timedelta(hours=1),
        status="open",
        accounting_status="ok",
    )
    db_session.add(trade)
    db_session.add(
        _bar(
            "GBPUSD",
            "M15",
            now - timedelta(minutes=5),
            open_=1.33420,
            high=1.33436,
            low=1.33400,
            close=1.33430,
        )
    )
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    closed = await tracker.check_and_close_trades(db_session)

    assert len(closed) == 1
    # spread = 0.00012 * 1.5 = 0.00018; exit = min(entry, stop + spread/2)
    # move = 1.33444 - 1.334356 = 0.000084; R = 0.000084 / 0.00306
    # Stored with 4-decimal precision -> 0.0275, not the old 0.48 from the
    # shrunken trailing-stop denominator.
    assert trade.pnl_pct == pytest.approx(0.0275, abs=1e-4)
    assert trade.exit_reason == "trailing_sl"
    assert trade.accounting_status == "ok"
    assert trade.initial_stop_loss == pytest.approx(1.33750)
    assert trade.stop_loss == pytest.approx(1.334266)


@pytest.mark.asyncio
async def test_missing_initial_anchor_fails_closed_instead_of_guessing(db_session):
    """Without an entry anchor, PnL stays NULL and is excluded from statistics."""
    now = datetime.now(UTC)
    trade = PaperTradeRecord(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.10000,
        stop_loss=1.09000,
        take_profit=1.12000,
        initial_stop_loss=None,
        initial_risk_pct=1.0,
        risk_pct=1.0,
        opened_at=now - timedelta(hours=1),
        status="open",
        accounting_status="ok",
    )
    db_session.add(trade)
    db_session.add(
        _bar(
            "EURUSD",
            "M15",
            now - timedelta(minutes=5),
            open_=1.09050,
            high=1.09100,
            low=1.08900,
            close=1.08950,
        )
    )
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    closed = await tracker.check_and_close_trades(db_session)

    assert len(closed) == 1
    assert trade.status == "closed"
    assert trade.pnl_pct is None
    assert trade.accounting_status == "invalid_initial_stop"

    stats = await tracker.get_statistics(db_session)
    assert stats["total_trades"] == 0
    assert stats["total_pnl_pct"] == 0.0


@pytest.mark.asyncio
async def test_force_close_without_anchor_leaves_pnl_unverified(db_session):
    """Age-based force close must not invent zero PnL when risk is unknown."""
    now = datetime.now(UTC)
    trade = PaperTradeRecord(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        initial_stop_loss=None,
        initial_risk_pct=1.0,
        risk_pct=1.0,
        opened_at=now - timedelta(hours=49),
        status="open",
        accounting_status="ok",
    )
    db_session.add(trade)
    db_session.add(_bar("XAUUSD", "H4", now - timedelta(hours=1), open_=1995.0, high=1998.0, low=1992.0, close=1996.0))
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    closed = await tracker.check_and_close_trades(db_session)

    assert len(closed) == 1
    assert trade.status == "closed"
    assert trade.exit_reason == "max_holding_time"
    assert trade.pnl_pct is None
    assert trade.accounting_status == "invalid_initial_stop"


@pytest.mark.asyncio
async def test_expired_limit_is_not_counted_as_a_zero_pnl_trade(db_session):
    """A limit order that never filled is 'not_filled', not a breakeven trade."""
    now = datetime.now(UTC)
    trade = PaperTradeRecord(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.10000,
        stop_loss=1.09000,
        take_profit=1.12000,
        initial_stop_loss=1.09000,
        initial_risk_pct=1.0,
        risk_pct=1.0,
        opened_at=now - timedelta(hours=49),
        status="open",
        is_pending_fill=True,
        stated_entry_price=1.05000,
        accounting_status="ok",
    )
    db_session.add(trade)
    db_session.add(
        _bar(
            "EURUSD",
            "M15",
            now - timedelta(minutes=30),
            open_=1.10000,
            high=1.10100,
            low=1.09900,
            close=1.10000,
        )
    )
    await db_session.commit()

    tracker = PaperTracker(
        settings={"paper_trading": {"initial_balance": 10000.0, "max_paper_trade_holding_hours": 200}}
    )
    await tracker.check_and_close_trades(db_session)

    assert trade.status == "closed"
    assert trade.exit_reason == "expired_limit"
    assert trade.pnl_pct == 0.0
    assert trade.accounting_status == "not_filled"

    stats = await tracker.get_statistics(db_session)
    assert stats["total_trades"] == 0


@pytest.mark.asyncio
async def test_linked_position_mirrors_verified_pnl_and_clamps_time(db_session):
    """The Position row must receive the verified PnL and never close before it opened."""
    now = datetime.now(UTC)
    analysis = AssetAnalysis(
        symbol="EURUSD",
        decision="buy",
        confidence=0.8,
        stop_loss=1.09000,
        take_profit=1.12000,
    )
    db_session.add(analysis)
    await db_session.flush()

    trade = PaperTradeRecord(
        analysis_id=analysis.id,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.10000,
        stop_loss=1.09000,
        take_profit=1.12000,
        initial_stop_loss=1.09000,
        initial_risk_pct=1.0,
        risk_pct=1.0,
        opened_at=now - timedelta(hours=2),
        status="open",
        accounting_status="ok",
    )
    position = Position(
        analysis_id=analysis.id,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.10000,
        opened_at=now - timedelta(minutes=30),
        status="open",
        is_paper=True,
    )
    db_session.add_all([trade, position])
    db_session.add(
        _bar(
            "EURUSD",
            "M15",
            now - timedelta(minutes=5),
            open_=1.08950,
            high=1.09000,
            low=1.08800,
            close=1.08850,
        )
    )
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    await tracker.check_and_close_trades(db_session)

    assert trade.pnl_pct is not None
    assert position.status == "closed"
    assert position.pnl == pytest.approx(10000.0 * trade.pnl_pct / 100.0, abs=0.01)
    assert position.closed_at is not None
    assert position.closed_at >= position.opened_at
