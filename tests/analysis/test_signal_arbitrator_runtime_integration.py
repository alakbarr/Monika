"""
Unit Tests for SignalArbitrator Runtime Parameter Passing & Decision Source Handling.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from tests.conftest import create_mock_async_session
from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal


@pytest.mark.asyncio
async def test_signal_arbitrator_with_vix_and_regime():
    """Verify SignalArbitrator handles high VIX (>25) and ranging market conflict gracefully."""
    arbitrator = SignalArbitrator(settings={"arbitration": {"high_vol_vix_threshold": 25.0}})

    mock_session = create_mock_async_session()
    sig = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="BTCUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
        rationale="TSM momentum breakout",
    )

    llm_decision = {"decision": "sell", "confidence": 0.70, "risk_multiplier": 1.0, "decision_source": "llm_stage2"}

    # Scenario: Conflict (Quant BUY vs LLM SELL) in high VIX and ranging regime
    res = await arbitrator.arbitrate(
        session=mock_session,
        symbol="BTCUSD",
        quant_signal=sig,
        llm_decision=llm_decision,
        vix_level=28.5,  # High VIX
        regime_info={"regime": "ranging"},
    )

    # When in conflict in ranging regime, system suppresses safely (conflict suppression)
    assert res.decision == "avoid"
    assert res.selected_source in ("conflict_suppression", "defensive_override")


@pytest.mark.asyncio
async def test_signal_arbitrator_concordant_boost_runtime():
    """Verify SignalArbitrator boosts confidence when Quant and LLM agree."""
    arbitrator = SignalArbitrator(settings={})

    mock_session = create_mock_async_session()
    sig = EdgeSignal(
        strategy_id="donchian_breakout",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        rationale="Donchian upper channel breakout",
    )

    llm_decision = {"decision": "buy", "confidence": 0.80, "risk_multiplier": 1.0, "decision_source": "llm_debate"}

    from unittest.mock import patch

    with patch("monika.core.calibration.confidence_calibrator.get_calibrated_confidence", AsyncMock(return_value=0.80)):
        res = await arbitrator.arbitrate(
            session=mock_session,
            symbol="EURUSD",
            quant_signal=sig,
            llm_decision=llm_decision,
            vix_level=14.0,
            regime_info={"regime": "trending_bullish"},
        )

        assert res.decision == "buy"
        assert res.confidence >= 0.80  # Boosted
        assert res.risk_multiplier >= 1.0


@pytest.mark.asyncio
async def test_signal_arbitrator_single_quant_signal_normal_vix():
    """Verify single quant signal approved with normal VIX (<=25)."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = create_mock_async_session()

    sig = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        meta={"size_multiplier": 1.0},
    )

    res = await arbitrator.arbitrate(
        session=mock_session, symbol="EURUSD", quant_signal=sig, llm_decision=None, vix_level=16.0
    )

    assert res.decision == "buy"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 1.0
    assert res.arbitration_reason == "Quant tsm_momentum single signal approved"
    assert res.meta.get("strategy_id") == "tsm_momentum"


@pytest.mark.asyncio
async def test_signal_arbitrator_single_quant_signal_high_vix():
    """Verify single quant signal approved with high VIX (>25) gets 0.5x penalty."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = create_mock_async_session()

    sig = EdgeSignal(
        strategy_id="bb_volume_profile",
        symbol="BTCUSD",
        direction="sell",
        valid=True,
        confidence=0.80,
        entry_price=65000.0,
        stop_loss=66000.0,
        take_profit=63000.0,
        meta={"size_multiplier": 1.0},
    )

    res = await arbitrator.arbitrate(
        session=mock_session, symbol="BTCUSD", quant_signal=sig, llm_decision=None, vix_level=28.5
    )

    assert res.decision == "sell"
    assert res.selected_source == "quant"
    assert res.risk_multiplier == 0.5
    assert "penalty applied: 0.5x" in res.arbitration_reason
    assert res.meta.get("strategy_id") == "bb_volume_profile"


@pytest.mark.asyncio
async def test_signal_arbitrator_quant_signal_dict_and_duck_typing():
    """Verify quant_signal passed as dict or object without strategy_id handles gracefully without AttributeError."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = create_mock_async_session()

    # Case A: Dict with strategy_id
    dict_sig = {
        "strategy_id": "dict_trend",
        "direction": "buy",
        "valid": True,
        "confidence": 0.72,
        "meta": {"size_multiplier": 1.0},
    }
    res_dict = await arbitrator.arbitrate(
        session=mock_session, symbol="GBPUSD", quant_signal=dict_sig, llm_decision=None, vix_level=15.0
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
        session=mock_session, symbol="GBPUSD", quant_signal=DuckSignal(), llm_decision=None, vix_level=15.0
    )
    assert res_duck.decision == "buy"
    assert res_duck.selected_source == "quant"
    assert res_duck.meta.get("strategy_id") == "unknown"
    assert "Quant unknown single signal approved" in res_duck.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_llm_error_fails_closed():
    """Verify SignalArbitrator fails closed to AVOID when LLM returned error/invalid state."""
    arbitrator = SignalArbitrator(settings={})
    mock_session = create_mock_async_session()

    quant_sig = EdgeSignal(
        strategy_id="donchian_breakout",
        symbol="BTCUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
    )

    # Case 1: LLM decision is "error"
    llm_error_decision = {
        "decision": "error",
        "confidence": 0.0,
        "risk_multiplier": 0.0,
        "rationale": "LLM API timeout / hallucination guard failed",
    }

    res = await arbitrator.arbitrate(
        session=mock_session,
        symbol="BTCUSD",
        quant_signal=quant_sig,
        llm_decision=llm_error_decision,
        vix_level=16.0,
        regime_info={"regime": "trend"},
    )

    assert res.decision == "avoid"
    assert res.risk_multiplier == 0.0
    assert res.selected_source == "fail_closed_llm_error"
    assert "Fail-closed: LLM analysis returned 'error'" in res.arbitration_reason
    assert res.conflict_detected is True

    # Case 2: LLM decision is random unparseable string
    llm_bad_decision = {"decision": "invalid_direction", "confidence": 0.5}
    res_bad = await arbitrator.arbitrate(
        session=mock_session,
        symbol="BTCUSD",
        quant_signal=quant_sig,
        llm_decision=llm_bad_decision,
        vix_level=16.0,
    )
    assert res_bad.decision == "avoid"
    assert res_bad.risk_multiplier == 0.0
    assert res_bad.selected_source == "fail_closed_llm_error"


