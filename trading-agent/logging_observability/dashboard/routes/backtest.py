# ==============================================================================
# File: logging_observability/dashboard/routes/backtest.py
# Description: REST API endpoints for Backtest management and telemetry
# ==============================================================================

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func

from database.db import get_session
from database.models import BacktestRun, BacktestTrade
from logging_observability.dashboard.rbac import Role, require_role
from logging_observability.dashboard.routes.common import _safe_json

logger = logging.getLogger("TradingAgent.Dashboard.Backtest")

backtest_router = APIRouter(prefix="/api/backtest", tags=["Backtest"])


class BacktestRunRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="Lookback days")
    mode: str = Field(default="full", description="Backtest mode: full, replay, walk_forward")
    initial_equity: float = Field(default=10000.0, gt=0, description="Initial account equity")
    step_hours: int = Field(default=6, ge=1, le=24, description="Step hours")


@backtest_router.get("/runs")
@require_role(Role.VIEWER)
async def list_backtest_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List historical backtest run records with summary metrics."""
    async with get_session() as session:
        stmt = (
            select(BacktestRun)
            .order_by(desc(BacktestRun.created_at))
            .offset(offset)
            .limit(limit)
        )
        runs = (await session.execute(stmt)).scalars().all()

        return {
            "total": len(runs),
            "runs": [
                {
                    "id": r.id,
                    "mode": r.mode,
                    "start_date": r.start_date.isoformat() if r.start_date else None,
                    "end_date": r.end_date.isoformat() if r.end_date else None,
                    "initial_equity": r.initial_equity,
                    "final_equity": r.final_equity,
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "profit_factor": r.profit_factor,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ],
        }


@backtest_router.get("/runs/{run_id}")
@require_role(Role.VIEWER)
async def get_backtest_run_details(
    run_id: int,
    request: Request,
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Max trades to return"),
    offset: int = Query(0, ge=0, description="Offset for trades pagination"),
) -> Dict[str, Any]:
    """Get detailed telemetry and executed trades for a specific backtest run."""
    async with get_session() as session:
        run = await session.get(BacktestRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")

        stmt = select(BacktestTrade).where(BacktestTrade.run_id == run_id).order_by(BacktestTrade.entry_time.asc())
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        trades = (await session.execute(stmt)).scalars().all()

        return {
            "run": {
                "id": run.id,
                "mode": run.mode,
                "start_date": run.start_date.isoformat() if run.start_date else None,
                "end_date": run.end_date.isoformat() if run.end_date else None,
                "step_hours": run.step_hours,
                "initial_equity": run.initial_equity,
                "final_equity": run.final_equity,
                "total_trades": run.total_trades,
                "win_rate": run.win_rate,
                "profit_factor": run.profit_factor,
                "sharpe_ratio": run.sharpe_ratio,
                "max_drawdown_pct": run.max_drawdown_pct,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            },
            "trades_count": len(trades),
            "total_trades": len(trades),
            "offset": offset,
            "limit": limit,
            "trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                    "entry_price": t.entry_price,
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "pnl_pips": t.pnl_pips,
                    "pnl_pct": t.pnl_pct,
                    "executed_lots": t.executed_lots,
                    "confidence": t.confidence,
                    "rationale": t.rationale,
                }
                for t in trades
            ],
        }


async def _execute_background_backtest(days: int, mode: str, initial_equity: float, step_hours: int):
    """Background task to run point-in-time backtest."""
    try:
        from backtest.point_in_time_engine import PointInTimeBacktestEngine
        from config.settings import load_all_config

        settings = load_all_config()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        engine = PointInTimeBacktestEngine(
            start_date=start_date,
            end_date=end_date,
            settings=settings,
            mode=mode,
            step_hours=step_hours,
            initial_equity=initial_equity,
        )
        await engine.run()
        logger.info(f"Dashboard-triggered backtest completed: {engine.run_record.id}")
    except Exception as e:
        logger.error(f"Background backtest failed: {e}", exc_info=True)


@backtest_router.post("/run")
@require_role(Role.OPERATOR)
async def trigger_backtest_run(
    req: BacktestRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    """Trigger an asynchronous backtest run in the background."""
    background_tasks.add_task(
        _execute_background_backtest,
        days=req.days,
        mode=req.mode,
        initial_equity=req.initial_equity,
        step_hours=req.step_hours,
    )
    return {
        "status": "queued",
        "message": f"Backtest queued for {req.days} days in {req.mode} mode with ${req.initial_equity:,.2f} initial equity.",
    }
