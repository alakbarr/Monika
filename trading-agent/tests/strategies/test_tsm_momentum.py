import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.strategies.tsm_momentum import TimeSeriesMomentum

@pytest.mark.asyncio
async def test_tsm_momentum_insufficient_history():
    settings = {'trading': {'edge_strategy': {'tsm_momentum': {'enabled': True}}}}
    strategy = TimeSeriesMomentum(settings)
    
    session = AsyncMock()
    # Mocking rows to be empty
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result
    
    sig = await strategy.evaluate(session, 'EURUSD', settings)
    
    assert not sig.valid
    assert "insufficient D1 history" in sig.rationale
