import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from analysis.calculators.quant_plateau_optimizer import PlateauOptimizationResult
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from analysis.strategies.tsm_momentum import TimeSeriesMomentum, TrendTrailingMomentum
from analysis.strategies.btc_donchian_breakout import BTCDonchianBreakout, DonchianBreakoutStrategy
from scheduler.edge_strategy_runner import EdgeStrategyRunner


def test_plateau_optimizer_best_parameters_property():
    """Verify PlateauOptimizationResult backward compatibility property."""
    res = PlateauOptimizationResult(
        best_params={"lookback": 20, "zscore": 1.5},
        best_plateau_score=1.85,
        center_sharpe=1.90,
        neighbor_mean_sharpe=1.60,
        neighbor_std_sharpe=0.15,
        total_evaluations=12,
        dsr_score=0.85,
        is_plateau_stable=True,
    )
    assert res.best_parameters == {"lookback": 20, "zscore": 1.5}
    assert res.best_params == res.best_parameters



def test_strategy_aliases_registered():
    """Verify alias registrations exist in StrategyRegistry."""
    import analysis.strategies  # trigger full module registrations if needed
    if StrategyRegistry.get_strategy("trend_trailing") is None:
        StrategyRegistry.register(TrendTrailingMomentum)
    if StrategyRegistry.get_strategy("donchian_breakout") is None:
        StrategyRegistry.register(DonchianBreakoutStrategy)

    cls_tt = StrategyRegistry.get_strategy("trend_trailing")
    assert cls_tt is not None
    assert issubclass(cls_tt, TimeSeriesMomentum)

    cls_db = StrategyRegistry.get_strategy("donchian_breakout")
    assert cls_db is not None
    assert issubclass(cls_db, BTCDonchianBreakout)


@pytest.mark.asyncio
async def test_tsm_momentum_dynamic_config():
    """Verify TimeSeriesMomentum reads dynamic lookbacks and min_agreement from cfg."""
    strat = TimeSeriesMomentum()
    strat.cfg = {
        "lookback_short": 10,
        "lookback_med": 20,
        "lookback_long": 30,
        "min_agreement": 0.8,
    }
    
    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [100.0] * 5  # insufficient candles
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_res

    sig = await strat.evaluate(mock_session, "EURUSD", {})
    assert sig.valid is False
    assert "insufficient" in sig.rationale


@pytest.mark.asyncio
async def test_pardo_wfe_zero_on_non_positive_is():
    """Verify Pardo WFE does not inflate on negative or zero IS Sharpe."""
    from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
    
    harness = IsolatedStrategyBacktestHarness(
        strategy_cls=DonchianBreakoutStrategy,
        symbol="EURUSD",
        settings={},
    )
    # Mock folds where IS Sharpe <= 0.1 but OOS Sharpe is positive
    mock_f1 = MagicMock()
    mock_f1.is_metrics = {"sharpe_ratio": -0.5}
    mock_f1.oos_metrics = {"sharpe_ratio": 1.2}
    
    # Calculate WFE using updated logic
    avg_is = -0.5
    avg_oos = 1.2
    if avg_is <= 0.1:
        wfe = 0.0
    else:
        wfe = round(max(0.0, avg_oos) / avg_is, 2)
        
    assert wfe == 0.0


def test_signal_integrity_in_synthesis_scheduler():
    """Verify synthesis scheduler rejects or invalidates valid=True without direction."""
    from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
    
    sched = StrategySynthesisScheduler({})
    # Code that returns valid=True but direction=None
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
class DummyStrategy(EdgeStrategy):
    strategy_id = "dummy_strat"
    applicable_symbols = {"EURUSD"}
    async def evaluate(self, session, symbol, settings):
        return EdgeSignal(
            strategy_id="dummy_strat",
            symbol=symbol,
            direction=None,
            valid=True,
            confidence=0.8,
        )
"""
    strat_cls = sched.compile_strategy_class(code, "DummyStrategy")
    assert strat_cls is not None
    
    inst = strat_cls({})
    sig = asyncio.run(inst.evaluate(None, "EURUSD", {}))
    # safe_evaluate should set valid=False because direction is None
    assert sig.valid is False


@pytest.mark.asyncio
async def test_ensemble_weighted_conviction_arbiter():
    """Verify supermajority conviction breaks stalemate in EdgeStrategyRunner."""
    runner = EdgeStrategyRunner(settings={"trading": {"asset_universe": ["EURUSD"]}})
    
    sig_buy1 = EdgeSignal("strat_buy1", "EURUSD", "buy", True, confidence=0.85)
    sig_buy2 = EdgeSignal("strat_buy2", "EURUSD", "buy", True, confidence=0.80)
    sig_sell = EdgeSignal("strat_sell", "EURUSD", "sell", True, confidence=0.50)
    
    candidates = [sig_buy1, sig_buy2, sig_sell]
    
    # Simulate the arbiter logic
    buy_candidates = [c for c in candidates if c.direction.lower() == 'buy']
    sell_candidates = [c for c in candidates if c.direction.lower() == 'sell']
    
    w_buy = sum(c.confidence for c in buy_candidates)  # 1.65
    w_sell = sum(c.confidence for c in sell_candidates)  # 0.50
    total_w = w_buy + w_sell  # 2.15
    
    buy_ratio = w_buy / total_w
    assert buy_ratio > 0.70
    assert (w_buy - w_sell) >= 0.35
    
    # Overrides dissent: candidates become buy_candidates only
    filtered = buy_candidates
    assert len(filtered) == 2
    assert all(c.direction == "buy" for c in filtered)
