import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal, PROMOTED_EMPIRICAL_STRATEGIES
from monika.application.analysis.strategies.liquidity_sweep_edge import LiquiditySweepStructuralShift


def test_liquidity_sweep_pruned_symbols():
    """Verify GBPUSD and XAUUSD are pruned from liquidity_sweep to prevent empirical alpha decay."""
    strat = LiquiditySweepStructuralShift()
    assert "GBPUSD" not in strat.applicable_symbols
    assert "XAUUSD" not in strat.applicable_symbols
    assert strat.applicable_symbols == {"EURUSD", "USDJPY", "AUDUSD"}
    assert not strat.is_enabled("GBPUSD")
    assert not strat.is_enabled("XAUUSD")
    assert strat.is_enabled("USDJPY")
    assert strat.is_enabled("EURUSD")
    assert strat.is_enabled("AUDUSD")


def test_promoted_empirical_strategies_invariants():
    """Verify all 9 empirical institutional alphas remain promoted."""
    expected = {
        "tokyo_open_sweep",
        "liquidity_sweep",
        "smt_divergence",
        "bb_volume_profile",
        "vwap_mean_reversion",
        "usdjpy_atr_exhaustion",
        "xtiusd_atr_exhaustion",
        "btcusd_dynamic_donchian",
        "tsm_momentum",
    }
    assert expected.issubset(PROMOTED_EMPIRICAL_STRATEGIES)


@pytest.mark.asyncio
async def test_promoted_strategy_degridlocking_on_llm_wait():
    """
    Verify promoted quant strategy executes when LLM is in 'wait' stance
    and TimesFM is neutral (skew = 0.0), breaking the 93.5% wait deadlock.
    """
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"quant_priority_risk_multiplier": 0.70}}}
    )

    quant_signal = EdgeSignal(
        strategy_id="tokyo_open_sweep",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": False},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "No catalyst present, waiting for London open.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": 0.0}

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "buy"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 0.70
    assert "Promoted quant signal tokyo_open_sweep executed" in res.arbitration_reason


@pytest.mark.asyncio
async def test_promoted_strategy_suppressed_when_timesfm_opposes():
    """Verify promoted quant signal is safely suppressed if TimesFM actively opposes direction."""
    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})

    quant_signal = EdgeSignal(
        strategy_id="tokyo_open_sweep",
        symbol="USDJPY",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=150.0,
        stop_loss=149.5,
        take_profit=151.0,
        meta={"is_incubating": False},
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "Waiting for direction.",
    }

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = None
    nested_ctx.__aexit__.return_value = None
    session_mock.begin_nested = MagicMock(return_value=nested_ctx)

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
    ) as mock_tfm:
        mock_tfm.return_value = {"quantile_skew": -0.25}  # Opposes BUY

        res = await arbitrator.arbitrate(
            session=session_mock,
            symbol="USDJPY",
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            regime_info={"regime": "ranging"},
        )

    assert res.decision == "wait"
    assert res.risk_multiplier == 0.0
    assert "contradicts TimesFM skew" in res.arbitration_reason
