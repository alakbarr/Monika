import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult

@pytest.mark.asyncio
async def test_signal_arbitrator_bayesian_pooling_concordant():
    settings = {
        "trading": {
            "signal_arbitration": {
                "enabled": True,
                "concordant_boost_conf": 0.05,
                "concordant_risk_multiplier": 1.20,
                "max_risk_multiplier": 1.30,
                "quant_priority_risk_multiplier": 0.70,
                "min_quant_confidence_for_trend_override": 0.75,
                "vix_defensive_override_threshold": 25.0,
                "empirical_joint_pooling": True
            }
        }
    }
    
    arbitrator = SignalArbitrator(settings)
    
    quant_signal = MagicMock(
        direction="buy",
        confidence=0.80,
        strategy_id="trend_trailing",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100
    )
    
    llm_decision = {
        "decision": "buy",
        "confidence": 0.85,
        "entry_price": 1.1005,
        "stop_loss": 1.0955,
        "take_profit": 1.1120,
        "risk_multiplier": 1.0
    }
    
    session = AsyncMock()
    
    # Mock confidence calibrator to return raw score
    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", side_effect=lambda s, c: c):
        res = await arbitrator.arbitrate(
            session=session,
            symbol="EURUSD",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            vix_level=16.0,
            regime_info={"regime": "trend"}
        )
        
        assert res.decision == "buy"
        assert res.selected_source == "concordant"
        # Calibrated Linear Opinion pool of 0.80 and 0.85 + boost produces >= 0.85
        assert res.confidence >= 0.85
        assert res.risk_multiplier == 1.20

@pytest.mark.asyncio
async def test_signal_arbitrator_vix_defensive_override():
    settings = {
        "trading": {
            "signal_arbitration": {
                "vix_defensive_override_threshold": 35.0
            }
        }
    }
    arbitrator = SignalArbitrator(settings)
    
    quant_signal = MagicMock(direction="buy", confidence=0.80, strategy_id="trend")
    llm_decision = {"decision": "sell", "confidence": 0.70}
    
    # Extreme VIX >= 35.0 triggers defensive override
    res = await arbitrator.arbitrate(
        session=None,
        symbol="EURUSD",
        quant_signal=quant_signal,
        llm_decision=llm_decision,
        vix_level=36.0,
        regime_info={"regime": "trend"}
    )
    
    assert res.decision == "avoid"
    assert res.selected_source == "defensive_override"