@pytest.mark.asyncio
async def test_quant_arbitration_skips_error_analyses_and_materializes_promoted_asset_analysis(db_session):
    """Verify run_quant_arbitration skips errored Stage 2 analyses and materializes AssetAnalysis for promoted WAIT symbols."""
    from unittest.mock import MagicMock, patch
    from contextlib import asynccontextmanager
    from monika.application.graph.nodes.risk.quant_arbitration import run_quant_arbitration
    from monika.infrastructure.database.models import AssetAnalysis

    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"trading": {}}

    # 1. An errored Stage 2 result: success=False and decision="error"
    # 2. A normal Stage 2 result in WAIT state that will be evaluated for quant promotion
    actionable = []
    asset_analyses = {
        "ETHUSD": {
            "symbol": "ETHUSD",
            "decision": "error",
            "success": False,
            "confidence": 0.0,
        },
        "BTCUSD": {
            "symbol": "BTCUSD",
            "decision": "wait",
            "confidence": 0.50,
            "entry_price": 65000.0,
            "stop_loss": 64000.0,
            "take_profit": 68000.0,
            "success": True,
        },
    }
    state = {
        "brief_id": 42,
        "asset_analyses": dict(asset_analyses),
    }

    mock_quant_signal = EdgeSignal(
        strategy_id="btcusd_dynamic_donchian",
        symbol="BTCUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
    )

    with (
        patch("monika.infrastructure.database.db.get_session", mock_session_ctx),
        patch(
            "monika.application.analysis.strategies.registry.StrategyRegistry.evaluate_all",
            AsyncMock(return_value=[mock_quant_signal]),
        ),
        patch("monika.application.analysis.strategies.decay_monitor.get_strategy_decay_monitor") as mock_decay,
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            AsyncMock(return_value={"quantile_skew": 0.25}),
        ),
    ):
        mock_mon = MagicMock()
        mock_mon.is_live_ready.return_value = True
        mock_decay.return_value = mock_mon

        filtered, rejected = await run_quant_arbitration(
            scheduler=mock_scheduler,
            actionable=actionable,
            asset_analyses=asset_analyses,
            state=state,
        )

    # ETHUSD (errored) was completely skipped
    assert not any(sym == "ETHUSD" for sym, _ in filtered)
    assert not any(d.get("symbol") == "ETHUSD" for d in rejected)

    # BTCUSD was promoted to BUY, has analysis_id populated, and was persisted into DB
    assert len(filtered) == 1
    sym, trade = filtered[0]
    assert sym == "BTCUSD"
    assert trade["decision"] == "buy"
    assert trade.get("analysis_id") is not None

    persisted = await db_session.get(AssetAnalysis, trade["analysis_id"])
    assert persisted is not None
    assert persisted.symbol == "BTCUSD"
    assert persisted.decision == "buy"
    assert persisted.brief_id == 42


@pytest.mark.asyncio
async def test_execution_node_missing_analysis_id_graceful(db_session):
    """Verify execution_node fails closed gracefully without KeyError when analysis_id is missing."""
    from unittest.mock import MagicMock, patch
    from contextlib import asynccontextmanager
    from monika.application.graph.nodes.execution_node import execution_node

    @asynccontextmanager
    async def mock_session_ctx():
        yield db_session

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {
        "trading": {
            "auto_execute": True,
            "auto_execute_min_confidence": 0.50,
            "auto_execute_min_confluence": 4,
            "auto_execute_active_hours_utc_start": 0,
            "auto_execute_active_hours_utc_end": 24,
            "symbols": ["EURUSD"],
        }
    }
    mock_scheduler.get_account_equity = AsyncMock(return_value=10000.0)

    # Proposal with missing analysis_id
    actionable_trade = {
        "symbol": "EURUSD",
        "decision": "buy",
        "confidence": 0.80,
        "entry_price": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
    }

    state = {
        "actionable_trades": [("EURUSD", actionable_trade)],
        "summary": {},
    }
    config = {"configurable": {"scheduler": mock_scheduler}}

    with patch("monika.infrastructure.database.db.get_session", mock_session_ctx):
        res = await execution_node(state, config)

    # Should not raise KeyError and execution should reflect skipped/blocked
    summary = res.get("summary", {})
    assert "execution" in summary
    assert summary["execution"].get("executed_count", 0) == 0
