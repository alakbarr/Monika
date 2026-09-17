import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.tools.tool_executor import ToolExecutor
from database.models import AssetAnalysis, TradeTrigger

@pytest.mark.asyncio
async def test_mechanical_risk_gate_classification_and_synthetic_trigger():
    settings = {
        "trading": {
            "risk": {"min_rr_ratio": 1.3},
            "edge_strategy": {
                "macro_bias": {"enabled": False},
                "volatility_regime": {"enabled": True}
            }
        }
    }
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    
    # Mock queries inside submit_asset_analysis
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_res)
    
    executor = ToolExecutor(session=mock_session, settings=settings, model_name="test-model")
    
    # Input with BUY decision but triggering a volatility regime gate error
    inp = {
        "symbol": "EURUSD",
        "decision": "buy",
        "confidence": 0.85,
        "rationale": "Bullish SMC setup",
        "confluence_score": 8,
        "confluence_factors": ["order_block"],
        "entry_condition": {"price": 1.0850, "type": "market", "detail": "Order block entry"},
        "priced_in_score": 3,
        "reevaluation_trigger": {"type": "price_level", "price": 1.0850, "direction": "above", "detail": "Re-evaluate if price reaches 1.0850"},
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "invalidation": "H4 break below 1.0790",
        "invalidation_price": 1.0790,
        "invalidation_direction": "below"
    }
    
    # Patch macro bias & volatility regime gate check to return a gate error
    with patch('analysis.calculators.regime_classifier.compute_bollinger_donchian_chop', new_callable=AsyncMock) as mock_chop, \
         patch('analysis.calculators.daily_range_calculator.compute_daily_range_context', new_callable=AsyncMock) as mock_adr, \
         patch('analysis.calculators.confluence_calculator.calculate_confluence', new_callable=AsyncMock) as mock_conf:
        
        mock_chop.return_value = {'chop_block': True, 'reason': 'BB width @ 20th pct (<=25) no breakout'}
        mock_adr.return_value = {'error': 'skip'}
        mock_conf.return_value = {'computed_score': 8}
        
        result = await executor._tool_submit_asset_analysis(inp)
        
        assert result["status"] == "saved"
        assert result["decision"] == "wait"
        
        # Verify that an AssetAnalysis and a TradeTrigger were added to session
        added_objects = [call[0][0] for call in mock_session.add.call_args_list]
        analysis_obj = next((obj for obj in added_objects if isinstance(obj, AssetAnalysis)), None)
        trigger_obj = next((obj for obj in added_objects if isinstance(obj, TradeTrigger)), None)
        
        assert analysis_obj is not None
        assert analysis_obj.decision == "wait"
        assert analysis_obj.confidence == 0.0
        assert "Mechanical Risk Gate" in analysis_obj.rationale
        
        # Verify synthetic trigger was generated
        assert trigger_obj is not None
        assert trigger_obj.trigger_type == "price_level"
        assert trigger_obj.status == "pending"
