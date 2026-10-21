"""The incubation loop must be wired from a closed paper trade to the strategy.

A strategy may only be promoted after real paper results. The chain is:
paper trade closed -> PaperTracker records the outcome -> StrategyDecayMonitor
counts it -> the strategy becomes live-ready after enough good paper trades.

The chain had never been exercised end to end (the live database held two open
paper trades and no closed one), so it is proven here instead of assumed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from monika.application.analysis.strategies.decay_monitor import (
    StrategyDecayMonitor,
    get_strategy_decay_monitor,
)
from monika.core.analytics.paper_tracker import PaperTracker
from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord

STRATEGY_ID = "incubation_probe_alpha"


@pytest.fixture(autouse=True)
def _reset_decay_monitor():
    yield
    StrategyDecayMonitor.reset()


async def _close_paper_trade(session, db_session, pnl_pct: float) -> None:
    analysis = AssetAnalysis(
        symbol="EURUSD",
        generated_at=datetime.now(timezone.utc),
        decision="buy",
        confidence=0.75,
        decision_source="edge_registry",
        source_strategy_id=STRATEGY_ID,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    trade = PaperTradeRecord(
        analysis_id=analysis.id,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        closed_at=datetime.now(timezone.utc),
        exit_price=1.1100,
        exit_reason="tp_hit",
        pnl_pct=pnl_pct,
        status="closed",
    )
    session.add(trade)
    await session.commit()
    await session.refresh(trade)

    tracker = PaperTracker(settings={"paper_trading": {"initial_balance": 10000.0}})
    await tracker._record_decay_outcome(session, trade)


@pytest.mark.asyncio
async def test_closed_paper_trade_feeds_the_incubation_counter(db_session):
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(STRATEGY_ID)

    async with db_session as session:
        await _close_paper_trade(session, db_session, pnl_pct=1.2)

    health = monitor.get_health(STRATEGY_ID)
    assert health.paper_trades_count == 1
    assert health.paper_wins_count == 1
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready(STRATEGY_ID) is False


@pytest.mark.asyncio
async def test_strategy_graduates_after_enough_good_paper_trades(db_session):
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(STRATEGY_ID)

    async with db_session as session:
        for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES):
            await _close_paper_trade(session, db_session, pnl_pct=1.2)

    health = monitor.get_health(STRATEGY_ID)
    assert health.paper_trades_count == StrategyDecayMonitor.MIN_INCUBATION_TRADES
    assert health.is_incubation_passed is True
    assert monitor.is_live_ready(STRATEGY_ID) is True


@pytest.mark.asyncio
async def test_losing_paper_trades_do_not_graduate_the_strategy(db_session):
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(STRATEGY_ID)

    async with db_session as session:
        for _ in range(StrategyDecayMonitor.MIN_INCUBATION_TRADES + 5):
            await _close_paper_trade(session, db_session, pnl_pct=-1.0)

    health = monitor.get_health(STRATEGY_ID)
    assert health.paper_trades_count == StrategyDecayMonitor.MIN_INCUBATION_TRADES + 5
    assert health.is_incubation_passed is False
    assert monitor.is_live_ready(STRATEGY_ID) is False


@pytest.mark.asyncio
async def test_realised_profit_is_used_for_the_profit_factor(db_session):
    """A strategy with large wins and small losses must show that in the factor."""
    monitor = get_strategy_decay_monitor()
    monitor.register_incubating_strategy(STRATEGY_ID)

    async with db_session as session:
        # 8 small losses and 7 large wins: 7*3.0 / 8*1.0 = 2.6 profit factor
        for _ in range(8):
            await _close_paper_trade(session, db_session, pnl_pct=-1.0)
        for _ in range(7):
            await _close_paper_trade(session, db_session, pnl_pct=3.0)

    health = monitor.get_health(STRATEGY_ID)
    assert health.paper_gross_profit == pytest.approx(21.0)
    assert health.paper_gross_loss == pytest.approx(8.0)
    assert health.paper_gross_profit / max(1e-6, health.paper_gross_loss) == pytest.approx(2.625, abs=0.01)
