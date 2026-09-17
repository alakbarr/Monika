import pytest
from unittest.mock import AsyncMock, patch
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from analysis.strategies.base_strategy import EdgeSignal

@pytest.mark.asyncio
async def test_signal_arbitrator_volatile_chop_blocked():
    """Verify that when market is in VOLATILE_CHOP and LLM is in wait/avoid stance, quant execution is blocked."""
    settings = {
        "trading": {
            "signal_arbitration": {
                "quant_weight": 0.45,
                "llm_weight": 0.55,
                "empirical_joint_pooling": True,
            }
        }
    }
    arbitrator = SignalArbitrator(settings=settings)
    mock_session = AsyncMock()

    quant_sig = EdgeSignal(
        strategy_id="bb_squeeze_scalp",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        rationale="BB squeeze breakout",
        exit_style="intraday_adr",
        entry_price=1.0850,
        stop_loss=1.0830,
        take_profit=1.0890
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "risk_multiplier": 1.0,
        "rationale": "High volatility chop observed"
    }

    regime_info = {
        "regime": "volatile_chop",
        "market_regime": "volatile_chop",
        "composite_quality": 0.35,
        "volatility_chop": {"chop_block": True}
    }

    result = await arbitrator.arbitrate(
        session=mock_session,
        symbol="EURUSD",
        quant_signal=quant_sig,
        llm_decision=llm_decision,
        vix_level=26.5,
        regime_info=regime_info
    )

    assert isinstance(result, ArbitrationResult)
    assert result.decision == "avoid"
    assert result.confidence == 0.0
    assert result.risk_multiplier == 0.0
    assert result.selected_source == "chop_block_suppression"
    assert "Volatile chop regime detected" in result.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_linear_opinion_pool_concordant():
    """Verify linear opinion pool computes weighted average correctly for concordant signals."""
    settings = {
        "trading": {
            "signal_arbitration": {
                "quant_weight": 0.40,
                "llm_weight": 0.60,
                "concordant_boost_confidence": 0.05,
                "concordant_risk_multiplier": 1.25,
                "max_concordant_risk_multiplier": 1.5,
                "empirical_joint_pooling": True,
            }
        }
    }
    arbitrator = SignalArbitrator(settings=settings)
    mock_session = AsyncMock()

    quant_sig = EdgeSignal(
        strategy_id="xau_trend",
        symbol="XAUUSD",
        direction="buy",
        valid=True,
        confidence=0.80,
        rationale="Strong trend",
        exit_style="trend_trailing",
        entry_price=2650.0,
        stop_loss=2635.0,
        take_profit=2685.0
    )

    llm_decision = {
        "decision": "buy",
        "confidence": 0.70,
        "risk_multiplier": 1.0,
        "entry_price": 2650.0,
        "stop_loss": 2635.0,
        "take_profit": 2685.0,
        "rationale": "Bullish momentum aligned"
    }

    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", AsyncMock(return_value=0.70)):
        result = await arbitrator.arbitrate(
            session=mock_session,
            symbol="XAUUSD",
            quant_signal=quant_sig,
            llm_decision=llm_decision,
            vix_level=17.0,
            regime_info={"regime": "trending_bull", "composite_quality": 0.85}
        )

        # Linear pool: (0.40 * 0.80 + 0.60 * 0.70) = 0.32 + 0.42 = 0.74
        # Boost: + 0.05 -> 0.79
        assert result.decision == "buy"
        assert result.confidence == 0.79
        assert result.risk_multiplier == 1.25
        assert result.selected_source == "concordant"
