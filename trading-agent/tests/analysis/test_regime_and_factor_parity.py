import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from analysis.strategies.registry import StrategyRegistry
from analysis.strategies.tsm_momentum import TimeSeriesMomentum
from analysis.strategies.gap_fade import DailyReopenGapFade
from risk.risk_gate import RiskGate
from scheduler.edge_strategy_runner import EdgeStrategyRunner
from scheduler.trigger_checker import TriggerChecker
from database.models import Position, PaperTradeRecord, TradeTrigger


class DummyTrendStrategy(EdgeStrategy):
    strategy_id = "dummy_trend"
    factor_family = "trend"
    compatible_regimes = {"TREND", "STRONG_TREND"}

    async def evaluate(self, session, symbol: str, settings: dict):
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.75,
            entry_price=1.2500,
            stop_loss=1.2400,
            take_profit=1.2700,
            factor_family="trend",
        )


class DummyFadeStrategy(EdgeStrategy):
    strategy_id = "dummy_fade"
    factor_family = "mean_reversion"
    compatible_regimes = {"RANGE", "VOLATILE_CHOP"}

    async def evaluate(self, session, symbol: str, settings: dict):
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="sell",
            valid=True,
            confidence=0.70,
            entry_price=1.2500,
            stop_loss=1.2600,
            take_profit=1.2300,
            factor_family="mean_reversion",
            ttl_minutes=45,
        )


@pytest.mark.asyncio
async def test_regime_classifier_probabilities():
    from analysis.calculators.regime_classifier import classify_market_regime
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # No VIX data
    mock_session.execute.return_value = mock_res

    with patch("analysis.calculators.regime_classifier._get_latest_adx", AsyncMock(return_value={"adx": 32.5})), \
         patch("analysis.calculators.regime_classifier._get_atr_series", AsyncMock(return_value=[1.2] * 20)), \
         patch("analysis.calculators.regime_classifier.compute_bollinger_donchian_chop", AsyncMock(return_value={"chop_block": False})):
        res = await classify_market_regime(mock_session, "EURUSD")
        assert "regime_probabilities" in res
        probs = res["regime_probabilities"]
        assert "trend" in probs
        assert "range" in probs
        assert "volatile_chop" in probs
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01
        assert probs["trend"] > probs["range"]


@pytest.mark.asyncio
async def test_strategy_regime_compatibility():
    trend_strat = DummyTrendStrategy()
    fade_strat = DummyFadeStrategy()

    assert trend_strat.is_regime_compatible("TREND") is True
    assert trend_strat.is_regime_compatible("STRONG_TREND") is True
    assert trend_strat.is_regime_compatible("RANGE") is False
    assert trend_strat.is_regime_compatible("VOLATILE_CHOP") is False

    assert fade_strat.is_regime_compatible("RANGE") is True
    assert fade_strat.is_regime_compatible("VOLATILE_CHOP") is True
    assert fade_strat.is_regime_compatible("TREND") is False


@pytest.mark.asyncio
async def test_registry_evaluate_all_regime_filtering():
    mock_session = AsyncMock()
    strat1 = DummyTrendStrategy()
    with patch.dict(StrategyRegistry._registry, {"dummy_trend": DummyTrendStrategy, "dummy_fade": DummyFadeStrategy}, clear=True):
        # When current_regime is RANGE, only strat2 (fade) should run
        signals_range = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {}, current_regime="RANGE")
        assert len(signals_range) == 1
        assert signals_range[0].strategy_id == "dummy_fade"
        assert signals_range[0].factor_family == "mean_reversion"

        # When current_regime is TREND, only strat1 (trend) should run
        signals_trend = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {}, current_regime="TREND")
        assert len(signals_trend) == 1
        assert signals_trend[0].strategy_id == "dummy_trend"
        assert signals_trend[0].factor_family == "trend"


@pytest.mark.asyncio
async def test_risk_gate_strategy_factor_exposure():
    settings = {
        "trading": {
            "risk": {
                "max_positions_per_factor_family": {
                    "trend": 2,
                    "mean_reversion": 2,
                    "default": 2,
                }
            }
        }
    }
    gate = RiskGate(settings)

    mock_session = AsyncMock()

    # Case 1: 1 existing trend position, adding 1 more -> Allowed
    pos1 = MagicMock(spec=Position)
    pos1.status = "open"
    pos1.source_strategy_id = "tsm_momentum"

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pos1]
    mock_session.execute.return_value = mock_res

    order_ok = {
        "symbol": "EURUSD",
        "direction": "buy",
        "volume": 0.1,
        "entry_price": 1.1000,
        "stop_loss": 1.0900,
        "take_profit": 1.1200,
        "strategy_factor_family": "trend",
    }

    allowed, reason = await gate._check_strategy_factor_exposure(mock_session, order_ok)
    assert allowed is True
    assert "factor_exposure_ok" in reason

    # Case 2: 2 existing trend positions, adding 1 more -> Rejected
    pos2 = MagicMock(spec=Position)
    pos2.status = "open"
    pos2.source_strategy_id = "xau_trend_engine"
    mock_res.scalars.return_value.all.return_value = [pos1, pos2]

    allowed, reason = await gate._check_strategy_factor_exposure(mock_session, order_ok)
    assert allowed is False
    assert "capacity reached" in reason


