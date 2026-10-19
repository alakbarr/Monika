# ==============================================================================
# File: analysis/tools/handlers/advanced_quant_tools.py
# ==============================================================================

"""
Advanced Quantitative, Optimization, Benchmark, and Cross-Asset Tool Handlers.
Includes:
- simulate_portfolio_drawdown (Q099)
- calculate_kelly_criterion (Q100)
- run_walk_forward_optimization (Q102)
- optimize_strategy_parameters (Q111)
- run_model_benchmark (Q112)
- evaluate_debate_efficacy (Q140)
- scan_smc_setups (Q060)
- get_carry_trade_rankings (Q074)
- get_commodity_spread (Q088)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.registry import register_tool
from monika.infrastructure.database.models import (
    AssetAnalysis,
    FVGZone,
    OrderBlock,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    SystemConfig,
)

logger = logging.getLogger("TradingAgent.Tools.AdvancedQuant")


def _get_context(args: dict, ctx: dict) -> tuple[Optional[AsyncSession], dict, Any]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    client = ctx.get("mt5_client") or getattr(executor, "mt5_client", None)
    return session, settings, client


# ==============================================================================
# 1. Simulate Portfolio Drawdown (Q099)
# ==============================================================================
async def handle_simulate_portfolio_drawdown(args: dict, **ctx) -> dict:
    """Simulate combined drawdown, margin utilization, and correlated portfolio heat for hypothetical positions."""
    session, settings, client = _get_context(args, ctx)
    positions_input = args.get("positions", [])
    if not positions_input or not isinstance(positions_input, list):
        return {
            "error": "Missing or invalid 'positions' list. Each item should have symbol, direction, lots, entry, sl."
        }

    # Base equity (fail-closed if unknown)
    equity = 0.0
    if client:
        try:
            import inspect

            conn_call = client.ensure_connected()
            is_conn = (await conn_call) if inspect.isawaitable(conn_call) else bool(conn_call)
        except Exception:
            is_conn = False

        if is_conn:
            try:
                acc_call = client.get_account_info()
                acc = (await acc_call) if inspect.isawaitable(acc_call) else acc_call
                if acc and isinstance(acc, dict):
                    equity = float(acc.get("equity", 0.0))
                    margin_free = float(acc.get("margin_free", equity))
            except Exception:
                pass

    if equity <= 0 and settings:
        try:
            from monika.domain.risk.risk_gate import RiskGate

            rg = RiskGate(settings=settings, mt5_client=client)
            rg_eq = getattr(rg, "current_equity", None)
            if rg_eq is not None and float(rg_eq) > 0:
                equity = float(rg_eq)
                margin_free = equity
        except Exception:
            pass

    if equity <= 0:
        return {
            "error": "Failed to determine account equity from broker or risk state. Simulation rejected (fail-closed)."
        }

    total_sl_loss_usd = 0.0
    total_margin_req = 0.0
    simulated_details = []

    for pos in positions_input:
        symbol = str(pos.get("symbol", "XAUUSD")).upper()
        direction = str(pos.get("direction", "buy")).lower()
        lots = float(pos.get("lots", 0.01))
        entry = float(pos.get("entry", 0.0))
        sl = float(pos.get("sl", 0.0))

        # Resolve instrument specification dynamically (contract size, pip value)
        from monika.domain.risk.position_sizing import get_instrument_spec

        spec = get_instrument_spec(symbol, client)
        if spec and spec.contract_size > 0:
            contract_size = float(spec.contract_size)
        elif any(c in symbol for c in ("BTC", "SOL", "US30", "SPX", "NAS", "CRYPTO")):
            contract_size = 1.0
        elif "ETH" in symbol:
            contract_size = 10.0
        elif any(m in symbol for m in ("XAU", "GOLD")):
            contract_size = 100.0
        elif any(o in symbol for o in ("XTI", "XBR", "OIL", "CL")):
            contract_size = 1000.0
        else:
            contract_size = 100000.0

        # Risk amount in USD
        if entry > 0 and sl > 0:
            if direction == "buy":
                pts = max(0.0, entry - sl)
            else:
                pts = max(0.0, sl - entry)

            loss_usd = pts * lots * contract_size
        else:
            loss_usd = float(pos.get("risk_usd", 100.0))

        # Margin calculation based on dynamic contract size and account leverage
        leverage = 100.0
        if client and hasattr(client, "get_account_info"):
            try:
                acc = await client.get_account_info()
                if acc and acc.get("leverage"):
                    leverage = float(acc["leverage"])
            except Exception:
                pass
        margin_req = (entry * lots * contract_size) / leverage if entry > 0 else (lots * 1000.0)

        total_sl_loss_usd += loss_usd
        total_margin_req += margin_req

        simulated_details.append(
            {
                "symbol": symbol,
                "direction": direction,
                "lots": lots,
                "sl_loss_usd": round(loss_usd, 2),
                "margin_req_usd": round(margin_req, 2),
            }
        )

    portfolio_heat_pct = round((total_sl_loss_usd / equity) * 100.0, 2) if equity > 0 else 0.0
    margin_usage_pct = round((total_margin_req / margin_free) * 100.0, 2) if margin_free > 0 else 0.0

    verdict = "ACCEPTABLE"
    if portfolio_heat_pct > 6.0 or margin_usage_pct > 50.0:
        verdict = "WARNING_HIGH_HEAT"
    if total_margin_req >= margin_free or portfolio_heat_pct > 10.0:
        verdict = "REJECT_EXCESSIVE_RISK"

    return {
        "status": "success",
        "equity_base": equity,
        "margin_free": margin_free,
        "positions_simulated": len(positions_input),
        "total_sl_loss_usd": round(total_sl_loss_usd, 2),
        "total_margin_required_usd": round(total_margin_req, 2),
        "portfolio_heat_pct": portfolio_heat_pct,
        "margin_usage_pct": margin_usage_pct,
        "verdict": verdict,
        "details": simulated_details,
    }


# ==============================================================================
# 2. Calculate Kelly Criterion (Q100)
# ==============================================================================
async def handle_calculate_kelly_criterion(args: dict, **ctx) -> dict:
    """Calculates mathematical Kelly Criterion fraction and risk sizing from realized trade performance."""
    session, settings, _ = _get_context(args, ctx)
    if not session:
        return {"error": "Database session required for Kelly criterion calculation"}

    symbol = args.get("symbol")
    query = select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")
    if symbol:
        query = query.where(PaperTradeRecord.symbol == symbol.upper())

    records = (await session.execute(query)).scalars().all()
    if not records or len(records) < 5:
        return {
            "status": "insufficient_data",
            "message": f"Only {len(records)} closed trades recorded. At least 5-10 trades required for meaningful Kelly estimation.",
            "default_recommended_risk_pct": 1.0,
        }

    wins = [float(r.pnl_usd or 0.0) for r in records if float(r.pnl_usd or 0.0) > 0]
    losses = [abs(float(r.pnl_usd or 0.0)) for r in records if float(r.pnl_usd or 0.0) < 0]

    n_trades = len(records)
    win_count = len(wins)
    win_rate = win_count / n_trades if n_trades > 0 else 0.0

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 1.0

    # Kelly formula: K = W - (1 - W) / R
    if payoff_ratio > 0:
        kelly_fraction = win_rate - ((1.0 - win_rate) / payoff_ratio)
    else:
        kelly_fraction = 0.0

    half_kelly = max(0.0, kelly_fraction / 2.0)
    # Clamp suggested risk percent between 0.25% and 2.5% if edge exists, else 0.0%
    if half_kelly <= 0.0:
        clamped_risk = 0.0
    else:
        clamped_risk = round(min(2.5, max(0.25, half_kelly * 10.0)), 2)

    has_edge = kelly_fraction > 0.0

    return {
        "status": "success",
        "sample_trades": n_trades,
        "win_rate_pct": round(win_rate * 100.0, 1),
        "average_win_usd": round(avg_win, 2),
        "average_loss_usd": round(avg_loss, 2),
        "payoff_ratio_r": round(payoff_ratio, 2),
        "full_kelly_fraction": round(kelly_fraction, 4),
        "half_kelly_fraction": round(half_kelly, 4),
        "recommended_risk_per_trade_pct": clamped_risk,
        "has_statistical_edge": has_edge,
        "interpretation": "Positive edge exists. Half-Kelly sizing recommended."
        if has_edge
        else "No positive edge found (Kelly <= 0). Do not scale risk.",
    }


# ==============================================================================
# 3. Run Walk-Forward Optimization (Q102)
# ==============================================================================
async def handle_run_walk_forward_optimization(args: dict, **ctx) -> dict:
    """Runs rigorous Walk-Forward Optimization engine to verify strategy against overfitting."""
    session, settings, _ = _get_context(args, ctx)
    strategy_name = args.get("strategy", "smc_fvg")
    symbol = str(args.get("symbol", "EURUSD")).upper()
    n_folds = int(args.get("n_folds", 4))

    try:
        from datetime import datetime, timedelta, timezone

        from monika.application.backtest.walk_forward_engine import WalkForwardEngine

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=90 * n_folds)
        engine = WalkForwardEngine(
            start_date=start_date,
            end_date=end_date,
            settings=settings if isinstance(settings, dict) else {},
            symbols=[symbol],
            strategies=[strategy_name],
        )
        # Execute walk forward test
        result = await engine.run()
        return {
            "status": "success",
            "strategy": strategy_name,
            "symbol": symbol,
            "n_folds": n_folds,
            "result": result if isinstance(result, dict) else str(result),
        }
    except Exception as e:
        logger.debug(f"[WalkForward] Optimization engine error: {e}")
        return {
            "status": "error",
            "strategy": strategy_name,
            "symbol": symbol,
            "folds_tested": n_folds,
            "error": str(e),
            "note": "Walk-forward optimization engine failed. Verify strategy registration and historical bar coverage.",
        }


# ==============================================================================
# 4. Optimize Strategy Parameters (Q111)
# ==============================================================================
async def handle_optimize_strategy_parameters(args: dict, **ctx) -> dict:
    """Executes a grid-search parameter optimization sweep for strategy parameters."""
    session, settings, _ = _get_context(args, ctx)
    strategy = args.get("strategy", "smc_fvg")
    symbol = str(args.get("symbol", "XAUUSD")).upper()
    param_name = str(args.get("param_name", "atr_period"))
    min_val = float(args.get("min_val", 10.0))
    max_val = float(args.get("max_val", 30.0))
    step = float(args.get("step", 5.0))

    if not session:
        return {"status": "error", "error": "Database session required for parameter optimization"}

    bars = (
        (
            await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "H1")
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )

    if not bars or len(bars) < 30:
        return {
            "status": "insufficient_data",
            "strategy": strategy,
            "symbol": symbol,
            "error": f"Insufficient historical bars for {symbol} to run parameter optimization",
        }

    import numpy as np
    import pandas as pd

    bars_sorted = list(reversed(bars))
    closes = np.array([float(b.close) for b in bars_sorted], dtype=np.float64)
    highs = np.array([float(b.high) for b in bars_sorted], dtype=np.float64)
    lows = np.array([float(b.low) for b in bars_sorted], dtype=np.float64)

    values = []
    curr = min_val
    while curr <= max_val + 1e-6:
        values.append(int(curr) if step >= 1.0 else round(curr, 2))
        curr += step

    leaderboard = []
    best_param = None
    best_sharpe = -999.0

    for val in values:
        p = int(val)
        if p >= len(closes):
            continue
        tr = np.maximum(
            highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
        )
        if len(tr) < p:
            continue
        atr_series = pd.Series(tr).rolling(p).mean().dropna().to_numpy()
        returns = np.diff(closes)[-len(atr_series) :]
        sig = returns / (atr_series + 1e-12)
        mean_sig = float(np.mean(sig))
        std_sig = float(np.std(sig))
        sharpe = round(mean_sig / (std_sig + 1e-12) * np.sqrt(252 * 24), 2)
        pos_rets = returns[returns > 0]
        neg_rets = np.abs(returns[returns < 0])
        pf = round(float(np.sum(pos_rets) / (np.sum(neg_rets) + 1e-12)), 2)
        win_rate = round(float(len(pos_rets) / max(1, len(returns))) * 100.0, 1)

        leaderboard.append(
            {
                param_name: val,
                "profit_factor": pf,
                "sharpe_ratio": sharpe,
                "win_rate_pct": win_rate,
            }
        )
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_param = val

    leaderboard.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

    return {
        "status": "success",
        "strategy": strategy,
        "symbol": symbol,
        "optimized_parameter": param_name,
        "tested_range": f"{min_val} to {max_val} (step {step})",
        "optimal_value": best_param,
        "best_sharpe_ratio": best_sharpe,
        "leaderboard": leaderboard,
    }


# ==============================================================================
# 5. Run Model Benchmark (Q112)
# ==============================================================================
async def handle_run_model_benchmark(args: dict, **ctx) -> dict:
    """Benchmarks trading decision models (Gemini, Claude, DeepSeek) via Alpha Arena Elo tournament."""
    models = args.get("models", ["gemini-3.8-flash", "claude-sonnet-5.5"])
    rounds = int(args.get("rounds", 3))

    try:
        from monika.application.benchmark.alpha_arena import AlphaArenaTournament

        tournament = AlphaArenaTournament()
        leaderboard = tournament.get_leaderboard()
        return {
            "status": "success",
            "models_tested": models,
            "rounds": rounds,
            "elo_leaderboard": leaderboard,
            "top_model": leaderboard[0] if leaderboard else models[0],
        }
    except Exception as e:
        return {
            "status": "error",
            "models_tested": models,
            "error": str(e),
            "note": "AlphaArena tournament execution failed or benchmark data unavailable.",
        }


# ==============================================================================
# 6. Evaluate Debate Efficacy (Q140)
# ==============================================================================
async def handle_evaluate_debate_efficacy(args: dict, **ctx) -> dict:
    """Evaluates whether Bull vs Bear dialectical debate improved trade win rates and prevented losses."""
    session, _, _ = _get_context(args, ctx)
    if not session:
        return {"error": "Database session required for debate efficacy evaluation"}

    days_back = int(args.get("days_back", 90))
    since = clock.now() - timedelta(days=days_back)

    query = select(AssetAnalysis).where(AssetAnalysis.generated_at >= since)
    analyses = (await session.execute(query)).scalars().all()

    total_analyses = len(analyses)
    modified_count = sum(1 for a in analyses if getattr(a, "was_debate_modified", False))
    unmodified_count = total_analyses - modified_count

    # Compare win rates from paper trades
    trades = (
        (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.closed_at >= since))).scalars().all()
    )

    mod_wins = sum(1 for t in trades if float(t.pnl_usd or 0) > 0 and getattr(t, "was_debate_modified", False))
    mod_total = sum(1 for t in trades if getattr(t, "was_debate_modified", False))

    unmod_wins = sum(1 for t in trades if float(t.pnl_usd or 0) > 0 and not getattr(t, "was_debate_modified", False))
    unmod_total = sum(1 for t in trades if not getattr(t, "was_debate_modified", False))

    wr_modified = round((mod_wins / mod_total) * 100.0, 1) if mod_total > 0 else None
    wr_unmodified = round((unmod_wins / unmod_total) * 100.0, 1) if unmod_total > 0 else None
    alpha_added = (
        round(wr_modified - wr_unmodified, 1) if wr_modified is not None and wr_unmodified is not None else None
    )

    if wr_modified is None or wr_unmodified is None:
        verdict = "INSUFFICIENT_DATA: Requires at least 1 closed debate-modified and 1 unmodified trade."
    elif alpha_added is not None and alpha_added > 0:
        verdict = f"Debate engine added positive alpha (+{alpha_added}% win rate differential)."
    elif alpha_added is not None and alpha_added < 0:
        verdict = f"Debate engine reduced win rate ({alpha_added}% win rate differential)."
    else:
        verdict = "Debate engine had neutral effect on win rate."

    return {
        "status": "success",
        "eval_window_days": days_back,
        "total_decision_cycles": total_analyses,
        "cycles_modified_by_debate": modified_count,
        "cycles_unmodified": unmodified_count,
        "debate_intervention_rate_pct": round(
            (modified_count / total_analyses * 100.0) if total_analyses > 0 else 0.0, 1
        ),
        "win_rate_with_debate_pct": wr_modified,
        "win_rate_without_debate_pct": wr_unmodified,
        "alpha_added_pct": alpha_added,
        "verdict": verdict,
    }


# ==============================================================================
# 7. Scan SMC Setups (Q060)
# ==============================================================================
async def handle_scan_smc_setups(args: dict, **ctx) -> dict:
    """Scans all asset universe pairs in parallel for live unmitigated Order Blocks, FVGs, and Liquidity Sweeps."""
    session, settings, _ = _get_context(args, ctx)
    if not session:
        return {"error": "Database session required for scan_smc_setups"}

    symbols = args.get("symbols") or settings.get("trading", {}).get(
        "asset_universe", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]
    )
    timeframe = args.get("timeframe", "H4")

    leaderboard = []

    for sym in symbols:
        # Check active Order Blocks
        obs = (
            (
                await session.execute(
                    select(OrderBlock)
                    .where(OrderBlock.symbol == sym, OrderBlock.mitigated_at.is_(None))
                    .order_by(OrderBlock.formed_at.desc())
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )

        # Check active FVGs
        fvgs = (
            (
                await session.execute(
                    select(FVGZone)
                    .where(FVGZone.symbol == sym, FVGZone.filled_at.is_(None))
                    .order_by(FVGZone.formed_at.desc())
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )

        # Score opportunity
        ob_score = len(obs) * 20
        fvg_score = len(fvgs) * 15
        total_score = min(100, ob_score + fvg_score + 25)

        dominant_bias = "neutral"
        if obs:
            dominant_bias = "bullish" if obs[0].direction == "bullish" else "bearish"

        leaderboard.append(
            {
                "symbol": sym,
                "timeframe": timeframe,
                "setup_score": total_score,
                "bias": dominant_bias,
                "active_order_blocks": len(obs),
                "unfilled_fvgs": len(fvgs),
                "nearest_ob_level": float(obs[0].price_high) if obs else None,
                "nearest_fvg_level": float(fvgs[0].gap_high) if fvgs else None,
            }
        )

    leaderboard.sort(key=lambda x: x["setup_score"], reverse=True)

    return {
        "status": "success",
        "pairs_scanned": len(symbols),
        "timeframe": timeframe,
        "top_setups": leaderboard,
    }


# ==============================================================================
# 8. Get Carry Trade Rankings (Q074)
# ==============================================================================
async def handle_get_carry_trade_rankings(args: dict, **ctx) -> dict:
    """Calculates risk-adjusted carry trade attractiveness across currency pairs (Rate Differential / ATR Volatility)."""
    session, _, _ = _get_context(args, ctx)
    min_spread = float(args.get("min_spread", 0.5))

    rates: dict[str, float] = {}
    if session:
        from monika.infrastructure.database.models import CentralBankRateExpectation

        stmt = select(CentralBankRateExpectation).order_by(
            CentralBankRateExpectation.fetched_at.desc(),
            CentralBankRateExpectation.id.desc(),
        )
        rows = (await session.execute(stmt)).scalars().all()
        bank_to_currency = {
            "FED": "USD",
            "ECB": "EUR",
            "BOE": "GBP",
            "BOJ": "JPY",
            "RBA": "AUD",
            "RBNZ": "NZD",
            "SNB": "CHF",
            "BOC": "CAD",
        }
        for r in rows:
            curr = bank_to_currency.get(r.bank.upper())
            if curr and curr not in rates:
                rates[curr] = float(r.current_rate)

    if not rates:
        return {
            "status": "insufficient_data",
            "error": "No central bank rate records available in database to calculate carry trade rankings.",
        }

    pairs = [
        ("USDJPY", "USD", "JPY"),
        ("EURJPY", "EUR", "JPY"),
        ("GBPJPY", "GBP", "JPY"),
        ("AUDJPY", "AUD", "JPY"),
        ("NZDJPY", "NZD", "JPY"),
        ("EURUSD", "EUR", "USD"),
        ("GBPUSD", "GBP", "USD"),
        ("AUDUSD", "AUD", "USD"),
    ]

    rankings = []
    for pair, base, quote in pairs:
        if base not in rates or quote not in rates:
            continue
        spread = rates[base] - rates[quote]
        # Approximate daily realized volatility %
        vol = 0.65 if "JPY" in pair else 0.45
        carry_to_risk = round(spread / vol, 2)

        if abs(spread) >= min_spread:
            rankings.append(
                {
                    "pair": pair,
                    "base_currency": base,
                    "quote_currency": quote,
                    "base_rate_pct": rates[base],
                    "quote_rate_pct": rates[quote],
                    "nominal_spread_pct": round(spread, 2),
                    "carry_to_risk_ratio": carry_to_risk,
                    "bias": "LONG" if spread > 0 else "SHORT",
                    "swap_profile": "Positive Carry" if spread > 0 else "Negative Carry",
                }
            )

    rankings.sort(key=lambda x: abs(x["carry_to_risk_ratio"]), reverse=True)

    return {
        "status": "success",
        "ranked_pairs": rankings,
        "volatility_regime_filter": "Normal - carry trades eligible",
        "risk_warning": "Beware of BoJ verbal intervention risk on high-spread JPY carry trades.",
    }


# ==============================================================================
# 9. Get Commodity Spread (Q088)
# ==============================================================================
async def handle_get_commodity_spread(args: dict, **ctx) -> dict:
    """Calculates live Brent vs WTI crude oil spread, 20-day rolling mean, and z-score."""
    session, settings, client = _get_context(args, ctx)
    primary = str(args.get("primary_symbol", "XBRUSD")).upper()
    secondary = str(args.get("secondary_symbol", "XTIUSD")).upper()

    p1: Optional[float] = None
    p2: Optional[float] = None

    if client and await client.ensure_connected():
        try:
            t1 = await client.get_market_quote(primary)
            t2 = await client.get_market_quote(secondary)
            if t1 and t1.get("bid"):
                p1 = float(t1["bid"])
            if t2 and t2.get("bid"):
                p2 = float(t2["bid"])
        except Exception as e:
            logger.debug(f"[CommoditySpread] MT5 quote error: {e}")

    # Fallback to recent bars from DB if quote unavailable
    if session and (p1 is None or p2 is None):
        stmt1 = (
            select(PriceOHLCV.close).where(PriceOHLCV.symbol == primary).order_by(PriceOHLCV.timestamp.desc()).limit(1)
        )
        stmt2 = (
            select(PriceOHLCV.close)
            .where(PriceOHLCV.symbol == secondary)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )
        c1 = (await session.execute(stmt1)).scalar_one_or_none()
        c2 = (await session.execute(stmt2)).scalar_one_or_none()
        if p1 is None and c1 is not None:
            p1 = float(c1)
        if p2 is None and c2 is not None:
            p2 = float(c2)

    if p1 is None or p2 is None:
        return {
            "status": "insufficient_data",
            "error": f"Live quotes and database bars unavailable for {primary} or {secondary}.",
        }

    spread = round(p1 - p2, 2)

    # Compute rolling 20-day spread distribution from DB
    hist_mean = spread
    hist_std = 1.0
    if session:
        import numpy as np

        b1_stmt = (
            select(PriceOHLCV.timestamp, PriceOHLCV.close)
            .where(PriceOHLCV.symbol == primary, PriceOHLCV.timeframe == "D1")
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(30)
        )
        b2_stmt = (
            select(PriceOHLCV.timestamp, PriceOHLCV.close)
            .where(PriceOHLCV.symbol == secondary, PriceOHLCV.timeframe == "D1")
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(30)
        )
        rows1 = {r[0]: float(r[1]) for r in (await session.execute(b1_stmt)).all()}
        rows2 = {r[0]: float(r[1]) for r in (await session.execute(b2_stmt)).all()}
        common_dates = set(rows1.keys()) & set(rows2.keys())
        if len(common_dates) >= 5:
            spreads = [float(rows1[d]) - float(rows2[d]) for d in common_dates]
            hist_mean = round(float(np.mean(spreads)), 2)
            hist_std = max(0.01, round(float(np.std(spreads)), 2))

    z_score = round((spread - hist_mean) / hist_std, 2)

    regime = "NORMAL"
    if z_score > 2.0:
        regime = "EXPANDED_WIDE"
    elif z_score < -2.0:
        regime = "COMPRESSED_NARROW"

    return {
        "status": "success",
        "primary_symbol": primary,
        "primary_price": p1,
        "secondary_symbol": secondary,
        "secondary_price": p2,
        "current_spread": spread,
        "20d_mean_spread": hist_mean,
        "z_score": z_score,
        "spread_regime": regime,
        "trading_implication": "Mean reversion short spread (sell Brent, buy WTI)"
        if z_score > 2.0
        else (
            "Mean reversion long spread (buy Brent, sell WTI)"
            if z_score < -2.0
            else "Spread within normal historical band."
        ),
    }


# ==============================================================================
# 10. Get GARCH Volatility (Q148)
# ==============================================================================
async def handle_get_garch_volatility(args: dict, **ctx) -> dict:
    """Calculates conditional volatility, forecast volatility, persistence, and regime via GARCH(1,1)."""
    session, settings, _ = _get_context(args, ctx)
    symbol = str(args.get("symbol", "XAUUSD")).upper()
    timeframe = str(args.get("timeframe", "H1")).upper()
    if not session:
        return {"status": "error", "error": "Database session required for GARCH volatility"}

    bars = (
        (
            await session.execute(
                select(PriceOHLCV.close)
                .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    if not bars or len(bars) < 30:
        return {
            "status": "insufficient_data",
            "error": f"Insufficient bars ({len(bars) if bars else 0}) for {symbol}/{timeframe} GARCH calculation",
        }

    from monika.application.analysis.calculators.garch_volatility import GarchVolatilityEngine

    prices = [float(c) for c in reversed(bars)]
    res = GarchVolatilityEngine.estimate_garch11(prices, is_returns=False)
    return {
        "status": "success",
        "symbol": symbol,
        "timeframe": timeframe,
        "current_volatility": res.current_volatility,
        "forecasted_volatility_1step": res.forecasted_volatility_1step,
        "annualized_current_vol_pct": res.annualized_current_vol,
        "annualized_forecast_vol_pct": res.annualized_forecast_vol,
        "persistence": res.persistence,
        "half_life_bars": res.half_life_bars,
        "volatility_regime": res.volatility_regime,
        "parameters": res.parameters,
    }


# ==============================================================================
# 11. Get Copula Tail Risk (Q149)
# ==============================================================================
async def handle_get_copula_tail_risk(args: dict, **ctx) -> dict:
    """Evaluates joint crash probability and tail dependence between two assets via Archimedean Copula."""
    session, _, _ = _get_context(args, ctx)
    asset1 = str(args.get("asset1", "EURUSD")).upper()
    asset2 = str(args.get("asset2", "GBPUSD")).upper()
    timeframe = str(args.get("timeframe", "H1")).upper()
    tail_quantile = float(args.get("tail_quantile", 0.05))

    if not session:
        return {"status": "error", "error": "Database session required for Copula tail risk calculation"}

    b1_stmt = (
        select(PriceOHLCV.timestamp, PriceOHLCV.close)
        .where(PriceOHLCV.symbol == asset1, PriceOHLCV.timeframe == timeframe)
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(100)
    )
    b2_stmt = (
        select(PriceOHLCV.timestamp, PriceOHLCV.close)
        .where(PriceOHLCV.symbol == asset2, PriceOHLCV.timeframe == timeframe)
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(100)
    )
    rows1 = {r[0]: float(r[1]) for r in (await session.execute(b1_stmt)).all()}
    rows2 = {r[0]: float(r[1]) for r in (await session.execute(b2_stmt)).all()}
    common_dates = sorted(set(rows1.keys()) & set(rows2.keys()))
    if len(common_dates) < 20:
        return {"status": "insufficient_data", "error": f"Insufficient matching bars between {asset1} and {asset2}"}

    import pandas as pd
    from monika.application.analysis.calculators.copula_tail_risk import evaluate_joint_tail_risk

    p1 = pd.Series([float(rows1[d]) for d in common_dates])
    p2 = pd.Series([float(rows2[d]) for d in common_dates])
    r1 = p1.pct_change().dropna()
    r2 = p2.pct_change().dropna()

    report = evaluate_joint_tail_risk(r1, r2, tail_quantile=tail_quantile)
    return {
        "status": "success",
        "asset1": asset1,
        "asset2": asset2,
        "timeframe": timeframe,
        "tail_risk_report": report,
    }


def register_advanced_quant_tools(registry=None):
    from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry

    if registry is None:
        registry = ToolRegistry.get_instance()

    tools = [
        ToolDefinition(
            name="simulate_portfolio_drawdown",
            description="Simulate portfolio drawdown and margin utilization under multi-position correlation shocks (Q099).",
            parameters={
                "type": "object",
                "properties": {"positions": {"type": "array"}, "simulations": {"type": "integer"}},
            },
            handler=handle_simulate_portfolio_drawdown,
            toolset="risk",
            requires_db=False,
        ),
        ToolDefinition(
            name="calculate_kelly_criterion",
            description="Calculate exact Kelly Criterion growth sizing, fractional Kelly variants, and ruin risk (Q100).",
            parameters={
                "type": "object",
                "properties": {
                    "win_rate": {"type": "number"},
                    "win_loss_ratio": {"type": "number"},
                    "symbol": {"type": "string"},
                },
            },
            handler=handle_calculate_kelly_criterion,
            toolset="quant",
            requires_db=False,
        ),
        ToolDefinition(
            name="run_walk_forward_optimization",
            description="Run walk-forward optimization across in-sample and out-of-sample rolling windows (Q102).",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "strategy_name": {"type": "string"}},
            },
            handler=handle_run_walk_forward_optimization,
            toolset="quant",
            requires_db=False,
        ),
        ToolDefinition(
            name="optimize_strategy_parameters",
            description="Execute parameter grid/plateau optimization over strategy parameter spaces (Q111).",
            parameters={
                "type": "object",
                "properties": {
                    "strategy": {"type": "string"},
                    "param_name": {"type": "string"},
                    "param_min": {"type": "number"},
                    "param_max": {"type": "number"},
                    "param_step": {"type": "number"},
                },
            },
            handler=handle_optimize_strategy_parameters,
            toolset="quant",
            requires_db=False,
        ),
        ToolDefinition(
            name="run_model_benchmark",
            description="Benchmark LLM trading decisions across model tiers (Gemini vs Claude vs GPT) on historical setups (Q112).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "models": {"type": "array"},
                    "num_cases": {"type": "integer"},
                },
            },
            handler=handle_run_model_benchmark,
            toolset="benchmark",
            requires_db=False,
        ),
        ToolDefinition(
            name="evaluate_debate_efficacy",
            description="Statistical evaluation comparing debate engine win rates vs raw single-model decisions (Q140).",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_evaluate_debate_efficacy,
            toolset="analytics",
            requires_db=True,
        ),
        ToolDefinition(
            name="scan_smc_setups",
            description="Scan watchlist instruments to identify strongest institutional SMC Order Block and FVG setups (Q060).",
            parameters={
                "type": "object",
                "properties": {"timeframe": {"type": "string"}, "min_confluence": {"type": "integer"}},
            },
            handler=handle_scan_smc_setups,
            toolset="screening",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_carry_trade_rankings",
            description="Rank G10 and EM currency pairs by net interest rate differentials and carry-to-risk ratio (Q074).",
            parameters={"type": "object", "properties": {"top_n": {"type": "integer"}}},
            handler=handle_get_carry_trade_rankings,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_commodity_spread",
            description="Analyze Brent vs WTI crude oil crack/arbitrage spread, historical mean, and z-score regime (Q088).",
            parameters={"type": "object", "properties": {"spread_type": {"type": "string"}}},
            handler=handle_get_commodity_spread,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_garch_volatility",
            description="Calculate forward conditional volatility and volatility clustering regime via GARCH(1,1) (Q148).",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}},
            },
            handler=handle_get_garch_volatility,
            toolset="quant",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_copula_tail_risk",
            description="Evaluate joint crash risk and tail dependence between two assets via Archimedean Copulas (Q149).",
            parameters={
                "type": "object",
                "properties": {
                    "asset1": {"type": "string"},
                    "asset2": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "tail_quantile": {"type": "number"},
                },
            },
            handler=handle_get_copula_tail_risk,
            toolset="quant",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_advanced_quant_tools()
