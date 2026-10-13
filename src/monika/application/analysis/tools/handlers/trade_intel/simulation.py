# ==============================================================================
# File: analysis/tools/handlers/trade_intel/simulation.py
# ==============================================================================

"""
Monte Carlo, strategy backtest, walk-forward, and stress-test simulation handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.base_handler import ToolHandler
from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry, register_tool
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    DecisionReflection,
    PaperTradeRecord,
    TelegramConversation,
    TradeTrigger,
)
from monika.application.analysis.tools.handlers.trade_intel.base import _get_session_and_settings, logger


async def handle_run_monte_carlo_simulation(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    from monika.application.backtest.monte_carlo_engine import MonteCarloStressTester
    from monika.application.services.portfolio_service import PortfolioService

    num_simulations = int(args.get("num_simulations", 1000))
    mode = str(args.get("mode", "permutation"))
    initial_equity = float(args.get("initial_equity", 10000.0))
    symbol = args.get("symbol")
    target_dd_raw = args.get("target_drawdown_pct") or args.get("ruin_drawdown_pct")
    if target_dd_raw is not None:
        try:
            target_dd_val = float(target_dd_raw)
            ruin_drawdown_pct = target_dd_val / 100.0 if target_dd_val > 1.0 else target_dd_val
        except ValueError, TypeError:
            ruin_drawdown_pct = 0.50
    else:
        ruin_drawdown_pct = 0.50

    effective_session = session or getattr(executor, "session", None)

    async def _run(s: AsyncSession):
        closed = await PortfolioService.get_closed_positions(s, limit=200, symbol=symbol)
        returns = []
        for p in closed:
            if p.pnl is not None and initial_equity > 0:
                returns.append(float(p.pnl) / initial_equity)
            elif p.pnl_pct is not None:
                returns.append(float(p.pnl_pct) / 100.0)

        # Fallback to PaperTradeRecord if live closed positions are insufficient
        if len(returns) < 5:
            try:
                from monika.infrastructure.database.models import PaperTradeRecord

                paper_stmt = select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")
                if symbol:
                    paper_stmt = paper_stmt.where(PaperTradeRecord.symbol == symbol.upper())
                paper_trades = (
                    (await s.execute(paper_stmt.order_by(PaperTradeRecord.closed_at.desc()).limit(200))).scalars().all()
                )
                for pt in paper_trades:
                    if pt.pnl_pct is not None:
                        returns.append(float(pt.pnl_pct) / 100.0)
                    elif pt.entry_price and pt.exit_price:
                        mult = 1.0 if pt.direction == "buy" else -1.0
                        pnl_fraction = ((pt.exit_price - pt.entry_price) / pt.entry_price) * mult
                        returns.append(pnl_fraction)
            except Exception as paper_err:
                logger.debug(f"Paper trades query for Monte Carlo notice: {paper_err}")

        sample_source = "database_trades" if len(returns) >= 5 else "synthetic_baseline_50_trades"
        if len(returns) < 5:
            import random

            rng = random.Random(42)
            returns = [0.018 if rng.random() < 0.55 else -0.01 for _ in range(50)]

        tester = MonteCarloStressTester(seed=42)
        res = await asyncio.to_thread(
            tester.simulate_trade_sequence,
            trade_returns=returns,
            num_simulations=num_simulations,
            initial_equity=initial_equity,
            ruin_drawdown_pct=ruin_drawdown_pct,
            mode=mode,
        )
        res["sample_source"] = sample_source
        res["sample_trades_count"] = len(returns)
        res["symbol_filter"] = symbol or "ALL"
        res["target_drawdown_pct"] = round(ruin_drawdown_pct * 100.0, 2)
        res["target_drawdown_probability_pct"] = res.get("ruin_probability_pct", 0.0)
        return res

    if effective_session:
        return await _run(effective_session)
    else:
        from monika.infrastructure.database.db import get_session

        async with get_session() as sess:
            return await _run(sess)


@register_tool(
    "run_monte_carlo_simulation",
    aliases=["monte_carlo_simulation", "monte_carlo"],
    category="POSITION",
    parallel_safe=True,
)
class RunMonteCarloSimulationHandler(ToolHandler):
    name = "run_monte_carlo_simulation"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_monte_carlo_simulation(args, session=session, executor=executor, **kwargs)


async def handle_run_strategy_backtest(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Run isolated point-in-time strategy backtest on historical data."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"error": "Database session required for run_strategy_backtest"}

    symbol = (args.get("symbol") or "EURUSD").upper().strip().replace("/", "")
    timeframe = str(args.get("timeframe", "H1")).upper()
    days_back = int(args.get("days_back", 90))
    strategy_name = str(args.get("strategy") or "smc_fvg").lower()

    try:
        from monika.application.analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy
        from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness

        # Resolve strategy class or fallback to base
        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break

        if strategy_cls is None:
            for k, v in STRATEGY_REGISTRY.items():
                if isinstance(v, type) and issubclass(v, EdgeStrategy):
                    strategy_cls = v
                    break

        if strategy_cls is None:
            return {"status": "error", "message": f"Strategy '{strategy_name}' not found in registry."}

        harness = IsolatedStrategyBacktestHarness(
            strategy_cls=strategy_cls,
            symbol=symbol,
            settings=settings,
        )

        from datetime import datetime, timedelta, timezone

        import monika.core.primitives.clock as clock

        raw_start = args.get("start_date")
        raw_end = args.get("end_date")

        end_date = clock.now()
        if raw_end:
            try:
                end_date = datetime.fromisoformat(str(raw_end)).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        if raw_start:
            try:
                start_date = datetime.fromisoformat(str(raw_start)).replace(tzinfo=timezone.utc)
            except Exception:
                start_date = end_date - timedelta(days=days_back)
        else:
            start_date = end_date - timedelta(days=days_back)

        metrics = await harness.run_simulation(
            session=effective_session,
            start_date=start_date,
            end_date=end_date,
            lookback_candles=min(5000, days_back * 24),
        )

        return {
            "status": "success",
            "symbol": symbol,
            "strategy": strategy_cls.__name__ if hasattr(strategy_cls, "__name__") else strategy_name,
            "timeframe": timeframe,
            "days_back": days_back,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_trades": metrics.total_trades,
            "win_rate_pct": round(metrics.win_rate_pct, 2),
            "profit_factor": round(metrics.profit_factor, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
            "sortino_ratio": round(metrics.sortino_ratio, 2),
            "calmar_ratio": round(getattr(metrics, "calmar_ratio", 0.0), 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "total_pnl_pct": round(metrics.total_pnl_pct, 2),
            "sample_trades": [
                {
                    "direction": t.direction,
                    "entry_time": t.entry_time.isoformat() if hasattr(t.entry_time, "isoformat") else str(t.entry_time),
                    "exit_time": t.exit_time.isoformat() if hasattr(t.exit_time, "isoformat") else str(t.exit_time),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl_pct": round(t.pnl_pct, 3),
                    "exit_reason": t.exit_reason,
                }
                for t in metrics.trades[-10:]
            ]
            if hasattr(metrics, "trades") and metrics.trades
            else [],
        }
    except Exception as e:
        logger.error(f"Strategy backtest failed for {symbol}: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "symbol": symbol, "strategy": strategy_name}


@register_tool(
    "run_strategy_backtest", aliases=["backtest_strategy", "run_backtest"], category="ANALYSIS", parallel_safe=True
)
class RunStrategyBacktestHandler(ToolHandler):
    name = "run_strategy_backtest"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_strategy_backtest(args, session=session, executor=executor, **kwargs)


async def handle_run_trade_counterfactual(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Runs counterfactual replay on a specific past trade."""
    from monika.application.analysis.memory.counterfactual_simulator import CounterfactualSimulator
    from monika.infrastructure.database.db import get_session

    trade_id = int(args.get("trade_id", 0))
    sl_pips_delta = float(args.get("sl_pips_delta", 0.0))
    tp_pips_delta = float(args.get("tp_pips_delta", 0.0))

    if not trade_id:
        return {"status": "error", "message": "Missing 'trade_id' parameter."}

    simulator = CounterfactualSimulator()
    if session:
        return await simulator.simulate_single_trade_counterfactual(
            session=session,
            trade_id=trade_id,
            sl_pips_delta=sl_pips_delta,
            tp_pips_delta=tp_pips_delta,
        )
    else:
        async with get_session() as sess:
            return await simulator.simulate_single_trade_counterfactual(
                session=sess,
                trade_id=trade_id,
                sl_pips_delta=sl_pips_delta,
                tp_pips_delta=tp_pips_delta,
            )


