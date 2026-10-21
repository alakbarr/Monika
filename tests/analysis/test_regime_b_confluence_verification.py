import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from monika.application.analysis.calculators.confluence_calculator import calculate_confluence
from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from monika.application.analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_confluence_calculator_regime_b_breakout_verified():
    """Verify that Regime B breakout factors are deterministically verified and awarded."""
    mock_session = AsyncMock()

    # Mock ADR context
    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={
                "target_tp_min_distance": 0.0030,
                "target_tp_max_distance": 0.0080,
                "target_sl_max_distance": 0.0035,
            },
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"structure_confirmed": False},
        ),
    ):
        # Test calculation with explicit Regime B factor claims
        factors = ["breakout_expansion", "volume_expansion", "trend_continuation", "momentum_expansion"]

        # Mock database rows for technical indicators and prices
        class MockRow:
            def __init__(self, val_dict, vol=150.0):
                import json
                from datetime import datetime, timezone

                self.value_json = json.dumps(val_dict)
                self.close = 1.1000
                self.high = 1.1050
                self.low = 1.0950
                self.volume = vol
                self.report_date = None
                self.price_low = 1.0950
                self.price_high = 1.1050
                self.timestamp = datetime.now(timezone.utc)
                self.structured_json = None
                self.direction = "bullish"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MockRow({"value": 1.1000, "atr": 0.0020, "rsi": 62.0})
        # Set first bar volume higher to trigger volume expansion
        h4_bars = [MockRow({"value": 1.1000}, vol=300.0)] + [MockRow({"value": 1.1000}, vol=150.0) for _ in range(9)]
        mock_result.scalars.return_value.all.return_value = h4_bars
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        res = await calculate_confluence(
            session=mock_session,
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1200,  # higher than prior bars
            sl=1.1160,
            tp=1.1280,
            settings={},
            confluence_factors=factors,
        )

        assert "computed_score" in res
        # Score must contain deterministic points for verified breakout factors
        assert res["computed_score"] >= 4


@pytest.mark.asyncio
async def test_signal_arbitrator_neutral_timesfm_preserves_llm_wait():
    """Without TimesFM directional confirmation the LLM wait stance must be preserved."""
    quant_signal = EdgeSignal(
        strategy_id="tokyo_open_sweep",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=155.20,
        stop_loss=154.80,
        take_profit=156.40,
        factor_family="mean_reversion",
    )

    arb = SignalArbitrator(settings={})
    mock_db = MagicMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin_nested.return_value = mock_nested
    res = await arb.arbitrate(
        session=mock_db,
        symbol="USDJPY",
        llm_decision={"decision": "wait", "confidence": 0.50},
        llm_confidence=0.50,
        quant_signal=quant_signal,
        macro_brief=None,
        timesfm_skew=0.0,  # Neutral / offline TimesFM
    )

    assert isinstance(res, ArbitrationResult)
    assert res.decision == "wait", (
        f"Arbitration reason: {res.arbitration_reason}, selected: {res.selected_source}, meta: {res.meta}"
    )
    assert res.risk_multiplier == 0.0
