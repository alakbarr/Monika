import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from analysis.memory.alpha_calculator import AlphaCalculator

@pytest.mark.asyncio
async def test_alpha_calculator_flat():
    session = AsyncMock()
    calc = AlphaCalculator(session)
    
    entry_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    exit_time = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    # BTCUSD uses FLAT
    res = await calc.calculate_alpha("BTCUSD", "BUY", entry_time, exit_time, 5.0)
    assert res['benchmark_name'] == 'FLAT'
    assert res['benchmark_return'] == 0.0
    assert res['alpha_return'] == 5.0

@pytest.mark.asyncio
async def test_alpha_calculator_dxy_inverse_buy():
    session = AsyncMock()
    calc = AlphaCalculator(session)
    
    # Mocking get_benchmark_return to return 1.0 (DXY goes up 1%)
    calc.get_benchmark_return = AsyncMock(return_value=1.0)
    
    entry_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    exit_time = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    # EURUSD uses DXY with -1 multiplier
    # BUY direction = 1 multiplier
    # Asset return = -2.0%
    # Eff benchmark return = 1.0 * (-1.0) * 1.0 = -1.0%
    # Alpha = (-2.0) - (-1.0) = -1.0%
    res = await calc.calculate_alpha("EURUSD", "BUY", entry_time, exit_time, -2.0)
    
    assert res['benchmark_name'] == 'DXY'
    assert res['benchmark_return'] == -1.0
    assert res['alpha_return'] == -1.0

@pytest.mark.asyncio
async def test_alpha_calculator_dxy_inverse_sell():
    session = AsyncMock()
    calc = AlphaCalculator(session)
    
    calc.get_benchmark_return = AsyncMock(return_value=1.0)
    
    entry_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    exit_time = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    # EURUSD uses DXY with -1 multiplier
    # SELL direction = -1 multiplier
    # Asset return (PnL) = 3.0% (profit)
    # Eff benchmark return = 1.0 * (-1.0) * (-1.0) = +1.0%
    # Alpha = 3.0 - 1.0 = 2.0%
    res = await calc.calculate_alpha("EURUSD", "SELL", entry_time, exit_time, 3.0)
    
    assert res['benchmark_name'] == 'DXY'
    assert res['benchmark_return'] == 1.0
    assert res['alpha_return'] == 2.0

@pytest.mark.asyncio
async def test_alpha_calculator_dxy_positive_buy():
    session = AsyncMock()
    calc = AlphaCalculator(session)
    
    calc.get_benchmark_return = AsyncMock(return_value=1.0)
    
    entry_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
    exit_time = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    # USDJPY uses DXY with +1 multiplier
    # BUY direction = +1
    res = await calc.calculate_alpha("USDJPY", "BUY", entry_time, exit_time, 2.0)
    
    assert res['benchmark_name'] == 'DXY'
    assert res['benchmark_return'] == 1.0
    assert res['alpha_return'] == 1.0
