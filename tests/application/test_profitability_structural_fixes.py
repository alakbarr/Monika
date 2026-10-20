import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal
from monika.domain.risk.evaluators.execution_checks import RiskExecutionChecksMixin, DEFAULT_SYMBOL_MAX_SPREAD_POINTS
from monika.application.analysis.tools.executor import FACTOR_POINT_MAP


def create_mock_session():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res
    session.begin_nested = MagicMock()
    session.add = MagicMock()
    return session


def test_bonus_confluence_factors_registered_in_factor_point_map():
    """Verify bonus confluence factors are correctly in FACTOR_POINT_MAP with point 1."""
    assert FACTOR_POINT_MAP.get("quant_strategy_edge") == 1
    assert FACTOR_POINT_MAP.get("rr_ratio_bonus") == 1
    assert FACTOR_POINT_MAP.get("adr_target_bonus") == 1


@pytest.mark.asyncio
async def test_signal_arbitrator_suppresses_counter_trend_mean_reversion():
    """Verify that a synthesized alpha with mean_reversion tags is blocked during strong trend."""
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"min_quant_confidence_for_trend_override": 0.70}}}
    )

    # Synthesized alpha that attempts to fade a strong trend
    mean_rev_signal = EdgeSignal(
        strategy_id="alpha_gbpusd_867953",
        symbol="GBPUSD",
        direction="sell",
        valid=True,
        confidence=0.85,
        entry_price=1.2850,
        stop_loss=1.2900,
        take_profit=1.2750,
        tags=["atr_exhaustion", "mean_reversion", "bearish_reversal"],
    )

    # Market is in a strong bullish trend, LLM is waiting
    session = create_mock_session()
    result = await arbitrator.arbitrate(
        session=session,
        symbol="GBPUSD",
        quant_signal=mean_rev_signal,
        llm_decision={"decision": "wait", "confidence": 0.5},
        regime_info={"regime": "trending_bullish"},
    )

    assert result.decision == "wait"
    assert result.selected_source == "regime_protection"
    assert "Counter-trend mean reversion is prohibited" in result.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_allows_genuine_trend_alpha_in_trend():
    """Verify that a genuine graduated trend-following alpha is prioritized during trend."""
    from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

    decay_mon = get_strategy_decay_monitor()
    decay_mon.get_health("tsm_momentum").is_incubation_passed = True

    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"min_quant_confidence_for_trend_override": 0.70}}}
    )

    trend_signal = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="XTIUSD",
        direction="buy",
        valid=True,
        confidence=0.88,
        entry_price=94.20,
        stop_loss=92.70,
        take_profit=96.72,
        tags=["volume_expansion", "donchian_breakout", "bullish_momentum"],
    )

    session = create_mock_session()
    result = await arbitrator.arbitrate(
        session=session,
        symbol="XTIUSD",
        quant_signal=trend_signal,
        llm_decision={"decision": "wait", "confidence": 0.4},
        regime_info={"regime": "strong_trend"},
    )

    assert result.decision == "buy"
    assert result.selected_source == "quant"


@pytest.mark.asyncio
async def test_crypto_spread_resolution_in_risk_gate():
    """Verify that BTCUSD 1965 points spread is accepted under default points and relative spread."""
    checker = RiskExecutionChecksMixin()
    checker.settings = {"trading": {"risk": {}}}

    mock_mt5 = AsyncMock()
    mock_mt5.is_connected = AsyncMock(return_value=True)
    # BTCUSD spread: 1965 points ($19.65 at point 0.01), price $81,200 (spread pct = 0.024% <= 0.05%)
    mock_mt5.get_spread = AsyncMock(
        return_value={
            "spread_points": 1965,
            "spread_cost": 19.65,
            "bid": 81200.0,
            "ask": 81219.65,
        }
    )
    checker._mt5 = mock_mt5

    passed, reason = await checker._check_max_spread(session=None, symbol="BTCUSD")
    assert passed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_crypto_spread_breach_in_risk_gate():
    """Verify that an exorbitant spread (e.g. 5000 points and 1% spread cost) is rejected."""
    checker = RiskExecutionChecksMixin()
    checker.settings = {"trading": {"risk": {}}}

    mock_mt5 = AsyncMock()
    mock_mt5.is_connected = AsyncMock(return_value=True)
    mock_mt5.get_spread = AsyncMock(
        return_value={
            "spread_points": 5000,
            "spread_cost": 500.0,
            "bid": 50000.0,
            "ask": 50500.0,
        }
    )
    checker._mt5 = mock_mt5

    passed, reason = await checker._check_max_spread(session=None, symbol="BTCUSD")
    assert passed is False
    assert "exceeds maximum allowed 3500.0 pts" in reason


