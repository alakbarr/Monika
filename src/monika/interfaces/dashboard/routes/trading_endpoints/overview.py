# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/overview.py
# Description: Overview, activity, performance metrics, and SSVP health endpoints
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from monika.interfaces.dashboard.rbac import Role, require_role
from monika.interfaces.dashboard.routes.common import (
    BatchCloseRequest,
    BulkBreakevenRequest,
    ClosePositionRequest,
    ManualOrderPreviewRequest,
    ManualOrderSubmitRequest,
    ModifyPositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TrailingOverrideRequest,
    TriggerCycleRequest,
    _safe_json,
    broadcast_live_event,
    get_dashboard_dependency,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Overview")

overview_router = APIRouter()


@overview_router.get("/api/v1/overview", tags=["Dashboard"])
async def get_overview():
    """Data metrik ringkas untuk highlight kartu dashboard."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis, RiskState, VIXData
    from monika.infrastructure.database.repositories import PositionRepository, SystemConfigRepository

    async with AsyncSessionLocal() as session:
        pos_repo = PositionRepository(session)
        cfg_repo = SystemConfigRepository(session)

        # Open positions
        pos_count = await pos_repo.count_open_positions()

        # Daily PnL + drawdown + paused
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (
            await session.execute(
                select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        # Account balance for pct calculation
        balance_cfg = await cfg_repo.get("account_balance") or await cfg_repo.get("initial_balance")

        balance = None
        if balance_cfg:
            try:
                balance = float(balance_cfg)
            except ValueError, TypeError:
                balance = None

        daily_pnl = round(risk.daily_pnl, 2) if risk else 0.0
        current_drawdown = round(risk.current_drawdown, 2) if risk else 0.0
        daily_pnl_pct = round((daily_pnl / balance) * 100, 2) if (balance and balance > 0) else None
        drawdown_pct = round((current_drawdown / balance) * 100, 2) if (balance and balance > 0) else None

        # Latest VIX
        vix = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()

        # Last analysis timestamp
        last_analysis = (
            await session.execute(select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(1))
        ).scalar_one_or_none()

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


@overview_router.get("/api/v1/paper-trading", tags=["Performance"])
async def get_paper_trading_stats():
    """Rangkuman PnL paper trading, win rate & detail performa."""
    from monika.core.analytics.paper_tracker import PaperTracker
    from monika.infrastructure.database.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tracker = PaperTracker()
        stats = await tracker.get_statistics(session)
        return stats


@overview_router.get("/api/v1/activity", tags=["Activity"])
async def get_activity(
    limit: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    offset: int = Query(default=0, ge=0),
):
    """Log aktivitas (berdukungan paginasi & filter)."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import ActivityLogRepository

    async with AsyncSessionLocal() as session:
        act_repo = ActivityLogRepository(session)
        logs = await act_repo.get_recent(limit=limit, offset=offset, category=category)

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


@overview_router.get("/api/v1/factor-analysis", tags=["Performance"])
async def get_factor_analysis():
    """Mengukur seberapa akurat confluence factor vs PnL sesungguhnya."""
    from monika.core.analytics.analysis_tracker import compute_factor_effectiveness
    from monika.infrastructure.database.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await compute_factor_effectiveness(session, days_back=60)
        return result


@overview_router.get("/api/v1/edge-metrics", tags=["Performance"])
async def get_edge_metrics():
    """
    Key metrics untuk monitoring apakah sistem masih memiliki edge positif.
    Ini adalah dashboard paling penting untuk trading system health.
    """
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        results = {}
        for days in [7, 14, 30]:
            since = now - timedelta(days=days)
            records = (
                await session.execute(
                    select(PaperTradeRecord, AssetAnalysis)
                    .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
                    .where(PaperTradeRecord.closed_at >= since)
                    .where(PaperTradeRecord.status == "closed")
                    .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                )
            ).all()

            if not records:
                results[f"{days}d"] = {"insufficient_data": True}
                continue

            wins = [r for r, a in records if r.exit_reason == "tp_hit"]
            losses = [r for r, a in records if r.exit_reason == "sl_hit"]

            rr_values = []
            for r, a in records:
                if r.entry_price and r.stop_loss and r.exit_price and r.exit_reason == "tp_hit":
                    sl_dist = abs(r.entry_price - r.stop_loss)
                    tp_dist = (
                        abs(r.exit_price - r.entry_price) if r.direction == "buy" else abs(r.entry_price - r.exit_price)
                    )
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


@overview_router.get("/api/v1/analysis-quality-realtime", tags=["Performance"])
async def get_analysis_quality_realtime():
    """Real-time analysis quality metrics for monitoring dashboard."""
    from sqlalchemy import or_, select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis, PaperTradeRecord

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        last_7d = now - timedelta(days=7)

        recent_analyses = (
            (
                await session.execute(
                    select(AssetAnalysis)
                    .where(AssetAnalysis.generated_at >= last_7d)
                    .where(AssetAnalysis.decision.in_(["buy", "sell"]))
                    .where(
                        or_(AssetAnalysis.decision_source.is_(None), AssetAnalysis.decision_source != "edge_registry")
                    )
                )
            )
            .scalars()
            .all()
        )

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

        closed_trades = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.closed_at >= last_7d)
                    .where(PaperTradeRecord.status == "closed")
                )
            )
            .scalars()
            .all()
        )
        tp_hits = sum(1 for t in closed_trades if t.exit_reason == "tp_hit")
        sl_hits = sum(1 for t in closed_trades if t.exit_reason == "sl_hit")
        win_rate = round(tp_hits / (tp_hits + sl_hits) * 100, 1) if (tp_hits + sl_hits) > 0 else None

        return {
            "period": "7d",
            "total_actionable_analyses": total,
            "missing_confluence_score_pct": round(missing_confluence / max(total, 1) * 100, 1),
            "missing_priced_in_score_pct": round(missing_priced_in / max(total, 1) * 100, 1),
            "avg_confluence_score": round(sum(valid_confluence) / len(valid_confluence), 2)
            if valid_confluence
            else None,
            "avg_priced_in_score": round(sum(valid_priced_in) / len(valid_priced_in), 2) if valid_priced_in else None,
            "compliance_rate_pct": round((1 - missing_confluence / max(total, 1)) * 100, 1),
            "confluence_score_distribution": score_dist,
            "closed_trades_7d": len(closed_trades),
            "win_rate_pct": win_rate,
            "alert": missing_confluence / max(total, 1) > 0.1,
        }


@overview_router.get("/api/v1/ssvp-health", tags=["SSVP"])
async def get_ssvp_health():
    """Monitor metric performa SSVP."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import SystemConfig

    async with AsyncSessionLocal() as session:
        cfg_calib = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "cds_threshold_calibration"))
        ).scalar_one_or_none()

        calib_data = {}
        if cfg_calib and cfg_calib.value:
            try:
                calib_data = json.loads(cfg_calib.value)
            except Exception:
                pass

        cfg_infl = (
            (
                await session.execute(
                    select(SystemConfig).where(
                        SystemConfig.key.in_(["score_inflation_correction_threshold", "score_inflation_report"])
                    )
                )
            )
            .scalars()
            .first()
        )

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