@pytest.mark.asyncio
async def test_edge_strategy_runner_ensemble_conflict_suppression():
    settings = {
        "trading": {
            "asset_universe": ["GBPUSD"],
            "edge_strategy": {
                "signal_cooldown_seconds": 3600,
            }
        }
    }
    runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())

    sig_buy = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.2500,
        stop_loss=1.2400,
        take_profit=1.2700,
        factor_family="trend",
    )
    sig_sell = EdgeSignal(
        strategy_id="gap_fade",
        symbol="GBPUSD",
        direction="sell",
        valid=True,
        confidence=0.75,
        entry_price=1.2500,
        stop_loss=1.2600,
        take_profit=1.2300,
        factor_family="mean_reversion",
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # No open position
    mock_session.execute.return_value = mock_res

    with patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
         patch("analysis.calculators.regime_classifier.classify_market_regime", AsyncMock(return_value={"regime": "trend"})), \
         patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[sig_buy, sig_sell])), \
         patch("scheduler.edge_strategy_runner.get_session") as mock_get_session, \
         patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route:

        mock_get_session.return_value.__aenter__.return_value = mock_session
        await runner.run_once()

        # Conflicting signals on the same symbol (buy vs sell) must suppress all routing
        mock_route.assert_not_called()


@pytest.mark.asyncio
async def test_edge_strategy_runner_ensemble_concordance_boost():
    settings = {
        "trading": {
            "asset_universe": ["GBPUSD"],
            "edge_strategy": {
                "signal_cooldown_seconds": 3600,
            }
        }
    }
    runner = EdgeStrategyRunner(settings=settings, execution_service=MagicMock())

    sig_buy1 = EdgeSignal(
        strategy_id="tsm_momentum",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.2500,
        stop_loss=1.2400,
        take_profit=1.2700,
        factor_family="trend",
    )
    sig_buy2 = EdgeSignal(
        strategy_id="liquidity_sweep",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.70,
        entry_price=1.2500,
        stop_loss=1.2400,
        take_profit=1.2700,
        factor_family="breakout",
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None  # No open position
    mock_session.execute.return_value = mock_res

    with patch("scheduler.edge_strategy_runner.validate_data_freshness", AsyncMock(return_value={"ready": True})), \
         patch("analysis.calculators.regime_classifier.classify_market_regime", AsyncMock(return_value={"regime": "trend"})), \
         patch("scheduler.edge_strategy_runner.StrategyRegistry.evaluate_all", AsyncMock(return_value=[sig_buy1, sig_buy2])), \
         patch("scheduler.edge_strategy_runner.get_session") as mock_get_session, \
         patch.object(runner, "_materialize_and_route", AsyncMock()) as mock_route:

        mock_get_session.return_value.__aenter__.return_value = mock_session
        await runner.run_once()

        # Concordant signals: chosen = sig_buy1, confidence boosted from 0.75 to 0.80
        mock_route.assert_called_once()
        routed_sig = mock_route.call_args[0][1]
        assert routed_sig.strategy_id == "tsm_momentum"
        assert round(routed_sig.confidence, 2) == 0.80
        assert routed_sig.meta.get("ensemble_confirmed") is True


@pytest.mark.asyncio
async def test_trigger_checker_cancel_pending_ttl():
    settings = {}
    checker = TriggerChecker(settings=settings, execution_service=MagicMock())

    trigger = TradeTrigger(
        id=99,
        asset_analysis_id=42,
        trigger_type="cancel_pending",
        condition_json='{"symbol": "EURUSD"}',
        status="pending",
    )

    pos_pending = MagicMock(spec=Position)
    pos_pending.status = "pending"
    pos_pending.mt5_ticket = 123456

    paper_pending = MagicMock(spec=PaperTradeRecord)
    paper_pending.status = "pending"
    paper_pending.notes = ""

    mock_session = AsyncMock()
    res_pos = MagicMock()
    res_pos.scalars.return_value.all.return_value = [pos_pending]
    res_paper = MagicMock()
    res_paper.scalars.return_value.all.return_value = [paper_pending]

    mock_session.execute.side_effect = [res_pos, res_paper]

    with patch("scheduler.trigger_checker.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session

        await checker._handle_cancel_pending_order(trigger)

        assert pos_pending.status == "cancelled"
        assert paper_pending.status == "cancelled"
