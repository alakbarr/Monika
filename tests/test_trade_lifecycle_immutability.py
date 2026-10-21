"""Phase 0: trailing may move the live stop, but never the entry-time anchor."""

from datetime import UTC, datetime, timedelta

import pytest

from monika.core.analytics.paper_tracker import PaperTracker
from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord, Position, PriceOHLCV


def _analysis(symbol: str = "EURUSD", stop_loss: float = 1.09000) -> AssetAnalysis:
    return AssetAnalysis(
        symbol=symbol,
        decision="buy",
        confidence=0.8,
        stop_loss=stop_loss,
        take_profit=1.12000,
    )


@pytest.mark.asyncio
async def test_trailing_updates_current_stop_but_not_initial_anchor(db_session):
    analysis = _analysis()
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
        opened_at=datetime.now(UTC),
        status="open",
        accounting_status="ok",
    )
    db_session.add(trade)
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    await tracker.update_paper_trade_sl(db_session, analysis.id, 1.10500)

    assert trade.stop_loss == pytest.approx(1.10500)
    assert trade.initial_stop_loss == pytest.approx(1.09000)
    assert trade.initial_risk_pct == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_closed_trade_is_not_rewritten_by_a_later_pass(db_session):
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
        opened_at=now - timedelta(hours=1),
        status="open",
        accounting_status="ok",
    )
    db_session.add(trade)
    db_session.add(
        PriceOHLCV(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=now - timedelta(minutes=5),
            open=1.09050,
            high=1.09100,
            low=1.08900,
            close=1.08950,
            volume=1000.0,
        )
    )
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    await tracker.check_and_close_trades(db_session)

    first_pnl = trade.pnl_pct
    first_exit = trade.exit_price
    first_closed_at = trade.closed_at
    assert trade.status == "closed"
    assert first_pnl is not None
    assert trade.initial_stop_loss == pytest.approx(1.09000)

    second_pass = await tracker.check_and_close_trades(db_session)

    assert second_pass == []
    assert trade.pnl_pct == first_pnl
    assert trade.exit_price == first_exit
    assert trade.closed_at == first_closed_at
    assert trade.initial_stop_loss == pytest.approx(1.09000)


@pytest.mark.asyncio
async def test_linked_position_closed_at_is_never_before_opened_at(db_session):
    now = datetime.now(UTC)
    analysis = _analysis()
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
        pnl_pct=-0.5,
        opened_at=now,
        closed_at=now - timedelta(hours=3),  # stale bar timestamp from a timezone bug
        status="closed",
        accounting_status="ok",
    )
    position = Position(
        analysis_id=analysis.id,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.10000,
        opened_at=now,
        status="open",
        is_paper=True,
    )
    db_session.add_all([trade, position])
    await db_session.commit()

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    await tracker._close_linked_position(db_session, trade)

    assert position.status == "closed"
    assert position.closed_at == position.opened_at
    assert position.pnl == pytest.approx(-50.0)
