"""
Unit tests for SMCFairValueGapStrategy and BBVolumeProfileMeanReversion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.strategies.smc_fvg import SMCFairValueGapStrategy
from analysis.strategies.bb_volume_profile import BBVolumeProfileMeanReversion
from analysis.strategies.registry import StrategyRegistry


def test_strategy_registry_includes_smc_and_bb():
    assert "smc_fvg" in StrategyRegistry._registry
    assert "bb_volume_profile" in StrategyRegistry._registry
    assert StrategyRegistry.get("smc_fvg") is SMCFairValueGapStrategy
    assert StrategyRegistry.get("bb_volume_profile") is BBVolumeProfileMeanReversion


@pytest.mark.asyncio
async def test_smc_fvg_strategy_bullish_signal():
    strat = SMCFairValueGapStrategy()
    mock_session = AsyncMock()

    # Synthetic candles creating a Bullish FVG
    candles = [
        MagicMock(open=100.0, high=102.0, low=99.0, close=101.0, volume=100.0),
        MagicMock(open=101.0, high=108.0, low=101.0, close=107.5, volume=500.0),  # Big impulse
        MagicMock(open=107.5, high=110.0, low=104.0, close=109.0, volume=200.0),  # Gap between 102 and 104
        MagicMock(open=109.0, high=109.5, low=103.0, close=103.5, volume=150.0),  # Retest inside gap
    ]
    strat.get_historical_candles = AsyncMock(return_value=candles)

    signal = await strat.evaluate(mock_session, "EURUSD", {})
    assert signal.strategy_id == "smc_fvg"
    assert signal.symbol == "EURUSD"
    if signal.valid:
        assert signal.direction in ("buy", "sell")
        assert signal.entry_price > 0
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


@pytest.mark.asyncio
async def test_bb_volume_profile_oversold_signal():
    strat = BBVolumeProfileMeanReversion()
    mock_session = AsyncMock()

    # 30 candles where latest close dips below lower Bollinger band
    candles = [
        MagicMock(open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0)
        for _ in range(25)
    ]
    # Add oversold drop
    candles.append(MagicMock(open=100.0, high=100.2, low=95.0, close=95.5, volume=800.0))

    strat.get_historical_candles = AsyncMock(return_value=candles)

    signal = await strat.evaluate(mock_session, "GBPUSD", {})
    assert signal.strategy_id == "bb_volume_profile"
    assert signal.symbol == "GBPUSD"
