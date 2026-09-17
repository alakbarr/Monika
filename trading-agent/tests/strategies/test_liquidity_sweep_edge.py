import pytest
from unittest.mock import AsyncMock, patch
from analysis.strategies.liquidity_sweep_edge import LiquiditySweepStructuralShift

@pytest.mark.asyncio
async def test_liquidity_sweep_edge():
    settings = {'trading': {'edge_strategy': {'liquidity_sweep': {'enabled': True, 'require_volume_confirmation': True}}}}
    strategy = LiquiditySweepStructuralShift(settings)
    session = AsyncMock()
    
    with patch('analysis.strategies.liquidity_sweep_edge.detect_liquidity_sweep', new_callable=AsyncMock) as mock_detect:
        # 1. Reject if no structure
        mock_detect.return_value = {'structure_confirmed': False, 'reasons': ['no structure']}
        sig = await strategy.evaluate(session, 'EURUSD', settings)
        assert not sig.valid
        
        # 2. Reject if require volume but not confirmed
        mock_detect.return_value = {'structure_confirmed': True, 'volume_confirmed': False, 'valid_for_direction': 'buy', 'reasons': []}
        sig = await strategy.evaluate(session, 'EURUSD', settings)
        assert not sig.valid
        assert "volume not confirmed" in sig.rationale
        
        # 3. Accept if structure and volume
        mock_detect.return_value = {'structure_confirmed': True, 'volume_confirmed': True, 'valid_for_direction': 'buy', 'reasons': ['ok']}
        sig = await strategy.evaluate(session, 'EURUSD', settings)
        assert sig.valid
        assert sig.direction == 'buy'