@pytest.mark.asyncio
async def test_timesfm_mock_forecast_in_backtest_session():
    """Verify that ZeroLookaheadSliceSession returns MockTimesFMForecastRow without CandleDict parse errors."""
    from monika.application.backtest.isolated_strategy_harness import ZeroLookaheadSliceSession, CandleDict
    from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

    candle = CandleDict(
        {"time": datetime.now(timezone.utc), "open": 1.12, "high": 1.13, "low": 1.11, "close": 1.125, "volume": 100}
    )
    session = ZeroLookaheadSliceSession(
        candle_cache={("EURUSD", "H1"): [candle]},
        as_of_time=datetime.now(timezone.utc),
        symbol="EURUSD",
    )

    engine = TimesFMEngine({})
    forecast = await engine.get_latest_forecast(session, "EURUSD", timeframe="H1")
    assert forecast is not None
    assert "quantiles" in forecast
    assert forecast["symbol"] == "EURUSD"
    assert "Q50" in forecast["quantiles"]


def test_donchian_breakout_applicable_symbols_restricted_to_crypto():
    """Verify that BTCDonchianBreakout and DonchianBreakoutStrategy are restricted to crypto only."""
    from monika.application.analysis.strategies.btc_donchian_breakout import (
        BTCDonchianBreakout,
        DonchianBreakoutStrategy,
    )

    assert BTCDonchianBreakout.applicable_symbols == {"BTCUSD", "ETHUSD", "SOLUSD"}
    assert DonchianBreakoutStrategy.applicable_symbols == {"BTCUSD", "ETHUSD", "SOLUSD"}
    assert "EURUSD" not in BTCDonchianBreakout.applicable_symbols


@pytest.mark.asyncio
async def test_smc_fvg_and_btc_donchian_quarantined_from_trading():
    """Verify that smc_fvg and btc_donchian_breakout are in QUARANTINED_STRATEGY_IDS and suppressed."""
    from monika.application.analysis.strategies.decay_monitor import (
        CORE_STRATEGY_IDS,
        QUARANTINED_STRATEGY_IDS,
        get_strategy_decay_monitor,
    )
    from monika.application.analysis.strategies.registry import StrategyRegistry

    assert "smc_fvg" not in CORE_STRATEGY_IDS
    assert "btc_donchian_breakout" not in CORE_STRATEGY_IDS
    assert "tsm_momentum" in CORE_STRATEGY_IDS

    assert "smc_fvg" in QUARANTINED_STRATEGY_IDS
    assert "btc_donchian_breakout" in QUARANTINED_STRATEGY_IDS
    assert "smc_fvg" in StrategyRegistry.QUARANTINED_STRATEGY_IDS
    assert "btc_donchian_breakout" in StrategyRegistry.QUARANTINED_STRATEGY_IDS

    monitor = get_strategy_decay_monitor()
    assert monitor.is_tradeable("smc_fvg") is False
    assert monitor.is_live_ready("smc_fvg") is False
    assert monitor.is_tradeable("btc_donchian_breakout") is False
    assert monitor.is_live_ready("btc_donchian_breakout") is False
    assert monitor.is_tradeable("tsm_momentum") is True

    session = create_mock_session()
    signals = await StrategyRegistry.evaluate_all(session=session, symbol="BTCUSD", settings={})
    emitted_strat_ids = {s.strategy_id for s in signals}
    assert "btc_donchian_breakout" not in emitted_strat_ids
    assert "smc_fvg" not in emitted_strat_ids


