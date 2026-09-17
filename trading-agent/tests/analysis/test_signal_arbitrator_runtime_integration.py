"""
Unit Tests for SignalArbitrator Runtime Parameter Passing & Decision Source Handling.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from analysis.arbitration.signal_arbitrator import SignalArbitrator
from analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_signal_arbitrator_with_vix_and_regime():
    """Verify SignalArbitrator handles high VIX (>25) and ranging market conflict gracefully."""
    arbitrator = SignalArbitrator(settings={"arbitration": {"high_vol_vix_threshold": 25.0}})
    
    mock_session = AsyncMock()
    sig = EdgeSignal(
        strategy_id="donchian_breakout",
        symbol="BTCUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
        rationale="Donchian upper channel breakout"
    )

    llm_decision = {
        "decision": "sell",
        "confidence": 0.70,
        "risk_multiplier": 1.0,
        "decision_source": "llm_stage2"
    }

    # Scenario: Conflict (Quant BUY vs LLM SELL) in high VIX and ranging regime
    res = await arbitrator.arbitrate(
        session=mock_session,
        symbol="BTCUSD",
        quant_signal=sig,
        llm_decision=llm_decision,
        vix_level=28.5,  # High VIX
        regime_info={"regime": "ranging"}
    )

    # When in conflict in ranging regime, system suppresses safely (conflict suppression)
    assert res.decision == "avoid"
    assert res.selected_source in ("conflict_suppression", "defensive_override")


@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_boost_runtime():
    """Verify SignalArbitrator boosts confidence when Quant and LLM agree."""
    arbitrator = SignalArbitrator(settings={})
    
    mock_session = AsyncMock()
    sig = EdgeSignal(
        strategy_id="donchian_breakout",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        rationale="Donchian upper channel breakout"
    )

    llm_decision = {
        "decision": "buy",
        "confidence": 0.80,
        "risk_multiplier": 1.0,
        "decision_source": "llm_debate"
    }

    from unittest.mock import patch
    with patch("utils.calibration.confidence_calibrator.get_calibrated_confidence", AsyncMock(return_value=0.80)):
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="EURUSD",
            quant_signal=sig,
            llm_decision=llm_decision,
            vix_level=14.0,
            regime_info={"regime": "trending_bullish"}
        )

        assert res.decision == "buy"
        assert res.confidence >= 0.80  # Boosted
        assert res.risk_multiplier >= 1.0


@pytest.mark.asyncio
async def test_signal_arbitrator_single_quant_signal_normal_vix():
    """Verify single quant signal approved with normal VIX (<=25)."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = AsyncMock()

    sig = EdgeSignal(
        strategy_id="donchian_breakout",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        meta={"size_multiplier": 1.0}
    )

    res = await arbitrator.arbitrate(
        session=mock_session,
        symbol="EURUSD",
        quant_signal=sig,
        llm_decision=None,
        vix_level=16.0
    )

    assert res.decision == "buy"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 1.0
    assert res.arbitration_reason == "Quant donchian_breakout single signal approved"
    assert res.meta.get("strategy_id") == "donchian_breakout"


@pytest.mark.asyncio
async def test_signal_arbitrator_single_quant_signal_high_vix():
    """Verify single quant signal approved with high VIX (>25) gets 0.5x penalty."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = AsyncMock()

    sig = EdgeSignal(
        strategy_id="bollinger_reversion",
        symbol="BTCUSD",
        direction="sell",
        valid=True,
        confidence=0.80,
        entry_price=65000.0,
        stop_loss=66000.0,
        take_profit=63000.0,
        meta={"size_multiplier": 1.0}
    )

    res = await arbitrator.arbitrate(
        session=mock_session,
        symbol="BTCUSD",
        quant_signal=sig,
        llm_decision=None,
        vix_level=28.5
    )

    assert res.decision == "sell"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 0.5
    assert "penalty applied: 0.5x" in res.arbitration_reason
    assert res.meta.get("strategy_id") == "bollinger_reversion"


@pytest.mark.asyncio
async def test_signal_arbitrator_quant_signal_dict_and_duck_typing():
    """Verify quant_signal passed as dict or object without strategy_id handles gracefully without AttributeError."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = AsyncMock()

    # Case A: Dict with strategy_id
    dict_sig = {
        "strategy_id": "dict_trend",
        "direction": "buy",
        "valid": True,
        "confidence": 0.72,
        "meta": {"size_multiplier": 1.0}
    }
    res_dict = await arbitrator.arbitrate(
        session=mock_session,
        symbol="GBPUSD",
        quant_signal=dict_sig,
        llm_decision=None,
        vix_level=15.0
    )
    assert res_dict.decision == "buy"
    assert res_dict.selected_source == "quant"
    assert res_dict.meta.get("strategy_id") == "dict_trend"
    assert "Quant dict_trend single signal approved" in res_dict.arbitration_reason

    # Case B: Object without strategy_id (duck-typing fallback to 'unknown')
    class DuckSignal:
        direction = "buy"
        valid = True
        confidence = 0.70

    res_duck = await arbitrator.arbitrate(
        session=mock_session,
        symbol="GBPUSD",
        quant_signal=DuckSignal(),
        llm_decision=None,
        vix_level=15.0
    )
    assert res_duck.decision == "buy"
    assert res_duck.selected_source == "quant"
    assert res_duck.meta.get("strategy_id") == "unknown"
    assert "Quant unknown single signal approved" in res_duck.arbitration_reason

