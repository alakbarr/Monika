import pytest
import asyncio
from datetime import datetime, timezone
from backtest.time_machine import TimeMachine, get_virtual_now, is_backtest_mode

@pytest.mark.asyncio
async def test_time_machine_context():
    dt = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    assert is_backtest_mode() is False
    # Outside context, get_virtual_now returns actual now. It should be > 2023.
    assert get_virtual_now() > dt

    async with TimeMachine(dt):
        assert is_backtest_mode() is True
        assert get_virtual_now() == dt
        
        # Test nested or consecutive logic if needed
        dt2 = datetime(2023, 1, 2, 12, 0, tzinfo=timezone.utc)
        async with TimeMachine(dt2):
            assert get_virtual_now() == dt2
            
        assert get_virtual_now() == dt

    assert is_backtest_mode() is False
    assert get_virtual_now() > dt