@pytest.mark.asyncio
async def test_signal_arbitrator_blocks_incubating_alpha_override_on_llm_wait():
    """Verify that an incubating strategy (not graduated) CANNOT override LLM wait stance."""
    from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

    decay_mon = get_strategy_decay_monitor()
    decay_mon.get_health("alpha_unincubated").is_incubation_passed = False

    arbitrator = SignalArbitrator(settings={})
    incubating_sig = EdgeSignal(
        strategy_id="alpha_unincubated",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.3000,
        stop_loss=1.2950,
        take_profit=1.3100,
    )

    session = create_mock_session()
    result = await arbitrator.arbitrate(
        session=session,
        symbol="GBPUSD",
        quant_signal=incubating_sig,
        llm_decision={"decision": "wait", "confidence": 0.5},
        regime_info={"regime": "trending_bullish"},
    )

    assert result.decision == "wait"
    assert result.selected_source == "llm"
    assert "incubating" in result.arbitration_reason


@pytest.mark.asyncio
async def test_risk_gate_rejects_inverted_buy_geometry():
    """Verify that TradeProposal and RiskGate strictly reject any BUY order where Stop Loss >= Entry Price."""
    from monika.domain.risk.risk_gate import RiskGate
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.trade_proposal import TradeProposal

    # 1. Proposal schema level: Must raise ValueError at boundary
    with pytest.raises(ValueError, match="BUY geometry violation"):
        TradeProposal(
            symbol="BTCUSD",
            direction="BUY",
            entry_price=82108.7,
            stop_loss=82203.4,
            take_profit=84000.0,
            lot_size=0.1,
        )

    # 2. RiskGate evaluation level: Sizing with inverted levels must be rejected
    risk_gate = RiskGate(settings={"trading": {"risk": {}}})
    session = create_mock_session()

    inverted_sizing = SizingResult(
        symbol="BTCUSD",
        direction="buy",
        entry_price=82108.7,
        stop_loss=82203.4,
        take_profit=84000.0,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=94.7,
        sl_distance_pips=947.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
    )

    verdict = await risk_gate.evaluate(session, "BTCUSD", "buy", sizing=inverted_sizing, account_equity=10000.0)
    assert verdict.approved is False
    assert any("BUY geometry violation" in r for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_risk_gate_rejects_inverted_sell_geometry():
    """Verify that TradeProposal and RiskGate strictly reject any SELL order where Stop Loss <= Entry Price."""
    from monika.domain.risk.risk_gate import RiskGate
    from monika.domain.risk.position_sizing import SizingResult
    from monika.domain.risk.trade_proposal import TradeProposal

    # 1. Proposal schema level: Must raise ValueError at boundary
    with pytest.raises(ValueError, match="SELL geometry violation"):
        TradeProposal(
            symbol="GBPUSD",
            direction="SELL",
            entry_price=1.33456,
            stop_loss=1.33420,
            take_profit=1.32000,
            lot_size=0.5,
        )

    # 2. RiskGate evaluation level: Sizing with inverted levels must be rejected
    risk_gate = RiskGate(settings={"trading": {"risk": {}}})
    session = create_mock_session()

    inverted_sizing = SizingResult(
        symbol="GBPUSD",
        direction="sell",
        entry_price=1.33456,
        stop_loss=1.33420,
        take_profit=1.32000,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.00036,
        sl_distance_pips=3.6,
        pip_value_per_lot=10.0,
        raw_lots=0.5,
        recommended_lots=0.5,
        rr_ratio=2.0,
        is_valid=True,
    )

    verdict = await risk_gate.evaluate(session, "GBPUSD", "sell", sizing=inverted_sizing, account_equity=10000.0)
    assert verdict.approved is False
    assert any("SELL geometry violation" in r for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_trailing_stop_manager_rejects_suicide_stop_adjustment():
    """Verify that TrailingStopManager strictly blocks any stop adjustment where BUY SL >= current mark price."""
    from monika.application.scheduler.trailing_stop_manager import TrailingStopManager

    exec_mock = AsyncMock()
    exec_mock.modify_position_sl_tp = AsyncMock(return_value={"success": True})

    manager = TrailingStopManager(
        settings={"trading": {"trailing_stop": {"enabled": True}}},
        execution_service=exec_mock,
    )

    pos = MagicMock()
    pos.symbol = "BTCUSD"
    pos.direction = "buy"
    pos.entry_price = 82108.7
    pos.sl = 81500.0
    pos.mt5_ticket = 99999
    pos.analysis_id = None
    pos.trailing_override_json = None

    session = AsyncMock()

    # Mock ATR
    mock_atr_row = MagicMock()
    mock_atr_row.value_json = "950.0"

    # Mock DB query
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_atr_row
    session.execute = AsyncMock(return_value=mock_res)

    # Current price has retraced to 82100.0 (near entry)
    # If breakeven is attempted at 82203.7, new_sl (82203.7) >= current_price (82100.0) -> MUST BE REJECTED
    result = await manager._check_position(session, pos, current_price_override=82100.0)
    assert result == {}  # Rejected, no adjustment made
    exec_mock.modify_position_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_signal_arbitrator_preserves_llm_wait_on_exhaustion_warning():
    """Verify that when LLM rationale identifies ADR exhaustion, Quant signal is blocked from overriding WAIT."""
    from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
    from monika.application.analysis.strategies.base_strategy import EdgeSignal

    arbitrator = SignalArbitrator(settings={})
    session = create_mock_session()

    quant_sig = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.88,
        entry_price=1.0900,
        stop_loss=1.0850,
        take_profit=1.1000,
    )

    llm_decision = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "Daily ADR 79% exhausted, extreme price extension near high of day. Awaiting pullback.",
    }

    res = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=quant_sig,
        llm_decision=llm_decision,
        vix_level=16.0,
        regime_info={"regime": "trend"},
    )

    assert res.decision == "wait"
    assert res.selected_source == "llm"
    assert "exhaustion" in res.arbitration_reason.lower()