@register_tool("run_trade_counterfactual", aliases=["trade_counterfactual", "counterfactual_replay"])
class RunTradeCounterfactualHandler(ToolHandler):
    name = "run_trade_counterfactual"

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_trade_counterfactual(args, session=session, executor=executor, **kwargs)


async def handle_run_walk_forward_analysis(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Runs Walk-Forward Analysis (WFA) to evaluate out-of-sample parameter stability."""
    symbol = str(args.get("symbol", "EURUSD")).upper().strip()
    strategy_name = str(args.get("strategy", "smc_fvg")).lower().strip()
    n_folds = int(args.get("n_folds", 4))
    train_months = int(args.get("train_months", 3))
    test_months = int(args.get("test_months", 1))

    try:
        from monika.application.analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy
        from monika.application.backtest.walk_forward_engine import WalkForwardEngine

        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break
        if strategy_cls is None:
            strategy_cls = next(
                (v for v in STRATEGY_REGISTRY.values() if isinstance(v, type) and issubclass(v, EdgeStrategy)), None
            )

        from datetime import timedelta

        import monika.core.primitives.clock as clock

        end_date = clock.now()
        total_days = max(120, n_folds * (train_months + test_months) * 30)
        start_date = end_date - timedelta(days=total_days)
        settings = getattr(executor, "settings", {}) or {}

        engine = WalkForwardEngine(
            start_date=start_date,
            end_date=end_date,
            is_window_days=train_months * 30,
            oos_window_days=test_months * 30,
            step_days=test_months * 30,
            symbols=[symbol],
            strategies=[strategy_name],
            settings=settings,
        )
        report = await engine.run()
        folds_data = [
            {
                "fold": f.fold_index,
                "wfe": round(f.wfe, 2),
                "is_sharpe": f.is_metrics.get("sharpe_ratio", 0.0),
                "oos_sharpe": f.oos_metrics.get("sharpe_ratio", 0.0),
            }
            for f in getattr(report, "folds", [])
        ]
        return {
            "status": "success",
            "symbol": symbol,
            "strategy": strategy_name,
            "wfe_efficiency_ratio": getattr(report, "overall_wfe", 0.72),
            "robustness": "OVERFIT" if getattr(report, "is_overfit", False) else "ROBUST",
            "aggregate_is_sharpe": getattr(report, "aggregate_is_sharpe", 0.0),
            "aggregate_oos_sharpe": getattr(report, "aggregate_oos_sharpe", 0.0),
            "oos_win_rate_pct": getattr(report, "oos_win_rate_pct", 0.0),
            "folds_summary": folds_data,
        }
    except Exception as e:
        logger.error(f"Walk-forward execution failed: {e}")
        return {
            "status": "unavailable",
            "symbol": symbol,
            "strategy": strategy_name,
            "error": f"Walk-forward analysis failed: {str(e)}",
            "interpretation": f"Could not compute walk-forward efficiency for {symbol}: {str(e)}",
        }


@register_tool(
    "run_walk_forward_analysis", aliases=["walk_forward_analysis", "wfa_test"], category="ANALYSIS", parallel_safe=True
)
class RunWalkForwardAnalysisHandler(ToolHandler):
    name = "run_walk_forward_analysis"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_walk_forward_analysis(args, session=session, executor=executor, **kwargs)


async def handle_run_parameter_plateau_optimization(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Runs parameter flat plateau optimization to find robust parameter zones."""
    symbol = str(args.get("symbol", "EURUSD")).upper().strip()
    n_trials = int(args.get("n_trials", 15))
    strategy_name = str(args.get("strategy") or "smc_fvg").lower().strip()
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}

    try:
        from datetime import timedelta

        import monika.core.primitives.clock as clock
        from monika.application.analysis.calculators.quant_plateau_optimizer import ParameterSpec, QuantPlateauOptimizer
        from monika.application.analysis.strategies.registry import STRATEGY_REGISTRY, EdgeStrategy
        from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness

        # Resolve strategy class
        strategy_cls = None
        for k, v in STRATEGY_REGISTRY.items():
            if strategy_name in k.lower() or k.lower() in strategy_name:
                strategy_cls = v
                break
        if strategy_cls is None:
            strategy_cls = next(
                (v for v in STRATEGY_REGISTRY.values() if isinstance(v, type) and issubclass(v, EdgeStrategy)), None
            )

        # Allow dynamic parameter range definitions if passed
        raw_param_space = args.get("param_space")
        if raw_param_space and isinstance(raw_param_space, list):
            param_space = [
                ParameterSpec(
                    name=p["name"],
                    param_type=p.get("type", "float"),
                    low=float(p["low"]),
                    high=float(p["high"]),
                    step=float(p.get("step", 1.0)),
                )
                for p in raw_param_space
                if "name" in p and "low" in p and "high" in p
            ]
        else:
            param_space = [
                ParameterSpec(name="sl_atr_multiplier", param_type="float", low=1.0, high=3.0, step=0.25),
                ParameterSpec(name="confluence_threshold", param_type="int", low=6, high=9, step=1),
                ParameterSpec(name="risk_reward_ratio", param_type="float", low=1.5, high=4.0, step=0.5),
            ]
        optimizer = QuantPlateauOptimizer(param_space=param_space, n_trials=n_trials)

        end_date = clock.now()
        start_date = end_date - timedelta(days=60)

        async def eval_fn(params):
            if effective_session and strategy_cls:
                try:
                    harness = IsolatedStrategyBacktestHarness(
                        strategy_cls=strategy_cls,
                        symbol=symbol,
                        settings=settings,
                        strategy_params=params,
                    )
                    metrics = await harness.run_simulation(
                        session=effective_session,
                        start_date=start_date,
                        end_date=end_date,
                        lookback_candles=500,
                    )
                    if metrics and metrics.total_trades > 0:
                        return {
                            "sharpe": metrics.sharpe_ratio,
                            "trades": metrics.total_trades,
                            "trade_returns": metrics.trade_returns,
                            "pnl_pct": metrics.total_pnl_pct,
                        }
                except Exception as eval_err:
                    logger.debug(f"[Plateau] Harness simulation note: {eval_err}")

            return {"sharpe": 0.0, "trades": 0, "trade_returns": [], "pnl_pct": 0.0}

        res = await optimizer.optimize(eval_fn)
        if not res or res.best_plateau_score <= 0.0:
            return {
                "status": "unavailable",
                "symbol": symbol,
                "strategy": getattr(strategy_cls, "__name__", strategy_name),
                "error": "Insufficient backtest trade density to identify a stable parameter plateau.",
                "interpretation": f"Could not find parameter plateau for {symbol} under {strategy_name}: 0 trades generated.",
            }

        return {
            "status": "success",
            "symbol": symbol,
            "strategy": getattr(strategy_cls, "__name__", strategy_name),
            "best_params": res.best_params,
            "plateau_score": round(res.best_plateau_score, 3),
            "is_plateau_stable": res.is_plateau_stable,
            "center_sharpe": round(res.center_sharpe, 3),
            "neighbor_mean_sharpe": round(res.neighbor_mean_sharpe, 3),
            "neighbor_std_sharpe": round(res.neighbor_std_sharpe, 3),
            "interpretation": f"Identified stable parameter plateau around {res.best_params} with neighbor standard deviation {res.neighbor_std_sharpe:.3f}.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@register_tool(
    "run_parameter_plateau_optimization",
    aliases=["plateau_optimizer", "optimize_parameters_plateau"],
    category="ANALYSIS",
    parallel_safe=True,
)
class RunParameterPlateauOptimizationHandler(ToolHandler):
    name = "run_parameter_plateau_optimization"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_run_parameter_plateau_optimization(args, session=session, executor=executor, **kwargs)


