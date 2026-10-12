import pytest
from unittest.mock import MagicMock
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult


@pytest.mark.asyncio
async def test_borderline_buffer_guard_wfe_dampening():
    arbitrator = SignalArbitrator()

    # Normal strategy passing standard criteria with borderline WFE (0.60 in [0.55, 0.65])
    quant_signal = {
        "direction": "buy",
        "valid": True,
        "strategy_id": "alpha_donchian_h1",
        "confidence": 0.80,
        "entry_price": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "meta": {
            "size_multiplier": 1.0,
            "wfe": 0.60,
            "sharpe": 1.80,
        },
    }

    result = await arbitrator.arbitrate(
        session=None,
        symbol="EURUSD",
        quant_signal=quant_signal,
        llm_decision=None,
        vix_level=15.0,
    )

    assert result.decision == "buy"
    # Normal risk multiplier is 1.0, but with borderline WFE it should be 1.0 * 0.60 = 0.60
    assert result.risk_multiplier == 0.60
    assert "Borderline Buffer Guard" in result.arbitration_reason
    assert "WFE 0.60 in borderline band [0.55, 0.65]" in result.arbitration_reason
    assert result.meta.get("borderline_buffer_guard", {}).get("applied") is True


@pytest.mark.asyncio
async def test_borderline_buffer_guard_sharpe_dampening():
    arbitrator = SignalArbitrator()

    # Strategy with borderline Sharpe (1.50 in [1.40, 1.60])
    quant_signal = {
        "direction": "sell",
        "valid": True,
        "strategy_id": "alpha_exhaustion_m15",
        "confidence": 0.75,
        "entry_price": 2000.0,
        "stop_loss": 2010.0,
        "take_profit": 1980.0,
        "meta": {
            "size_multiplier": 1.0,
            "wfe": 0.75,
            "sharpe": 1.50,
        },
    }

    result = await arbitrator.arbitrate(
        session=None,
        symbol="XAUUSD",
        quant_signal=quant_signal,
        llm_decision=None,
        vix_level=15.0,
    )

    assert result.decision == "sell"
    assert result.risk_multiplier == 0.60
    assert "Sharpe 1.50 in borderline band [1.40, 1.60]" in result.arbitration_reason


@pytest.mark.asyncio
async def test_borderline_buffer_guard_unaffected_robust_strategy():
    arbitrator = SignalArbitrator()

    # Elite robust strategy: WFE = 0.78 (> 0.65) and Sharpe = 2.10 (> 1.60)
    quant_signal = {
        "direction": "buy",
        "valid": True,
        "strategy_id": "alpha_elite_regime",
        "confidence": 0.85,
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": 52000.0,
        "meta": {
            "size_multiplier": 1.0,
            "wfe": 0.78,
            "sharpe": 2.10,
        },
    }

    result = await arbitrator.arbitrate(
        session=None,
        symbol="BTCUSD",
        quant_signal=quant_signal,
        llm_decision=None,
        vix_level=15.0,
    )

    assert result.decision == "buy"
    assert result.risk_multiplier == 1.0
    assert "Borderline Buffer Guard" not in result.arbitration_reason
    assert "borderline_buffer_guard" not in result.meta