@pytest.mark.asyncio
async def test_arbitrator_rejects_inverted_physical_geometry():
    """Verify SignalArbitrator strictly fails closed if any source outputs inverted SL/TP levels."""
    arbitrator = SignalArbitrator(settings={})
    session = create_mock_session()

    # Case 1: BUY with SL >= Entry
    inverted_buy_quant = EdgeSignal(
        strategy_id="smt_divergence",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.0900,
        stop_loss=1.0950,  # Inverted!
        take_profit=1.1100,
    )
    res_buy = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=inverted_buy_quant,
        llm_decision=None,
    )
    assert res_buy.decision == "avoid"
    assert res_buy.confidence == 0.0
    assert res_buy.risk_multiplier == 0.0
    assert res_buy.selected_source == "fail_closed_geometry_violation"

    # Case 2: SELL with SL <= Entry
    inverted_sell_llm = {
        "decision": "sell",
        "confidence": 0.85,
        "entry_price": 1.0900,
        "stop_loss": 1.0850,  # Inverted!
        "take_profit": 1.0700,
    }
    res_sell = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=None,
        llm_decision=inverted_sell_llm,
    )
    assert res_sell.decision == "avoid"
    assert res_sell.confidence == 0.0
    assert res_sell.risk_multiplier == 0.0
    assert res_sell.selected_source == "fail_closed_geometry_violation"

    # Case 3: BUY with TP <= Entry
    inverted_tp_buy = {
        "decision": "buy",
        "confidence": 0.85,
        "entry_price": 1.0900,
        "stop_loss": 1.0800,
        "take_profit": 1.0850,  # Inverted!
    }
    res_tp = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=None,
        llm_decision=inverted_tp_buy,
    )
    assert res_tp.decision == "avoid"
    assert res_tp.selected_source == "fail_closed_geometry_violation"


