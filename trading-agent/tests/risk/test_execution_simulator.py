import pytest
from unittest.mock import AsyncMock, MagicMock
from risk.execution_simulator import ExecutionSimulator, ExecutionSimulationResult, SlippageScenario
from database.models import PriceOHLCV
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_simulator_resilient_trade():
    """
    Normal trade with generous edge relative to slippage drag passes stress test.
    """
    sim = ExecutionSimulator(
        settings={"trading": {"risk": {"slippage_sandbox_enabled": True, "min_edge_to_slippage_ratio": 1.1}}}
    )

    # 100 synthetic ticks around 1.0850 with 1.5 pips spread (0.00015)
    ticks = [{"bid": 1.08500, "ask": 1.08515, "spread": 0.00015}] * 100

    result = await sim.simulate_execution(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.08500,
        stop_loss=1.08200,
        take_profit=1.09100,  # 60 pips gross edge
        ticks=ticks,
    )

    assert isinstance(result, ExecutionSimulationResult)
    assert result.resilient is True
    assert result.edge_to_drag_ratio > 1.1
    assert result.rejection_reason is None
    assert "baseline" in result.scenarios
    assert "elevated" in result.scenarios
    assert "stress" in result.scenarios
    assert result.scenarios["stress"].multiplier == 3.0
    assert result.scenarios["stress"].slippage_drag > result.scenarios["baseline"].slippage_drag


@pytest.mark.asyncio
async def test_simulator_unfavorable_slippage_rejection():
    """
    Razor-thin trade edge with wide spread fails slippage stress simulation.
    """
    sim = ExecutionSimulator(
        settings={"trading": {"risk": {"slippage_sandbox_enabled": True, "min_edge_to_slippage_ratio": 1.1}}}
    )

    # 100 ticks with wide spread: 0.00030 (3 pips)
    ticks = [{"bid": 1.08500, "ask": 1.08530, "spread": 0.00030}] * 100

    # Trade has only 0.00025 gross edge
    result = await sim.simulate_execution(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.08500,
        stop_loss=1.08450,
        take_profit=1.08525,  # 2.5 pips gross edge < 3.0x stress drag
        ticks=ticks,
    )

    assert result.resilient is False
    assert result.edge_to_drag_ratio < 1.1
    assert result.rejection_reason is not None
    assert "SLIPPAGE_UNFAVORABLE" in result.rejection_reason


@pytest.mark.asyncio
async def test_simulator_disabled_by_config():
    """
    When disabled by config, simulator passes unconditionally.
    """
    sim = ExecutionSimulator(
        settings={"trading": {"risk": {"slippage_sandbox_enabled": False}}}
    )

    result = await sim.simulate_execution(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.08500,
        stop_loss=1.08490,
        take_profit=1.08501,
    )

    assert result.resilient is True
    assert result.edge_to_drag_ratio == 99.0
    assert result.details.get("status") == "disabled_by_config"


@pytest.mark.asyncio
async def test_simulator_fetch_recent_ticks_mt5():
    """
    Tests tick retrieval from MT5 client when available.
    """
    mock_mt5 = MagicMock()
    mock_mt5.get_ticks = AsyncMock(
        return_value=[
            {"bid": 1.0850, "ask": 1.0852, "flags": 0} for _ in range(50)
        ]
    )

    sim = ExecutionSimulator(mt5_client=mock_mt5)
    ticks = await sim.fetch_recent_ticks("EURUSD", count=50)

    assert len(ticks) == 50
    assert round(ticks[0]["spread"], 5) == 0.0002


@pytest.mark.asyncio
async def test_simulator_fetch_recent_ticks_ohlcv_fallback(db_session):
    """
    Tests tick reconstruction from OHLCV bars when MT5 is unavailable.
    """
    sim = ExecutionSimulator(mt5_client=None)

    # Insert mock OHLCV bars
    for i in range(5):
        bar = PriceOHLCV(
            symbol="EURUSD",
            timeframe="M1",
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=1.0850 + i * 0.0001,
            high=1.0855 + i * 0.0001,
            low=1.0848 + i * 0.0001,
            close=1.0852 + i * 0.0001,
            volume=100.0,
        )
        db_session.add(bar)
    await db_session.commit()

    ticks = await sim.fetch_recent_ticks("EURUSD", count=30, session=db_session)
    assert len(ticks) > 0
    assert all("spread" in t and "bid" in t and "ask" in t for t in ticks)
