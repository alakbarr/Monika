import pytest
from unittest.mock import AsyncMock, patch
from analysis.strategies.pretrade_gate import evaluate_pretrade_gate

@pytest.mark.asyncio
async def test_pretrade_gate():
    session = AsyncMock()
    settings = {'trading': {'edge_strategy': {'min_adx_for_trend': 20}}}
    
    with patch('analysis.strategies.pretrade_gate.compute_bollinger_donchian_chop', new_callable=AsyncMock) as mock_chop, \
         patch('analysis.strategies.pretrade_gate.compute_volume_profile', new_callable=AsyncMock) as mock_vp, \
         patch('analysis.strategies.pretrade_gate.classify_market_regime', new_callable=AsyncMock) as mock_regime:
        
        # Chop blocks trend
        mock_chop.return_value = {'chop_block': True, 'reason': 'choppy'}
        allowed, reason = await evaluate_pretrade_gate(session, 'EURUSD', settings, 'trend')
        assert not allowed
        assert 'chop_block' in reason
        
        # Clear chop, check VP
        mock_chop.return_value = {'chop_block': False}
        mock_vp.return_value = {'regime': 'imbalanced'}
        allowed, reason = await evaluate_pretrade_gate(session, 'EURUSD', settings, 'mean_reversion')
        assert not allowed
        assert 'imbalanced volume regime blocks mean-reversion' in reason
        
        mock_vp.return_value = {'regime': 'balanced'}
        allowed, reason = await evaluate_pretrade_gate(session, 'EURUSD', settings, 'trend')
        assert not allowed
        assert 'balanced volume regime blocks pure trend-following' in reason
