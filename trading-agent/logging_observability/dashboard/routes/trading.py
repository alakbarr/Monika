# ==============================================================================
# File: logging_observability/dashboard/routes/trading.py
# Description: Trading, Positions, Orders, Analysis, and Control Endpoints
# ==============================================================================

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from logging_observability.dashboard.rbac import Role, require_role
from logging_observability.dashboard.routes.common import (
    ClosePositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TriggerCycleRequest,
    _safe_json,
    broadcast_live_event,
    get_dashboard_dependency,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading")

trading_router = APIRouter()


# ---------------------------------------------------------------------------
# Overview (main dashboard stat cards)
# ---------------------------------------------------------------------------

@trading_router.get("/api/overview", tags=["Dashboard"])
async def get_overview():
    """Data metrik ringkas untuk highlight kartu dashboard."""
    from database.db import AsyncSessionLocal
    from database.models import Position, RiskState, VIXData, AssetAnalysis, SystemConfig
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        # Open positions
        pos_count = (await session.execute(
            select(func.count(Position.id)).where(Position.status == "open")
        )).scalar_one_or_none() or 0

        # Daily PnL + drawdown + paused
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (await session.execute(
            select(RiskState)
            .where(RiskState.date >= today_start)
            .order_by(RiskState.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        # Account balance for pct calculation
        balance_cfg = (await session.execute(
            select(SystemConfig.value).where(SystemConfig.key.in_(["account_balance", "initial_balance"])).limit(1)
        )).scalar_one_or_none()

        balance = None
        if balance_cfg:
            try:
                balance = float(balance_cfg)
            except (ValueError, TypeError):
                balance = None

        daily_pnl = round(risk.daily_pnl, 2) if risk else 0.0
        current_drawdown = round(risk.current_drawdown, 2) if risk else 0.0
        daily_pnl_pct = round((daily_pnl / balance) * 100, 2) if (balance and balance > 0) else None
        drawdown_pct = round((current_drawdown / balance) * 100, 2) if (balance and balance > 0) else None

        # Latest VIX
        vix = (await session.execute(
            select(VIXData).order_by(VIXData.date.desc()).limit(1)
        )).scalar_one_or_none()

        # Last analysis timestamp
        last_analysis = (await session.execute(
            select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        return {
            "agent_status": "paused" if (risk and risk.trading_paused) else "active",
            "open_positions_count": pos_count,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "current_drawdown": current_drawdown,
            "drawdown_pct": drawdown_pct,
            "trading_paused": risk.trading_paused if risk else False,
            "pause_reason": risk.reason if risk else None,
            "vix": round(vix.close, 2) if vix else None,
            "vix_date": vix.date.isoformat() if vix else None,
            "last_analysis_at": last_analysis.generated_at.isoformat() if last_analysis else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Paper trading stats
# ---------------------------------------------------------------------------

@trading_router.get("/api/paper-trading", tags=["Performance"])
async def get_paper_trading_stats():
    """Rangkuman PnL paper trading, win rate & detail performa."""
    from database.db import AsyncSessionLocal
    from utils.analytics.paper_tracker import PaperTracker

    async with AsyncSessionLocal() as session:
        tracker = PaperTracker()
        stats = await tracker.get_statistics(session)
        return stats


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@trading_router.get("/api/positions", tags=["Positions"])
async def get_positions(
    status: str = Query(default="open", description="Filter by status: open, closed, all"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Daftar historis atau posisi yang masih terbuka."""
    from database.db import AsyncSessionLocal
    from database.models import Position
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        q = select(Position).order_by(Position.opened_at.desc()).limit(limit)
        if status != "all":
            q = q.where(Position.status == status)

        positions = (await session.execute(q)).scalars().all()

        return [
            {
                "id": p.id,
                "mt5_ticket": p.mt5_ticket,
                "symbol": p.symbol,
                "direction": p.direction,
                "volume": p.volume,
                "entry_price": p.entry_price,
                "sl": p.sl,
                "tp": p.tp,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "status": p.status,
                "pnl": round(p.pnl, 2) if p.pnl is not None else None,
            }
            for p in positions
        ]


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@trading_router.get("/api/activity", tags=["Activity"])
async def get_activity(
    limit: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    offset: int = Query(default=0, ge=0),
):
    """Log aktivitas (berdukungan paginasi & filter)."""
    from database.db import AsyncSessionLocal
    from database.models import ActivityLog
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        q = (
            select(ActivityLog)
            .order_by(ActivityLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        if category:
            q = q.where(ActivityLog.category == category)

        logs = (await session.execute(q)).scalars().all()

        return [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "category": log.category,
                "description": log.description,
                "related_id": log.related_id,
                "actor": log.actor,
            }
            for log in logs
        ]


# ---------------------------------------------------------------------------
# Asset analysis results
# ---------------------------------------------------------------------------

@trading_router.get("/api/analysis", tags=["Analysis"])
async def get_analysis(
    limit: int = Query(default=20, ge=1, le=100),
    symbol: Optional[str] = Query(default=None),
):
    """Riwayat analisis Stage 2 AI per aset."""
    from database.db import AsyncSessionLocal
    from database.models import AssetAnalysis
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        q = (
            select(AssetAnalysis)
            .order_by(AssetAnalysis.generated_at.desc())
            .limit(limit)
        )
        if symbol:
            q = q.where(AssetAnalysis.symbol == symbol.upper())

        analyses = (await session.execute(q)).scalars().all()

        results = []
        for a in analyses:
            reeval = None
            if a.reevaluation_trigger:
                try:
                    rt = json.loads(a.reevaluation_trigger)
                    reeval = rt.get("detail") or str(rt)
                except Exception:
                    reeval = str(a.reevaluation_trigger)[:100]

            results.append({
                "id": a.id,
                "symbol": a.symbol,
                "decision": a.decision,
                "confidence": round(a.confidence * 100, 1) if a.confidence else None,
                "generated_at": a.generated_at.isoformat() if a.generated_at else None,
                "stop_loss": a.stop_loss,
                "take_profit": a.take_profit,
                "rationale": (a.rationale or "")[:300],
                "reevaluation_trigger": reeval,
                "invalidation": (a.invalidation or "")[:200],
            })
        return results


@trading_router.get("/api/factor-analysis", tags=["Performance"])
async def get_factor_analysis():
    """Mengukur seberapa akurat confluence factor vs PnL sesungguhnya."""
    from database.db import AsyncSessionLocal
    from utils.analytics.analysis_tracker import compute_factor_effectiveness

    async with AsyncSessionLocal() as session:
        result = await compute_factor_effectiveness(session, days_back=60)
        return result


# ---------------------------------------------------------------------------
# Order log (audit trail)
# ---------------------------------------------------------------------------

@trading_router.get("/api/orders", tags=["Orders"])
async def get_orders(
    limit: int = Query(default=30, ge=1, le=100),
    action: Optional[str] = Query(default=None, description="Filter: place, modify, close"),
):
    """Audit trail percobaan order (sukses & gagal/tolak)."""
    from database.db import AsyncSessionLocal
    from database.models import OrderLog
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        q = (
            select(OrderLog)
            .order_by(OrderLog.timestamp.desc())
            .limit(limit)
        )
        if action:
            q = q.where(OrderLog.action == action)

        orders = (await session.execute(q)).scalars().all()

        return [
            {
                "id": o.id,
                "action": o.action,
                "symbol": o.symbol,
                "params": _safe_json(o.params_json),
                "requested_by": o.requested_by,
                "approved_by": o.approved_by,
                "result": _safe_json(o.result),
                "timestamp": o.timestamp.isoformat() if o.timestamp else None,
            }
            for o in orders
        ]


# ---------------------------------------------------------------------------
# Risk state
# ---------------------------------------------------------------------------

@trading_router.get("/api/risk", tags=["Risk"])
async def get_risk():
    """State PnL hari ini, status auto-trading (paused/active), margin, dan parameter risiko."""
    from database.db import AsyncSessionLocal
    from database.models import RiskState, PaperTradeRecord, Position
    from sqlalchemy import select, desc

    settings = get_dashboard_dependency("settings") or {}
    trading_risk = settings.get("trading", {}).get("risk", {}) if isinstance(settings, dict) else {}
    max_risk_pct = float(trading_risk.get("risk_percent_per_trade", 1.0))
    max_daily_dd = float(trading_risk.get("max_daily_drawdown_percent", 3.0))
    max_positions = int(trading_risk.get("max_concurrent_positions", 5))

    now_utc = datetime.now(timezone.utc)
    is_weekend = now_utc.weekday() >= 5

    mt5_client = get_dashboard_dependency("mt5_client")
    account_info = None
    if mt5_client and hasattr(mt5_client, "get_account_info"):
        try:
            account_info = await mt5_client.get_account_info()
        except Exception:
            pass

    async with AsyncSessionLocal() as session:
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (await session.execute(
            select(RiskState)
            .where(RiskState.date >= today_start)
            .order_by(RiskState.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        # Count real consecutive losses from closed trades
        consecutive_losses = 0
        recent_closed = (await session.execute(
            select(PaperTradeRecord.exit_reason, PaperTradeRecord.pnl_pct)
            .where(PaperTradeRecord.status == "closed")
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(10)
        )).all()
        for row in recent_closed:
            pnl = row.pnl_pct or 0.0
            if row.exit_reason == "sl_hit" or pnl < 0:
                consecutive_losses += 1
            else:
                break

        # Open positions count for exposure estimation
        open_pos_count = (await session.execute(
            select(Position).where(Position.status == "open")
        )).scalars().all()
        active_pos_count = len(open_pos_count)

        # Margin and exposure calculations
        margin_used = 0.0
        margin_free = 0.0
        margin_level_pct = 0.0
        margin_usage_pct = 0.0

        if account_info and isinstance(account_info, dict):
            equity = float(account_info.get("equity") or 0.0)
            margin_used = float(account_info.get("margin") or 0.0)
            margin_free = float(account_info.get("margin_free") or 0.0)
            margin_level_pct = float(account_info.get("margin_level") or 0.0)
            margin_usage_pct = (margin_used / equity * 100.0) if equity > 0 else 0.0
        else:
            # Synthetic approximation if broker offline
            margin_usage_pct = round(active_pos_count * 2.5, 2)

        total_open_risk_pct = round(active_pos_count * max_risk_pct, 2)

        if not risk:
            return {
                "date": now_utc.date().isoformat(),
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "current_drawdown": 0.0,
                "trading_paused": False,
                "reason": None,
                "margin_used": round(margin_used, 2),
                "margin_free": round(margin_free, 2),
                "margin_level_pct": round(margin_level_pct, 2),
                "margin_usage_pct": round(margin_usage_pct, 2),
                "total_open_risk_pct": total_open_risk_pct,
                "consecutive_losses": consecutive_losses,
                "max_consecutive_losses": 3,
                "max_risk_pct": max_risk_pct,
                "max_daily_drawdown_pct": max_daily_dd,
                "max_positions": max_positions,
                "avg_spread_pips": 1.2,
                "avg_rr_ratio": 1.5,
                "is_weekend": is_weekend,
            }

        daily_pnl_pct = getattr(risk, "daily_pnl_pct", None)
        starting_bal = getattr(risk, "starting_balance", None)
        if daily_pnl_pct is None and hasattr(risk, "daily_pnl") and starting_bal:
            daily_pnl_pct = (risk.daily_pnl / starting_bal) * 100
        elif daily_pnl_pct is None:
            daily_pnl_pct = 0.0

        return {
            "date": risk.date.date().isoformat() if risk.date else None,
            "daily_pnl": round(risk.daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "current_drawdown": round(risk.current_drawdown, 2),
            "trading_paused": risk.trading_paused,
            "reason": risk.reason,
            "margin_used": round(margin_used, 2),
            "margin_free": round(margin_free, 2),
            "margin_level_pct": round(margin_level_pct, 2),
            "margin_usage_pct": round(margin_usage_pct, 2),
            "total_open_risk_pct": total_open_risk_pct,
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": 3,
            "max_risk_pct": max_risk_pct,
            "max_daily_drawdown_pct": max_daily_dd,
            "max_positions": max_positions,
            "avg_spread_pips": 1.2,
            "avg_rr_ratio": 1.5,
            "is_weekend": is_weekend,
        }


# ---------------------------------------------------------------------------
# Edge metrics
# ---------------------------------------------------------------------------

@trading_router.get("/api/edge-metrics", tags=["Performance"])
async def get_edge_metrics():
    """
    Key metrics untuk monitoring apakah sistem masih memiliki edge positif.
    Ini adalah dashboard paling penting untuk trading system health.
    """
    from database.db import AsyncSessionLocal
    from database.models import PaperTradeRecord, AssetAnalysis
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        results = {}
        for days in [7, 14, 30]:
            since = now - timedelta(days=days)
            records = (await session.execute(
                select(PaperTradeRecord, AssetAnalysis)
                .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
                .where(PaperTradeRecord.closed_at >= since)
                .where(PaperTradeRecord.status == "closed")
                .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
            )).all()

            if not records:
                results[f"{days}d"] = {"insufficient_data": True}
                continue

            wins = [r for r, a in records if r.exit_reason == "tp_hit"]
            losses = [r for r, a in records if r.exit_reason == "sl_hit"]

            rr_values = []
            for r, a in records:
                if r.entry_price and r.stop_loss and r.exit_price and r.exit_reason == "tp_hit":
                    sl_dist = abs(r.entry_price - r.stop_loss)
                    tp_dist = abs(r.exit_price - r.entry_price) if r.direction == "buy" else abs(r.entry_price - r.exit_price)
                    if sl_dist > 0:
                        rr_values.append(tp_dist / sl_dist)

            win_rate = len(wins) / len(records) if records else 0
            loss_rate = 1 - win_rate
            avg_rr = sum(rr_values) / len(rr_values) if rr_values else 2.0
            expectancy = (win_rate * avg_rr) - loss_rate

            hold_times = [r.holding_hours for r, a in records if r.holding_hours]

            results[f"{days}d"] = {
                "total_trades": len(records),
                "win_rate_pct": round(win_rate * 100, 1),
                "avg_rr_achieved": round(avg_rr, 2),
                "expectancy_per_trade_R": round(expectancy, 3),
                "is_profitable": expectancy > 0,
                "avg_holding_hours": round(sum(hold_times) / len(hold_times), 1) if hold_times else None,
                "by_symbol": {},
            }

        return {
            "edge_metrics": results,
            "alert": any(
                r.get("expectancy_per_trade_R", 1) < -0.1
                for r in results.values()
                if isinstance(r, dict) and "expectancy_per_trade_R" in r
            ),
            "timestamp": now.isoformat(),
        }


@trading_router.get("/api/decision-distribution", tags=["Analysis"])
async def get_decision_distribution():
    from database.db import AsyncSessionLocal
    from database.models import AssetAnalysis
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        since = datetime.now(timezone.utc) - timedelta(days=30)

        result = (await session.execute(
            select(
                AssetAnalysis.symbol,
                AssetAnalysis.decision,
                func.count(AssetAnalysis.id).label("count")
            )
            .where(AssetAnalysis.generated_at >= since)
            .group_by(AssetAnalysis.symbol, AssetAnalysis.decision)
        )).all()

        distribution = {}
        for row in result:
            if row.symbol not in distribution:
                distribution[row.symbol] = {
                    "buy": 0, "sell": 0, "wait": 0, "avoid": 0, "skip": 0
                }
            distribution[row.symbol][row.decision] = distribution[row.symbol].get(row.decision, 0) + row.count

        for sym, counts in distribution.items():
            total = sum(counts.values())
            trade_decisions = counts.get("buy", 0) + counts.get("sell", 0)
            distribution[sym]["total"] = total
            distribution[sym]["trade_rate_pct"] = round(trade_decisions / total * 100, 1) if total > 0 else 0

        return distribution


@trading_router.get("/api/analysis-quality-realtime", tags=["Performance"])
async def get_analysis_quality_realtime():
    """Real-time analysis quality metrics for monitoring dashboard."""
    from database.db import AsyncSessionLocal
    from database.models import AssetAnalysis, PaperTradeRecord
    from sqlalchemy import select, or_

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        last_7d = now - timedelta(days=7)

        recent_analyses = (await session.execute(
            select(AssetAnalysis)
            .where(AssetAnalysis.generated_at >= last_7d)
            .where(AssetAnalysis.decision.in_(["buy", "sell"]))
            .where(or_(
                AssetAnalysis.decision_source.is_(None),
                AssetAnalysis.decision_source != "edge_registry"
            ))
        )).scalars().all()

        total = len(recent_analyses)
        missing_confluence = sum(1 for a in recent_analyses if a.confluence_score is None)
        missing_priced_in = sum(1 for a in recent_analyses if a.priced_in_score is None)
        valid_confluence = [a.confluence_score for a in recent_analyses if a.confluence_score is not None]
        valid_priced_in = [a.priced_in_score for a in recent_analyses if a.priced_in_score is not None]

        score_dist = {"high": 0, "medium": 0, "low": 0}
        for s in valid_confluence:
            if s >= 10:
                score_dist["high"] += 1
            elif s >= 7:
                score_dist["medium"] += 1
            else:
                score_dist["low"] += 1

        closed_trades = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.closed_at >= last_7d)
            .where(PaperTradeRecord.status == "closed")
        )).scalars().all()
        tp_hits = sum(1 for t in closed_trades if t.exit_reason == "tp_hit")
        sl_hits = sum(1 for t in closed_trades if t.exit_reason == "sl_hit")
        win_rate = round(tp_hits / (tp_hits + sl_hits) * 100, 1) if (tp_hits + sl_hits) > 0 else None

        return {
            "period": "7d",
            "total_actionable_analyses": total,
            "missing_confluence_score_pct": round(missing_confluence / max(total, 1) * 100, 1),
            "missing_priced_in_score_pct": round(missing_priced_in / max(total, 1) * 100, 1),
            "avg_confluence_score": round(sum(valid_confluence) / len(valid_confluence), 2) if valid_confluence else None,
            "avg_priced_in_score": round(sum(valid_priced_in) / len(valid_priced_in), 2) if valid_priced_in else None,
            "compliance_rate_pct": round((1 - missing_confluence / max(total, 1)) * 100, 1),
            "confluence_score_distribution": score_dist,
            "closed_trades_7d": len(closed_trades),
            "win_rate_pct": win_rate,
            "alert": missing_confluence / max(total, 1) > 0.1,
        }


@trading_router.get("/api/ssvp-health", tags=["SSVP"])
async def get_ssvp_health():
    """Monitor metric performa SSVP."""
    from database.db import AsyncSessionLocal
    from database.models import SystemConfig
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        cfg_calib = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "cds_threshold_calibration")
        )).scalar_one_or_none()

        calib_data = {}
        if cfg_calib and cfg_calib.value:
            try:
                calib_data = json.loads(cfg_calib.value)
            except Exception:
                pass

        cfg_infl = (await session.execute(
            select(SystemConfig).where(
                SystemConfig.key.in_(["score_inflation_correction_threshold", "score_inflation_report"])
            )
        )).scalars().first()

        infl_data = {}
        if cfg_infl and cfg_infl.value:
            try:
                infl_data = json.loads(cfg_infl.value)
            except Exception:
                pass

        return {
            "calibration": calib_data,
            "inflation": infl_data,
            "status": "healthy" if calib_data.get("result", {}).get("is_cds_predictive", True) else "warning",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@trading_router.get("/api/debate-outcomes", tags=["Analysis"])
async def get_debate_outcomes(limit: int = Query(default=20, ge=1, le=100)):
    """Ambil ringkasan hasil debate bull/bear & adjudikasi spesialis (M-4)."""
    from database.db import AsyncSessionLocal
    from database.models import AssetAnalysis
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(AssetAnalysis)
            .where(AssetAnalysis.decision.in_(["buy", "sell"]))
            .order_by(AssetAnalysis.generated_at.desc())
            .limit(limit)
        )).scalars().all()

        results = []
        for r in rows:
            adj = None
            raw_adj = getattr(r, "specialist_biases_json", None) or getattr(r, "specialist_adjudication", None)
            if raw_adj:
                try:
                    adj = json.loads(raw_adj)
                except Exception:
                    adj = raw_adj
            bull_raw = getattr(r, "debate_bull_thesis", None)
            bear_raw = getattr(r, "debate_bear_dissent", None)
            bull_thesis = None
            bear_dissent = None
            if bull_raw:
                try:
                    bull_thesis = json.loads(bull_raw)
                except Exception:
                    bull_thesis = bull_raw
            if bear_raw:
                try:
                    bear_dissent = json.loads(bear_raw)
                except Exception:
                    bear_dissent = bear_raw

            conf_val = r.confidence
            if conf_val is not None:
                norm_conf = round(conf_val * 100, 1) if conf_val <= 1.0 else round(conf_val, 1)
            else:
                norm_conf = None

            results.append({
                "id": r.id,
                "symbol": r.symbol,
                "decision": r.decision,
                "confidence": norm_conf,
                "confluence_score": r.confluence_score,
                "risk_multiplier": r.risk_multiplier,
                "rationale": r.rationale,
                "specialist_adjudication": adj,
                "debate_bull_thesis": bull_thesis,
                "debate_bear_dissent": bear_dissent,
                "debate_verdict": getattr(r, "debate_verdict", None),
                "debate_reason": getattr(r, "debate_reason", None),
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "execution_status": r.execution_status,
            })
        return {"total": len(results), "items": results}


@trading_router.get("/api/signals/mt5", tags=["Execution"])
async def get_mt5_signals(limit: int = Query(default=50, ge=1, le=200)):
    """Ambil riwayat sinyal dan korelasi eksekusi MT5 (M-4)."""
    from database.db import AsyncSessionLocal
    from database.models import MT5Signal
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(MT5Signal)
            .order_by(MT5Signal.created_at.desc())
            .limit(limit)
        )).scalars().all()

        return {
            "total": len(rows),
            "items": [
                {
                    "id": s.id,
                    "asset_analysis_id": s.asset_analysis_id,
                    "symbol": s.symbol,
                    "action": s.action,
                    "status": s.status,
                    "mt5_ticket": s.mt5_ticket,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "executed_at": s.executed_at.isoformat() if s.executed_at else None,
                    "error_message": s.error_message,
                }
                for s in rows
            ],
        }


@trading_router.get("/api/triggers", tags=["Analysis"])
async def get_trade_triggers(status: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)):
    """Ambil daftar trade triggers kondisional (M-4)."""
    from database.db import AsyncSessionLocal
    from database.models import TradeTrigger
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = select(TradeTrigger)
        if status:
            stmt = stmt.where(TradeTrigger.status == status)
        stmt = stmt.order_by(TradeTrigger.created_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

        results = []
        for t in rows:
            cond = None
            if t.condition_json:
                try:
                    cond = json.loads(t.condition_json)
                except Exception:
                    cond = t.condition_json
            results.append({
                "id": t.id,
                "asset_analysis_id": t.asset_analysis_id,
                "trigger_type": t.trigger_type,
                "status": t.status,
                "condition": cond,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "fired_at": t.fired_at.isoformat() if t.fired_at else None,
            })
        return {"total": len(results), "items": results}


# ---------------------------------------------------------------------------
# Interactive Action Endpoints (2-Way Dashboard Control [MED-02])
# ---------------------------------------------------------------------------

@trading_router.post("/api/actions/trigger-cycle", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_trigger_cycle(request: Request, body: TriggerCycleRequest = TriggerCycleRequest()):
    """Trigger the LangGraph analysis cycle immediately."""
    cycle_sched = get_dashboard_dependency("cycle_scheduler")
    if not cycle_sched:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "CycleScheduler is not initialized or registered."}
        )

    if hasattr(cycle_sched, "_cycle_lock") and cycle_sched._cycle_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"status": "skipped", "message": "An analysis cycle is already actively executing."}
        )

    asyncio.create_task(cycle_sched.run_once(forced=body.forced))

    from database.db import AsyncSessionLocal
    from database.models import ActivityLog
    try:
        async with AsyncSessionLocal() as session:
            session.add(ActivityLog(
                category="system",
                description=f"Analysis cycle manually triggered via Dashboard ({body.reason})",
                actor="dashboard",
            ))
            await session.commit()
    except Exception as e:
        logger.debug(f"Failed to log dashboard activity: {e}")

    await broadcast_live_event("cycle_triggered", {
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "forced": body.forced,
        "reason": body.reason,
    })

    return {
        "status": "triggered",
        "message": "Analysis cycle dispatched successfully.",
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "forced": body.forced,
    }


@trading_router.post("/api/actions/steer", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_steer(body: SteerRequest, request: Request):
    """Inject operator steering instruction / directive into active or next cycle."""
    from database.db import AsyncSessionLocal
    from database.models import ActivityLog, UserMarketIntel, _utcnow

    now = _utcnow()
    symbols_str = ",".join(body.symbols) if body.symbols else "ALL"

    try:
        async with AsyncSessionLocal() as session:
            intel = UserMarketIntel(
                telegram_user_id="operator_dashboard",
                intel_type="tactical_directive",
                title="Operator Steer Directive",
                summary=body.message,
                directive="neutral",
                target_cycle="next_cycle_only" if body.mode == "follow_up" else "continuous",
                affected_symbols=symbols_str,
                is_active=True,
                created_at=now,
            )
            session.add(intel)
            session.add(ActivityLog(
                category="analysis",
                description=f"Operator steer injected ({body.mode}): {body.message[:150]}",
                actor="operator",
            ))
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to persist operator steer directive: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    await broadcast_live_event("steer_injected", {
        "message": body.message,
        "mode": body.mode,
        "symbols": body.symbols,
        "injected_at": now.isoformat(),
    })

    return {
        "status": "steered",
        "message": "Steer directive successfully recorded and broadcasted.",
        "mode": body.mode,
        "injected_at": now.isoformat(),
    }


@trading_router.post("/api/actions/override-risk", tags=["Actions"])
@require_role(Role.ADMIN)
async def action_override_risk(payload: OverrideRiskRequest, request: Request):
    """Update dynamic risk parameters in SystemConfig and runtime settings."""
    from database.db import AsyncSessionLocal
    from database.models import SystemConfig, ActivityLog
    from sqlalchemy import select

    updated_fields = {}
    if payload.risk_percent_per_trade is not None:
        updated_fields["risk_percent_per_trade"] = float(payload.risk_percent_per_trade)
    if payload.max_daily_drawdown_percent is not None:
        updated_fields["max_daily_drawdown_percent"] = float(payload.max_daily_drawdown_percent)
    if payload.max_weekly_drawdown_percent is not None:
        updated_fields["max_weekly_drawdown_percent"] = float(payload.max_weekly_drawdown_percent)
    if payload.max_concurrent_positions is not None:
        updated_fields["max_concurrent_positions"] = int(payload.max_concurrent_positions)
    if payload.max_lot_per_symbol is not None:
        updated_fields["max_lot_per_symbol"] = float(payload.max_lot_per_symbol)
    if payload.max_risk_amount_usd is not None:
        updated_fields["max_risk_amount_usd"] = float(payload.max_risk_amount_usd)
    if payload.auto_execute is not None:
        updated_fields["auto_execute"] = bool(payload.auto_execute)
    if payload.system_paused is not None:
        updated_fields["system_paused"] = bool(payload.system_paused)
    if payload.custom_overrides:
        updated_fields.update(payload.custom_overrides)

    if not updated_fields:
        return JSONResponse(status_code=400, content={"status": "error", "message": "No risk fields provided to override."})

    async with AsyncSessionLocal() as session:
        cfg_row = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "risk_override")
        )).scalar_one_or_none()

        current_cfg = {}
        if cfg_row and cfg_row.value:
            try:
                current_cfg = json.loads(cfg_row.value)
            except Exception:
                pass
        current_cfg.update(updated_fields)

        if cfg_row:
            cfg_row.value = json.dumps(current_cfg)
        else:
            session.add(SystemConfig(key="risk_override", value=json.dumps(current_cfg)))

        settings = get_dashboard_dependency("settings")
        if settings and isinstance(settings, dict):
            trading_risk = settings.setdefault("trading", {}).setdefault("risk", {})
            trading_risk.update(updated_fields)

        reason_text = payload.reason or f"Risk parameters overridden via Dashboard: {list(updated_fields.keys())}"
        session.add(ActivityLog(
            category="risk",
            description=reason_text,
            actor="dashboard",
        ))
        await session.commit()

    await broadcast_live_event("risk_override_updated", {
        "updated_fields": updated_fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "success",
        "message": "Risk parameters overridden successfully.",
        "updated": updated_fields,
        "effective_config": current_cfg,
    }


@trading_router.post("/api/actions/close-position", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_close_position(payload: ClosePositionRequest, request: Request):
    """Close floating position in MT5/broker or synthetic paper trade."""
    from database.db import AsyncSessionLocal
    from database.models import Position
    from sqlalchemy import select

    exec_svc = get_dashboard_dependency("execution_service")
    mt5_client = get_dashboard_dependency("mt5_client")

    target_ticket = payload.ticket

    async with AsyncSessionLocal() as session:
        if target_ticket is None and payload.position_id is not None:
            pos = (await session.execute(
                select(Position).where(Position.id == payload.position_id)
            )).scalar_one_or_none()
            if not pos:
                return JSONResponse(status_code=404, content={"status": "error", "message": f"Position {payload.position_id} not found."})
            target_ticket = pos.mt5_ticket
            if target_ticket is None and pos.is_paper:
                if exec_svc and hasattr(exec_svc, "_close_paper_position"):
                    res = await exec_svc._close_paper_position(session, pos, requested_by="dashboard", reason=payload.reason)
                    return {"status": "success", "result": res}

    if target_ticket is None:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Must provide ticket or position_id."})

    if exec_svc and hasattr(exec_svc, "close_position_by_ticket"):
        res = await exec_svc.close_position_by_ticket(
            ticket=target_ticket,
            requested_by="dashboard",
            reason=payload.reason,
        )
    elif mt5_client and hasattr(mt5_client, "close_position"):
        res = await mt5_client.close_position(
            ticket=target_ticket,
            comment=f"Close:dashboard"[:31],
        )
    else:
        async with AsyncSessionLocal() as session:
            pos = (await session.execute(
                select(Position).where(Position.mt5_ticket == target_ticket)
            )).scalar_one_or_none()
            if pos:
                pos.status = "closed"
                pos.closed_at = datetime.now(timezone.utc)
                await session.commit()
                res = {"success": True, "ticket": target_ticket, "note": "Closed in DB (standalone mode)"}
            else:
                return JSONResponse(status_code=404, content={"status": "error", "message": f"Ticket {target_ticket} not found."})

    await broadcast_live_event("position_closed", {
        "ticket": target_ticket,
        "result": res,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "success" if res.get("success") else "failed",
        "ticket": target_ticket,
        "result": res,
    }


@trading_router.post("/api/actions/emergency-kill", tags=["Actions"])
@trading_router.post("/api/kill", tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_emergency_kill(request: Request):
    """Trigger emergency kill switch and position liquidation safely via daemon."""
    from database.db import AsyncSessionLocal
    from database.models import SystemConfig, ActivityLog
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "kill_switch")
        )).scalar_one_or_none()
        if cfg:
            cfg.value = "true"
        else:
            session.add(SystemConfig(key="kill_switch", value="true"))
        session.add(ActivityLog(
            category="system",
            description="Emergency kill switch activated via Dashboard / CLI",
            actor="operator",
        ))
        await session.commit()

    exec_svc = get_dashboard_dependency("execution_service")
    guardian = get_dashboard_dependency("position_guardian")
    if exec_svc and hasattr(exec_svc, "kill_switch"):
        asyncio.create_task(exec_svc.kill_switch("Dashboard emergency kill switch"))
    elif guardian and hasattr(guardian, "execution_service") and hasattr(guardian.execution_service, "kill_switch"):
        asyncio.create_task(guardian.execution_service.kill_switch("Dashboard emergency kill switch"))

    await broadcast_live_event("kill_switch_activated", {
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "reason": "Emergency kill switch triggered",
    })
    return {"status": "success", "message": "Emergency kill switch activated. Position closures initiated."}


@trading_router.api_route("/api/actions/approve-trade/{trade_id}", methods=["POST", "PUT"], tags=["Actions"])
@require_role(Role.OPERATOR)
async def action_approve_trade(trade_id: int, request: Request):
    """Approve a pending trade trigger or asset analysis for order execution."""
    from database.db import AsyncSessionLocal
    from database.models import AssetAnalysis, TradeTrigger, ActivityLog
    from sqlalchemy import select

    exec_svc = get_dashboard_dependency("execution_service")

    async with AsyncSessionLocal() as session:
        trigger = (await session.execute(
            select(TradeTrigger).where(TradeTrigger.id == trade_id)
        )).scalar_one_or_none()

        if trigger:
            trigger.status = "approved"
            trigger.fired_at = datetime.now(timezone.utc)
            session.add(ActivityLog(
                category="trading",
                description=f"TradeTrigger #{trade_id} approved via Dashboard",
                actor="dashboard",
                related_id=trade_id,
            ))
            await session.commit()

            await broadcast_live_event("trade_approved", {
                "trade_id": trade_id,
                "type": "TradeTrigger",
                "status": "approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "status": "success",
                "type": "TradeTrigger",
                "id": trade_id,
                "message": f"TradeTrigger #{trade_id} approved.",
            }

        analysis = (await session.execute(
            select(AssetAnalysis).where(AssetAnalysis.id == trade_id)
        )).scalar_one_or_none()

        if analysis:
            if analysis.decision not in ("buy", "sell"):
                return JSONResponse(
                    status_code=400,
                    content={"status": "rejected", "message": f"AssetAnalysis #{trade_id} has non-tradeable decision '{analysis.decision}'."}
                )

            if exec_svc:
                exec_result = await exec_svc.execute_analysis(session, analysis)
                await session.commit()
                res_dict = {
                    "executed": exec_result.executed,
                    "ticket": exec_result.mt5_ticket,
                    "price": exec_result.executed_price,
                    "lots": exec_result.executed_lots,
                    "error": exec_result.mt5_error,
                }
            else:
                analysis.execution_status = "approved_manual"
                await session.commit()
                res_dict = {"executed": False, "note": "Marked approved_manual (standalone mode)"}

            await broadcast_live_event("trade_approved", {
                "trade_id": trade_id,
                "type": "AssetAnalysis",
                "result": res_dict,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return {
                "status": "success",
                "type": "AssetAnalysis",
                "id": trade_id,
                "execution": res_dict,
            }

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": f"No pending trade or trigger found with ID {trade_id}."}
    )
