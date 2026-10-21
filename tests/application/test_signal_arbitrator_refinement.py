"""Unit and integration tests for refined SignalArbitrator concordant logic."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator


@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_flat_risk_multiplier():
    """Verify concordant agreement defaults to flat 1.0 risk multiplier instead of overleveraging."""
    arbitrator = SignalArbitrator(settings={})
    assert arbitrator.arbitration_cfg.get("concordant_risk_multiplier", 1.0) == 1.0

    quant_sig = MagicMock(
        symbol="EURUSD",
        direction="buy",
        confidence=0.80,
        strategy_id="tokyo_open_sweep",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        meta={"atr": 0.0020},
    )
    llm_dec = {
        "decision": "buy",
        "confidence": 0.75,
        "entry_price": 1.1000,
        "stop_loss": 1.0960,
        "take_profit": 1.1100,
        "risk_multiplier": 1.0,
    }

    mock_session = MagicMock()
    with patch(
        "monika.core.calibration.confidence_calibrator.get_calibrated_confidence", new_callable=AsyncMock
    ) as mock_cal:
        mock_cal.return_value = 0.75
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="EURUSD",
            quant_signal=quant_sig,
            llm_decision=llm_dec,
            market_regime="trending_bullish",
        )

        assert res.decision == "buy"
        assert res.selected_source == "concordant"
        assert res.risk_multiplier == 1.0


@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_preserves_llm_structural_levels_with_buffer():
    """Verify decisive LLM maintains structural levels and receives ATR buffer."""
    arbitrator = SignalArbitrator(
        settings={"trading": {"arbitration": {"concordant_risk_multiplier": 1.0, "enforce_structural_buffer": True}}}
    )

    quant_sig = MagicMock(
        symbol="GBPUSD",
        direction="sell",
        confidence=0.85,
        strategy_id="london_breakout",
        entry_price=1.3200,
        stop_loss=1.3230,  # Narrow quant SL (dist 0.0030)
        take_profit=1.3100,
        meta={"atr": 0.0020},
    )
    llm_dec = {
        "decision": "sell",
        "confidence": 0.82,
        "entry_price": 1.3200,
        "stop_loss": 1.3250,  # Major structural swing high
        "take_profit": 1.3080,
        "risk_multiplier": 1.0,
    }

    mock_session = MagicMock()
    with patch(
        "monika.core.calibration.confidence_calibrator.get_calibrated_confidence", new_callable=AsyncMock
    ) as mock_cal:
        mock_cal.return_value = 0.82
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="GBPUSD",
            quant_signal=quant_sig,
            llm_decision=llm_dec,
            market_regime="trending_bearish",
        )

        assert res.decision == "sell"
        assert res.selected_source == "concordant"
        assert res.meta.get("level_source") == "llm"
        # SL must be at least the LLM's structural high + FX buffer (0.0020 * 0.35 = 0.0007)
        assert res.stop_loss >= 1.32570
        assert res.stop_loss > res.entry_price
        assert res.take_profit < res.entry_price