@pytest.mark.asyncio
async def test_arbitrator_scenario1_blocks_quarantined_and_incubating_alphas():
    """Verify standalone quant execution without LLM strictly rejects quarantined and incubating alphas."""
    arbitrator = SignalArbitrator(settings={})
    session = create_mock_session()

    # Quarantined strategy
    quarantined_sig = EdgeSignal(
        strategy_id="smc_fvg",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.0900,
        stop_loss=1.0850,
        take_profit=1.1000,
    )
    res_q = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=quarantined_sig,
        llm_decision=None,
    )
    assert res_q.decision == "avoid"
    assert res_q.selected_source == "quarantine_suppression"

    # Incubating candidate alpha
    incubating_sig = EdgeSignal(
        strategy_id="alpha_synth_999",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.85,
        entry_price=1.3000,
        stop_loss=1.2950,
        take_profit=1.3100,
        meta={"is_incubating": True},
    )
    res_inc = await arbitrator.arbitrate(
        session=session,
        symbol="GBPUSD",
        quant_signal=incubating_sig,
        llm_decision=None,
    )
    assert res_inc.decision == "avoid"
    assert res_inc.selected_source == "incubation_gate"


@pytest.mark.asyncio
async def test_trailing_stop_manager_minimum_hold_time():
    """Verify TrailingStopManager skips BE/trailing adjustment when position is held < 15 minutes."""
    from datetime import datetime, timezone, timedelta
    from monika.application.scheduler.trailing_stop_manager import TrailingStopManager

    exec_mock = AsyncMock()
    manager = TrailingStopManager(
        settings={"trading": {"trailing_stop": {"enabled": True}}},
        execution_service=exec_mock,
    )

    pos = MagicMock()
    pos.symbol = "EURUSD"
    pos.direction = "buy"
    pos.entry_price = 1.0900
    pos.sl = 1.0850
    pos.mt5_ticket = 12345
    # Position opened only 5 minutes ago
    pos.opened_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    pos.trailing_override_json = None

    session = AsyncMock()
    result = await manager._check_position(session, pos, current_price_override=1.0950)
    assert result == {}
    exec_mock.modify_position_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_signal_arbitrator_blocks_unpromoted_override_on_llm_wait():
    """Verify that an unpromoted strategy cannot override an LLM WAIT decision."""
    from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
    from monika.application.analysis.strategies.base_strategy import EdgeSignal

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    session = AsyncMock()

    unpromoted_sig = EdgeSignal(
        strategy_id="alpha_unpromoted_xyz",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.90,
        entry_price=1.0900,
        stop_loss=1.0850,
        take_profit=1.1000,
    )
    llm_wait = {
        "decision": "wait",
        "confidence": 0.50,
        "rationale": "Consolidation before macro news",
    }

    res = await arbitrator.arbitrate(
        session=session,
        symbol="EURUSD",
        quant_signal=unpromoted_sig,
        llm_decision=llm_wait,
    )
    assert res.decision == "wait"
    assert res.selected_source == "llm"


@pytest.mark.asyncio
async def test_compute_prompt_invariants_formatting():
    """Verify compute_prompt_invariants creates pre-computed invariants block with recommended execution levels."""
    from monika.application.analysis.stages.per_asset.runner_mixins.single_asset_helpers import (
        compute_prompt_invariants,
    )

    settings = {"trading": {"risk": {"min_rr_ratio": 1.5}}}
    raw_bundle = {
        "get_price_history_H4": {"bars": [{"close": 1.1500}]},
        "get_atr_H4": {"atr": 0.0020},
        "get_daily_range_context": {"adr_5d": 0.0060},
    }
    blocks = []
    curr_px, atr, adr = await compute_prompt_invariants(
        settings=settings,
        symbol="EURUSD",
        raw_bundle_data=raw_bundle,
        initial_context_blocks=blocks,
        session=None,
    )
    assert curr_px == 1.1500
    assert atr == 0.0020
    assert adr == 0.0060
    assert len(blocks) == 1
    assert blocks[0][0] == "PRE-COMPUTED TRADE INVARIANTS"
    assert "BUY INVARIANTS" in blocks[0][1]
    assert "SELL INVARIANTS" in blocks[0][1]
