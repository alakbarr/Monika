"""
Autonomous Alpha Discovery Scheduler.

Periodically explores and validates parameter variations and rule hypotheses
on historical market data using PointInTimeBacktestEngine and WalkForwardEngine.
Promotes robust alpha candidates with Walk-Forward Efficiency (WFE) > 0.60
and positive Out-of-Sample Sharpe into candidate strategy pools.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import select, update
from backtest.walk_forward_engine import WalkForwardEngine, WalkForwardResult
from backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness
from analysis.strategies.registry import StrategyRegistry
import analysis.strategies
from analysis.calculators.quant_plateau_optimizer import (
    QuantPlateauOptimizer,
    ParameterSpec,
    PlateauOptimizationResult,
)
from database.db import get_session
from database.models import SystemConfig, ActivityLog

logger = logging.getLogger("TradingAgent.AlphaDiscoveryScheduler")

STRATEGY_PARAM_SPACES: Dict[str, List[ParameterSpec]] = {
    "donchian_breakout": [
        ParameterSpec("donchian_period", "int", low=10, high=40, step=2),
        ParameterSpec("volume_zscore_min", "float", low=1.0, high=2.5, step=0.1),
        ParameterSpec("size_multiplier", "float", low=0.5, high=1.0, step=0.1),
    ],
    "btc_donchian_breakout": [
        ParameterSpec("donchian_period", "int", low=10, high=40, step=2),
        ParameterSpec("volume_zscore_min", "float", low=1.0, high=2.5, step=0.1),
        ParameterSpec("size_multiplier", "float", low=0.5, high=1.0, step=0.1),
    ],
    "xau_trend_engine": [
        ParameterSpec("donchian_period", "int", low=12, high=36, step=2),
        ParameterSpec("volume_zscore_min", "float", low=1.0, high=2.5, step=0.1),
        ParameterSpec("size_multiplier", "float", low=0.5, high=1.0, step=0.1),
    ],
    "trend_trailing": [
        ParameterSpec("lookback_short", "int", low=20, high=80, step=5),
        ParameterSpec("lookback_med", "int", low=90, high=160, step=10),
        ParameterSpec("min_agreement", "float", low=0.5, high=1.0, step=0.1),
        ParameterSpec("sl_atr_multiplier", "float", low=1.2, high=2.5, step=0.2),
        ParameterSpec("tp_sl_multiplier", "float", low=1.5, high=3.0, step=0.2),
    ],
    "tsm_momentum": [
        ParameterSpec("lookback_short", "int", low=20, high=80, step=5),
        ParameterSpec("lookback_med", "int", low=90, high=160, step=10),
        ParameterSpec("min_agreement", "float", low=0.5, high=1.0, step=0.1),
        ParameterSpec("sl_atr_multiplier", "float", low=1.2, high=2.5, step=0.2),
        ParameterSpec("tp_sl_multiplier", "float", low=1.5, high=3.0, step=0.2),
    ],
    "liquidity_sweep": [
        ParameterSpec("asian_session_start_utc", "int", low=0, high=4, step=1),
        ParameterSpec("asian_session_end_utc", "int", low=6, high=9, step=1),
        ParameterSpec("sweep_pip_threshold", "float", low=2.0, high=10.0, step=1.0),
    ],
}


@dataclass
class AlphaHypothesis:
    """Hypothesis defining a specific strategy rule and parameter combination."""
    hypothesis_id: str
    name: str
    strategy_type: str  # e.g. "donchian_breakout", "trend_trailing", "liquidity_sweep", "mean_reversion"
    symbol: str
    parameters: Dict[str, Any]
    description: str


@dataclass
class CandidateAlphaProposal:
    """A vetted alpha strategy proposal passing walk-forward efficiency thresholds."""
    proposal_id: str
    hypothesis: AlphaHypothesis
    overall_wfe: float
    aggregate_is_sharpe: float
    aggregate_oos_sharpe: float
    total_oos_trades: int
    oos_win_rate_pct: float
    is_overfit: bool
    status: str = "PROPOSED"  # "PROPOSED", "ACCEPTED", "DEPLOYED", "REJECTED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    markdown_report: str = ""
    max_drawdown_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class AlphaDiscoveryScheduler:
    """
    Autonomous scheduler loop that generates and backtests alpha hypotheses.
    Enforces institutional Walk-Forward Optimization (WFO) standards:
    - Minimum WFE > 0.60 (industry threshold for genuine out-of-sample edge)
    - Positive OOS Sharpe (> 0.50)
    - Zero curve-fitting / overfit flag false
    """

    def __init__(
        self,
        settings: dict,
        interval_hours: float = 24.0,
        lookback_days: int = 120,
        is_window_days: int = 60,
        oos_window_days: int = 20,
        step_days: int = 20,
        min_wfe: float = 0.60,
        min_oos_sharpe: float = 0.50,
        recovery_event: Optional[asyncio.Event] = None,
        notifier: Optional[Any] = None,
        edge_strategy_runner: Optional[Any] = None,
        auto_deploy_paper: bool = False,
    ):
        self.settings = settings
        cfg = settings.get("alpha_discovery", {}) if isinstance(settings, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        self.interval_hours = float(cfg.get("interval_hours", interval_hours))
        self.lookback_days = int(cfg.get("lookback_days", lookback_days))
        self.is_window_days = int(cfg.get("is_window_days", is_window_days))
        self.oos_window_days = int(cfg.get("oos_window_days", oos_window_days))
        self.step_days = int(cfg.get("step_days", step_days))
        self.min_wfe = float(cfg.get("min_wfe", min_wfe))
        self.min_oos_sharpe = float(cfg.get("min_oos_sharpe", min_oos_sharpe))
        self.max_drawdown_limit = float(cfg.get("max_drawdown_limit", 20.0))
        self.auto_deploy_paper = bool(cfg.get("auto_deploy_paper", auto_deploy_paper))
        self.recovery_event = recovery_event
        self.notifier = notifier
        self.edge_strategy_runner = edge_strategy_runner
        self._running = False
        self._stop_event = asyncio.Event()
        self.candidate_proposals: List[CandidateAlphaProposal] = []
        self._evaluated_hypothesis_ids: set[str] = set()

    def set_edge_strategy_runner(self, runner: Any) -> None:
        """Sets or updates the active EdgeStrategyRunner instance for hot-reloading."""
        self.edge_strategy_runner = runner


    def generate_hypotheses(self, symbols: Optional[List[str]] = None) -> List[AlphaHypothesis]:
        """
        Generates a diverse set of parameter variations and rule hypotheses
        across targeted symbols and trading regimes.
        """
        syms = symbols or self.settings.get("trading", {}).get(
            "asset_universe", ["XAUUSD", "EURUSD", "BTCUSD", "GBPUSD"]
        )
        hypotheses: List[AlphaHypothesis] = []

        for sym in syms:
            # 1. Donchian Breakout Variations
            for period in (14, 20, 30):
                for zscore in (1.2, 1.5, 1.8):
                    hyp_id = f"donchian_{sym}_p{period}_z{int(zscore*10)}"
                    hypotheses.append(
                        AlphaHypothesis(
                            hypothesis_id=hyp_id,
                            name=f"Donchian Breakout ({sym} P={period} Z={zscore})",
                            strategy_type="btc_donchian_breakout" if "BTC" in sym else "xau_trend_engine",
                            symbol=sym,
                            parameters={
                                "donchian_period": period,
                                "volume_zscore_min": zscore,
                                "size_multiplier": 0.8,
                            },
                            description=f"Donchian breakout on {sym} with period {period} and volume filter {zscore}",
                        )
                    )

            # 2. Trend Trailing Volatility Variations
            for sl_atr in (1.2, 1.5, 2.0):
                for tp_sl in (1.5, 2.0, 2.5):
                    hyp_id = f"trend_trail_{sym}_sl{int(sl_atr*10)}_tp{int(tp_sl*10)}"
                    hypotheses.append(
                        AlphaHypothesis(
                            hypothesis_id=hyp_id,
                            name=f"Trend Trailing ({sym} SL={sl_atr} ATR, TP={tp_sl} R)",
                            strategy_type="trend_trailing",
                            symbol=sym,
                            parameters={
                                "sl_atr_multiplier": sl_atr,
                                "tp_sl_multiplier": tp_sl,
                                "use_adr_cap": True,
                            },
                            description=f"Trend trailing on {sym} with SL {sl_atr} ATR and TP/SL {tp_sl}",
                        )
                    )

            # 3. Liquidity Sweep Asian Range Variations
            for asian_hours in ((0, 8), (22, 7)):
                hyp_id = f"sweep_{sym}_h{asian_hours[0]}_{asian_hours[1]}"
                hypotheses.append(
                    AlphaHypothesis(
                        hypothesis_id=hyp_id,
                        name=f"Asian Liquidity Sweep ({sym} {asian_hours[0]}-{asian_hours[1]} UTC)",
                        strategy_type="liquidity_sweep",
                        symbol=sym,
                        parameters={
                            "asian_session_start_utc": asian_hours[0],
                            "asian_session_end_utc": asian_hours[1],
                        },
                        description=f"Liquidity sweep targeting Asian range between {asian_hours[0]} and {asian_hours[1]} UTC",
                    )
                )

        return hypotheses

    async def evaluate_hypothesis(self, hypothesis: AlphaHypothesis) -> Optional[CandidateAlphaProposal]:
        """
        Evaluates a single alpha hypothesis using IsolatedStrategyBacktestHarness over historical window.
        Returns CandidateAlphaProposal if WFE > min_wfe (0.60) and OOS Sharpe > min_oos_sharpe (0.50).
        """
        logger.debug(
            f"[AlphaDiscovery] Evaluating hypothesis '{hypothesis.name}' "
            f"on {hypothesis.symbol}..."
        )

        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=self.lookback_days)
        end_date = now

        # Construct custom overlay settings for this test
        test_settings = dict(self.settings)
        trading_cfg = dict(test_settings.get("trading", {}))
        edge_cfg = dict(trading_cfg.get("edge_strategy", {}))

        # Merge hypothesis parameters into edge_strategy config
        strat_key = hypothesis.strategy_type
        existing_strat_cfg = dict(edge_cfg.get(strat_key, {}))
        existing_strat_cfg.update(hypothesis.parameters)
        edge_cfg[strat_key] = existing_strat_cfg
        trading_cfg["edge_strategy"] = edge_cfg
        test_settings["trading"] = trading_cfg

        # Resolve strategy class from StrategyRegistry or aliases
        strat_cls = StrategyRegistry.get_strategy(hypothesis.strategy_type)
        if strat_cls is None:
            alias_map = {
                "trend_trailing": "tsm_momentum",
                "donchian_breakout": "btc_donchian_breakout",
                "btc_donchian_breakout": "btc_donchian_breakout",
                "xau_trend_engine": "xau_trend_engine",
                "liquidity_sweep": "liquidity_sweep",
            }
            target_id = alias_map.get(hypothesis.strategy_type, hypothesis.strategy_type)
            strat_cls = StrategyRegistry.get_strategy(target_id)

        if strat_cls is None:
            logger.warning(
                f"[AlphaDiscovery] Strategy class for '{hypothesis.strategy_type}' "
                f"not found in StrategyRegistry. Skipping evaluation."
            )
            return None

        # Execute Isolated Zero-Lookahead Walk-Forward Harness
        harness = IsolatedStrategyBacktestHarness(
            strategy_cls=strat_cls,
            symbol=hypothesis.symbol,
            settings=test_settings,
            strategy_params=hypothesis.parameters,
        )

        # Plateau Pre-Optimization: Find parameter flat stability plateau on IS data before WFO
        param_specs = STRATEGY_PARAM_SPACES.get(hypothesis.strategy_type)
        if param_specs and hasattr(harness, "fetch_historical_candles") and hasattr(harness, "_run_simulation_on_candles"):
            try:
                async with get_session() as opt_session:
                    all_candles = await harness.fetch_historical_candles(
                        session=opt_session, timeframe="H1", limit=1200
                    )
                if all_candles and len(all_candles) >= 120:
                    is_size = int(len(all_candles) * 0.65)
                    is_candles = all_candles[:is_size]

                    async def _eval_plateau(params: Dict[str, Any]) -> Dict[str, Any]:
                        harness.strategy_params = params
                        m = await harness._run_simulation_on_candles(is_candles)
                        return {
                            "sharpe": m.sharpe_ratio,
                            "trades": m.total_trades,
                            "trade_returns": [t.pnl_pct / 100.0 for t in m.trades],
                            "pnl_pct": m.total_pnl_pct,
                        }

                    optimizer = QuantPlateauOptimizer(
                        param_space=param_specs,
                        n_trials=12,
                        n_neighbors_per_candidate=2,
                        min_trade_count=10,
                    )
                    opt_res = await optimizer.optimize(_eval_plateau)
                    if opt_res and opt_res.best_parameters:
                        hypothesis.parameters.update(opt_res.best_parameters)
                        harness.strategy_params = hypothesis.parameters
                        logger.info(
                            f"[AlphaDiscovery] Plateau optimizer found robust parameter plateau for '{hypothesis.name}': "
                            f"{opt_res.best_parameters} (Plateau Score: {opt_res.best_plateau_score:.2f}, "
                            f"Neighbor Sharpe: {opt_res.neighbor_mean_sharpe:.2f})"
                        )
            except Exception as opt_err:
                logger.debug(f"[AlphaDiscovery] Plateau pre-optimization non-fatal: {opt_err}")

        try:
            async with get_session() as session:
                result = await harness.run_walk_forward(
                    session=session,
                    n_folds=4,
                    is_ratio=0.65,
                    total_candles=1500,
                    min_candles=60,
                    trial_counter=max(1, len(self._evaluated_hypothesis_ids)),
                )
        except Exception as e:
            logger.warning(
                f"[AlphaDiscovery] Walk-Forward evaluation failed for '{hypothesis.name}': {e}",
                exc_info=True,
            )
            return None

        # Parse metrics (supports both dictionary result from harness and mock result objects)
        if isinstance(result, dict):
            wfe = float(result.get("overall_wfe", 0.0) or 0.0)
            oos_sharpe = float(result.get("aggregate_oos_sharpe", 0.0) or 0.0)
            is_sharpe = float(result.get("aggregate_is_sharpe", 0.0) or 0.0)
            dsr_score = float(result.get("dsr", 0.0) or 0.0)
            oos_trades = result.get("all_oos_trades", [])
            total_oos_trades = int(result.get("total_oos_trades", len(oos_trades)))
            alpha_val = result.get("alpha_validation")
            alpha_passed = getattr(alpha_val, "passed", True) if alpha_val else True
            is_overfit = bool(oos_sharpe < 0.20 or (is_sharpe > 1.5 and oos_sharpe < 0.40) or wfe < 0.40)
            passed = bool(result.get("passed", False))
        else:
            wfe = float(getattr(result, "overall_wfe", 0.0) or 0.0)
            oos_sharpe = float(getattr(result, "aggregate_oos_sharpe", 0.0) or 0.0)
            is_sharpe = float(getattr(result, "aggregate_is_sharpe", 0.0) or 0.0)
            dsr_score = float(getattr(result, "deflated_sharpe", 0.0) or 0.0)
            oos_trades = getattr(result, "stitched_oos_trades", [])
            total_oos_trades = int(getattr(result, "total_oos_trades", len(oos_trades)))
            alpha_val = getattr(result, "alpha_validation", None)
            alpha_passed = getattr(alpha_val, "passed", True) if alpha_val else True
            is_overfit = bool(getattr(result, "is_overfit", False))
            passed = bool(wfe >= self.min_wfe and oos_sharpe >= self.min_oos_sharpe and not is_overfit)

        # Compute maximum drawdown across stitched OOS trades
        max_dd_pct = 0.0
        wins = 0
        if oos_trades:
            equity = 1.0
            peak = 1.0
            for trade in oos_trades:
                pnl_pct = float(getattr(trade, "pnl_pct", 0.0) or 0.0)
                if pnl_pct > 0:
                    wins += 1
                equity *= (1.0 + pnl_pct / 100.0)
                if equity > peak:
                    peak = equity
                dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
                if dd > max_dd_pct:
                    max_dd_pct = dd
        if not isinstance(result, dict) and getattr(result, "folds", None):
            for f in result.folds:
                fold_dd = float(f.oos_metrics.get("max_drawdown_pct", 0.0) or 0.0)
                if fold_dd > max_dd_pct:
                    max_dd_pct = fold_dd

        oos_win_rate = round((wins / total_oos_trades) * 100.0, 1) if total_oos_trades > 0 else (
            float(getattr(result, "oos_win_rate_pct", 0.0)) if not isinstance(result, dict) else 0.0
        )

        min_oos_trades_threshold = int(self.settings.get("alpha_discovery", {}).get("min_oos_trades", 20))
        meets_criteria = (
            (passed or (wfe >= self.min_wfe and oos_sharpe >= self.min_oos_sharpe and not is_overfit))
            and wfe >= self.min_wfe
            and oos_sharpe >= self.min_oos_sharpe
            and not is_overfit
            and total_oos_trades >= min_oos_trades_threshold
            and max_dd_pct <= self.max_drawdown_limit
            and alpha_passed
        )

        logger.debug(
            f"[AlphaDiscovery] Hypothesis '{hypothesis.name}' Result: "
            f"WFE={wfe:.2f} (min {self.min_wfe}), OOS Sharpe={oos_sharpe:.2f} "
            f"(min {self.min_oos_sharpe}), MaxDD={max_dd_pct:.1f}% (max {self.max_drawdown_limit}%), "
            f"Trades={total_oos_trades}, Overfit={is_overfit}, AlphaValid={alpha_passed} -> "
            f"{'QUALIFIED' if meets_criteria else 'REJECTED'}"
        )

        if not meets_criteria:
            return None

        # Build proposal with auto-promotion to PAPER_ACTIVE if WFE >= min_wfe (0.60) and auto_deploy_paper is True
        proposal_id = f"alpha_{uuid.uuid4().hex[:8]}"
        if hasattr(harness, "generate_markdown_report"):
            md_report = harness.generate_markdown_report(result if isinstance(result, dict) else {
                "overall_wfe": wfe,
                "aggregate_is_sharpe": is_sharpe,
                "aggregate_oos_sharpe": oos_sharpe,
                "dsr": dsr_score,
                "all_oos_trades": oos_trades,
                "alpha_validation": alpha_val,
            })
        else:
            md_report = f"# Alpha Evaluation: {hypothesis.name}\nWFE: {wfe:.2f}"

        initial_status = "PAPER_ACTIVE" if (wfe >= self.min_wfe and self.auto_deploy_paper) else "PROPOSED"

        proposal = CandidateAlphaProposal(
            proposal_id=proposal_id,
            hypothesis=hypothesis,
            overall_wfe=wfe,
            aggregate_is_sharpe=is_sharpe,
            aggregate_oos_sharpe=oos_sharpe,
            total_oos_trades=total_oos_trades,
            oos_win_rate_pct=oos_win_rate,
            is_overfit=is_overfit,
            status=initial_status,
            markdown_report=md_report,
            max_drawdown_pct=round(max_dd_pct, 2),
        )

        self.candidate_proposals.append(proposal)

        # Persist proposal into DB and hot-reload if PAPER_ACTIVE
        await self._persist_proposal(proposal)

        return proposal

    async def _persist_proposal(self, proposal: CandidateAlphaProposal) -> None:
        """Persists vetted candidate proposal into DB SystemConfig and ActivityLog."""
        try:
            async with get_session() as session:
                config_key = f"candidate_alpha_{proposal.proposal_id}"
                config_val = json.dumps(proposal.to_dict())

                existing = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == config_key)
                )).scalar_one_or_none()

                if existing:
                    await session.execute(
                        update(SystemConfig)
                        .where(SystemConfig.key == config_key)
                        .values(value=config_val)
                    )
                else:
                    session.add(SystemConfig(key=config_key, value=config_val))

                # Auto-deployment: If status is PAPER_ACTIVE, persist dynamic parameters and hot-reload
                if proposal.status == "PAPER_ACTIVE":
                    # 1. Persist isolated per-symbol parameter key to prevent cross-asset overwrites
                    sym_param_key = f"strategy_params_{proposal.hypothesis.strategy_type}_{proposal.hypothesis.symbol}"
                    param_val = json.dumps(proposal.hypothesis.parameters)
                    existing_sym = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == sym_param_key)
                    )).scalar_one_or_none()

                    if existing_sym:
                        await session.execute(
                            update(SystemConfig)
                            .where(SystemConfig.key == sym_param_key)
                            .values(value=param_val)
                        )
                    else:
                        session.add(SystemConfig(key=sym_param_key, value=param_val))

                    # 2. Maintain global key for backward compatibility
                    global_param_key = f"strategy_params_{proposal.hypothesis.strategy_type}"
                    existing_global = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == global_param_key)
                    )).scalar_one_or_none()

                    if existing_global:
                        await session.execute(
                            update(SystemConfig)
                            .where(SystemConfig.key == global_param_key)
                            .values(value=param_val)
                        )
                    else:
                        session.add(SystemConfig(key=global_param_key, value=param_val))

                    # Hot-reload into StrategyRegistry and EdgeStrategyRunner with symbol context & alias sync
                    alias_map = {
                        "trend_trailing": "tsm_momentum",
                        "tsm_momentum": "trend_trailing",
                        "donchian_breakout": "btc_donchian_breakout",
                        "btc_donchian_breakout": "donchian_breakout",
                    }
                    target_types = [proposal.hypothesis.strategy_type]
                    if proposal.hypothesis.strategy_type in alias_map:
                        target_types.append(alias_map[proposal.hypothesis.strategy_type])

                    for stype in target_types:
                        try:
                            from analysis.strategies.registry import StrategyRegistry
                            StrategyRegistry.hot_reload(
                                stype,
                                proposal.hypothesis.parameters,
                                symbol=proposal.hypothesis.symbol,
                            )
                        except Exception as reg_err:
                            logger.debug(f"[AlphaDiscovery] StrategyRegistry hot_reload non-fatal for {stype}: {reg_err}")

                        if self.edge_strategy_runner and hasattr(self.edge_strategy_runner, "hot_reload_strategy"):
                            try:
                                self.edge_strategy_runner.hot_reload_strategy(
                                    stype, proposal.hypothesis.parameters
                                )
                            except Exception as run_err:
                                logger.debug(f"[AlphaDiscovery] EdgeStrategyRunner hot_reload non-fatal for {stype}: {run_err}")

                    # Register into StrategyDecayMonitor as incubating (min 4 paper trades required)
                    try:
                        from analysis.strategies.decay_monitor import get_strategy_decay_monitor
                        decay_mon = get_strategy_decay_monitor()
                        decay_mon.register_incubating_strategy(proposal.hypothesis.strategy_type)
                        await decay_mon.save_to_db(session)
                        logger.info(
                            f"[AlphaDiscovery] Registered '{proposal.hypothesis.strategy_type}' as incubating "
                            f"(requires {decay_mon.MIN_INCUBATION_TRADES} paper trades before live execution)."
                        )
                    except Exception as d_err:
                        logger.debug(f"[AlphaDiscovery] Failed to register incubating strategy in decay monitor: {d_err}")

                session.add(ActivityLog(
                    category="strategy",
                    description=(
                        f"Autonomous Alpha Discovered [{proposal.status}]: {proposal.hypothesis.name} "
                        f"WFE={proposal.overall_wfe:.2f}, OOS_Sharpe={proposal.aggregate_oos_sharpe:.2f}, "
                        f"Trades={proposal.total_oos_trades} (ID={proposal.proposal_id})"
                    ),
                    actor="alpha_discovery_scheduler",
                    related_id=None,
                ))
                await session.commit()
                logger.debug(f"[AlphaDiscovery] Successfully persisted proposal {proposal.proposal_id} ({proposal.status}) to DB.")

            # Notify operator if notifier is available
            if self.notifier and hasattr(self.notifier, "send_info"):
                deploy_badge = "🚀 <b>HOT-DEPLOYED TO PAPER TRADING</b>" if proposal.status == "PAPER_ACTIVE" else "PROPOSED"
                await self.notifier.send_info(
                    f"🧬 <b>Autonomous Alpha Discovered!</b>\n"
                    f"<b>Status:</b> {deploy_badge}\n"
                    f"<b>Strategy:</b> {proposal.hypothesis.name}\n"
                    f"<b>Symbol:</b> {proposal.hypothesis.symbol}\n"
                    f"<b>WFE:</b> <code>{proposal.overall_wfe:.2f}</code> (Target > 0.60)\n"
                    f"<b>OOS Sharpe:</b> <code>{proposal.aggregate_oos_sharpe:.2f}</code>\n"
                    f"<b>Max Drawdown:</b> <code>{proposal.max_drawdown_pct:.1f}%</code> (Limit <= {self.max_drawdown_limit:.1f}%)\n"
                    f"<b>OOS Win Rate:</b> <code>{proposal.oos_win_rate_pct:.1f}%</code> ({proposal.total_oos_trades} trades)\n"
                    f"Registered proposal: <code>{proposal.proposal_id}</code>"
                )
        except Exception as e:
            logger.warning(f"[AlphaDiscovery] Failed persisting proposal {proposal.proposal_id}: {e}")

    async def promote_to_paper_active(self, proposal_id: str) -> bool:
        """Promotes a candidate proposal to PAPER_ACTIVE and hot-reloads into EdgeStrategyRunner."""
        target_prop = next((p for p in self.candidate_proposals if p.proposal_id == proposal_id), None)
        try:
            async with get_session() as session:
                if not target_prop:
                    config_key = f"candidate_alpha_{proposal_id}"
                    row = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == config_key)
                    )).scalar_one_or_none()
                    if row and row.value:
                        d = json.loads(row.value)
                        target_prop = CandidateAlphaProposal(
                            proposal_id=d["proposal_id"],
                            hypothesis=AlphaHypothesis(**d["hypothesis"]),
                            overall_wfe=d["overall_wfe"],
                            aggregate_is_sharpe=d["aggregate_is_sharpe"],
                            aggregate_oos_sharpe=d["aggregate_oos_sharpe"],
                            total_oos_trades=d["total_oos_trades"],
                            oos_win_rate_pct=d["oos_win_rate_pct"],
                            is_overfit=d["is_overfit"],
                            status="PAPER_ACTIVE",
                            markdown_report=d.get("markdown_report", ""),
                            max_drawdown_pct=d.get("max_drawdown_pct", 0.0)
                        )

                if not target_prop:
                    logger.warning(f"[AlphaDiscovery] Cannot find proposal {proposal_id} to promote.")
                    return False

                target_prop.status = "PAPER_ACTIVE"
                await self._persist_proposal(target_prop)
                logger.debug(f"[AlphaDiscovery] Promoted proposal {proposal_id} to PAPER_ACTIVE and hot-reloaded.")
                return True
        except Exception as e:
            logger.warning(f"[AlphaDiscovery] Promotion failed for {proposal_id}: {e}")
            return False


    async def run_discovery_cycle(self, max_evaluations: int = 5) -> List[CandidateAlphaProposal]:
        """
        Runs one cycle of autonomous alpha exploration across untried hypotheses.
        """
        all_hypotheses = self.generate_hypotheses()
        untried = [h for h in all_hypotheses if h.hypothesis_id not in self._evaluated_hypothesis_ids]

        if not untried:
            logger.debug("[AlphaDiscovery] All hypotheses evaluated. Resetting tracking cache.")
            self._evaluated_hypothesis_ids.clear()
            untried = all_hypotheses

        batch = untried[:max_evaluations]
        logger.debug(f"[AlphaDiscovery] Starting discovery cycle with {len(batch)} hypotheses...")

        found_proposals: List[CandidateAlphaProposal] = []
        for hyp in batch:
            self._evaluated_hypothesis_ids.add(hyp.hypothesis_id)
            proposal = await self.evaluate_hypothesis(hyp)
            if proposal:
                found_proposals.append(proposal)

        logger.debug(
            f"[AlphaDiscovery] Discovery cycle complete: {len(found_proposals)} "
            f"new qualified alpha proposals discovered."
        )
        return found_proposals

    async def start(self) -> None:
        """Main autonomous scheduler loop."""
        if not self.enabled:
            logger.info("AlphaDiscoveryScheduler is disabled via configuration.")
            return
        self._running = True
        logger.info(f"AlphaDiscoveryScheduler started (interval: {self.interval_hours}h)")

        if self.recovery_event:
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=120.0)
                logger.info("AlphaDiscoveryScheduler: Recovery complete, ready to operate.")
            except asyncio.TimeoutError:
                logger.debug("AlphaDiscoveryScheduler: Recovery wait timed out (120s), proceeding.")

        while self._running:
            try:
                await self.run_discovery_cycle()
            except Exception as e:
                logger.error(f"AlphaDiscoveryScheduler cycle error: {e}", exc_info=True)

            sleep_seconds = self.interval_hours * 3600
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        logger.info("AlphaDiscoveryScheduler stopped.")