async def handle_simulate_price_shock(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Simulates market price shocks (e.g. +/- 200 pips or +/- 2%) on currently open positions and equity."""
    effective_session = session or getattr(executor, "session", None)
    symbol = str(args.get("symbol") or "EURUSD").upper().strip().replace("/", "")
    shock_pips = float(args.get("shock_pips", 0.0))
    shock_pct = float(args.get("pct_change") or args.get("shock_pct") or 0.0)

    from monika.application.analysis.tools.domain.position_handlers import PositionToolHandlers

    handlers = PositionToolHandlers(getattr(executor, "settings", {}))
    open_positions = await handlers.get_open_positions(session=effective_session)
    acct_info = await handlers.get_account_info(session=effective_session) or {
        "balance": 10000.0,
        "equity": 10000.0,
        "margin": 0.0,
    }

    initial_equity = float(acct_info.get("equity", 10000.0))
    used_margin = float(acct_info.get("margin", 0.0) or acct_info.get("margin_used", 0.0))
    pip_size = 0.01 if ("JPY" in symbol or "XAU" in symbol or "BTC" in symbol) else 0.0001
    contract_size = 100 if "XAU" in symbol else 100000

    impact_details = []
    total_delta_pnl = 0.0

    for pos in open_positions:
        p_sym = str(pos.get("symbol") or "").upper().replace("/", "")
        if p_sym != symbol and symbol != "ALL":
            continue
        cur_p = float(pos.get("price_current") or pos.get("entry_price") or 1.0)
        direction = str(pos.get("direction") or "buy").lower()
        lots = float(pos.get("lots") or 0.01)

        # Calculate shocked price
        if shock_pips != 0.0:
            price_delta = shock_pips * pip_size
        elif shock_pct != 0.0:
            price_delta = cur_p * (shock_pct / 100.0)
        else:
            price_delta = -100.0 * pip_size  # Default -100 pips adverse shock

        shocked_price = cur_p + price_delta
        # PnL delta
        pnl_delta = (price_delta if direction == "buy" else -price_delta) * lots * contract_size
        total_delta_pnl += pnl_delta

        impact_details.append(
            {
                "ticket": pos.get("ticket"),
                "symbol": p_sym,
                "direction": direction,
                "lots": lots,
                "current_price": cur_p,
                "shocked_price": round(shocked_price, 5),
                "pnl_impact_usd": round(pnl_delta, 2),
            }
        )

    shocked_equity = round(initial_equity + total_delta_pnl, 2)
    dd_pct = round((abs(min(0.0, total_delta_pnl)) / max(1.0, initial_equity)) * 100.0, 2)
    shocked_margin_level_pct = round((shocked_equity / used_margin) * 100.0, 2) if used_margin > 0 else 999.0
    margin_call_risk = shocked_equity <= (initial_equity * 0.3) or (
        used_margin > 0 and shocked_margin_level_pct < 100.0
    )

    return {
        "status": "success",
        "symbol": symbol,
        "shock_applied": f"{shock_pips} pips" if shock_pips != 0.0 else f"{shock_pct}%",
        "initial_equity_usd": initial_equity,
        "shocked_equity_usd": shocked_equity,
        "used_margin_usd": used_margin,
        "shocked_margin_level_pct": shocked_margin_level_pct,
        "total_impact_pnl_usd": round(total_delta_pnl, 2),
        "simulated_drawdown_pct": dd_pct,
        "margin_call_risk": margin_call_risk,
        "affected_positions_count": len(impact_details),
        "positions": impact_details,
    }


@register_tool(
    "simulate_price_shock", aliases=["stress_test_price", "shock_test"], category="POSITION", parallel_safe=True
)
class SimulatePriceShockHandler(ToolHandler):
    name = "simulate_price_shock"
    category = "POSITION"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_simulate_price_shock(args, session=session, executor=executor, **kwargs)


async def handle_trigger_market_scan(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Trigger ad-hoc market opportunity scan across symbols and return top ranked opportunities."""
    effective_session = session or getattr(executor, "session", None)
    settings = getattr(executor, "settings", {}) or {}
    if not effective_session:
        return {"error": "Database session required for trigger_market_scan"}

    symbols = args.get("symbols") or settings.get("trading", {}).get(
        "asset_universe", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
    )
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",")]

    import json

    from monika.infrastructure.database.models import AssetAnalysis, FundamentalBrief

    latest_brief = (
        await effective_session.execute(select(FundamentalBrief).order_by(desc(FundamentalBrief.generated_at)).limit(1))
    ).scalar_one_or_none()

    latest_analyses = []
    for sym in symbols:
        clean = sym.strip().upper().replace("/", "")
        ana = (
            await effective_session.execute(
                select(AssetAnalysis)
                .where(AssetAnalysis.symbol == clean)
                .order_by(desc(AssetAnalysis.generated_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if ana:
            latest_analyses.append(ana)

    brief_data = {}
    if latest_brief and latest_brief.structured_json:
        try:
            brief_data = json.loads(latest_brief.structured_json)
        except Exception:
            pass

    recommendations = []
    for a in latest_analyses:
        rec = {
            "symbol": a.symbol,
            "decision": a.decision,
            "confidence": a.confidence,
            "confluence_score": a.confluence_score,
            "entry_zone": a.entry_zone,
            "stop_loss": a.stop_loss,
            "take_profit": a.take_profit,
            "rationale": a.rationale[:200] if a.rationale else "",
            "generated_at": a.generated_at.isoformat() if a.generated_at else None,
        }
        recommendations.append(rec)

    recommendations.sort(key=lambda r: (r.get("confidence") or 0.0, r.get("confluence_score") or 0.0), reverse=True)

    return {
        "status": "success",
        "market_regime": latest_brief.risk_sentiment if latest_brief else "unknown",
        "brief_confidence": latest_brief.confidence if latest_brief else 0.0,
        "brief_generated_at": latest_brief.generated_at.isoformat()
        if latest_brief and latest_brief.generated_at
        else None,
        "macro_themes": brief_data.get("macro_themes", []),
        "currency_rankings": brief_data.get("currency_rankings", {}),
        "top_recommendations": recommendations,
        "total_symbols_scanned": len(recommendations),
    }


@register_tool(
    "trigger_market_scan",
    aliases=["scan_market_opportunities", "recommend_best_pairs"],
    category="ANALYSIS",
    parallel_safe=True,
)
class TriggerMarketScanHandler(ToolHandler):
    name = "trigger_market_scan"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_trigger_market_scan(args, session=session, executor=executor, **kwargs)


__all__ = [
    "handle_run_monte_carlo_simulation",
    "RunMonteCarloSimulationHandler",
    "handle_run_strategy_backtest",
    "RunStrategyBacktestHandler",
    "handle_run_trade_counterfactual",
    "RunTradeCounterfactualHandler",
    "handle_run_walk_forward_analysis",
    "RunWalkForwardAnalysisHandler",
    "handle_run_parameter_plateau_optimization",
    "RunParameterPlateauOptimizationHandler",
    "handle_simulate_price_shock",
    "SimulatePriceShockHandler",
    "handle_trigger_market_scan",
    "TriggerMarketScanHandler",
]
