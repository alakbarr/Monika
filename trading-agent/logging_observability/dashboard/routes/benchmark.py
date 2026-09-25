# ==============================================================================
# File: logging_observability/dashboard/routes/benchmark.py
# Description: REST API endpoints for LLM Benchmark suite management & analytics
# ==============================================================================

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func

from database.db import get_session
from benchmark.db_models import BenchmarkRun, BenchmarkResult
from benchmark.task_specs import TASKS
from benchmark.model_registry import CANDIDATE_MODELS, get_candidate_models, get_tier_models, get_router_matrix
from benchmark.runner import run_benchmark
from benchmark.report import build_report
from config.settings import load_all_config
from logging_observability.dashboard.rbac import Role, require_role
from logging_observability.dashboard.routes.common import _safe_json, broadcast_live_event

logger = logging.getLogger("TradingAgent.Dashboard.Benchmark")

benchmark_router = APIRouter(prefix="/api/benchmark", tags=["Benchmark"])


class BenchmarkRunRequest(BaseModel):
    tasks: Optional[List[str]] = Field(default=None, description="Subset task IDs to evaluate")
    models: Optional[List[str]] = Field(default=None, description="Subset model names/IDs to evaluate")
    tier: Optional[str] = Field(default=None, description="Tier filter: system_one, cheap_efficient, cheap_smart, high_intelligence")
    symbols: Optional[List[str]] = Field(default=None, description="Asset symbols for per-asset analysis")
    judge_model: Optional[str] = Field(default=None, description="Judge model name")
    judge_models: Optional[List[str]] = Field(default=None, description="Judge ensemble model names")
    reference_model: Optional[str] = Field(default=None, description="Upstream reference model")
    concurrency: Optional[int] = Field(default=4, ge=1, le=16, description="Async job concurrency")
    use_fixtures: Optional[bool] = Field(default=False, description="Use synthetic September 2026 market fixtures")
    compare_routers: Optional[bool] = Field(default=False, description="Test router matrix (direct vs OpenRouter vs 9router)")


@benchmark_router.get("/tasks")
@require_role(Role.VIEWER)
async def list_benchmark_tasks(request: Request) -> Dict[str, Any]:
    """List all available benchmark evaluation tasks."""
    task_list = [
        {
            "id": spec.task_id,
            "category": spec.category,
            "mode": spec.mode,
            "is_system_one": spec.mode == "system_one",
        }
        for spec in TASKS.values()
    ]
    return {
        "total": len(task_list),
        "tasks": task_list,
        "categories": sorted(list(set(t["category"] for t in task_list))),
    }


@benchmark_router.get("/models")
@require_role(Role.VIEWER)
async def list_benchmark_models(request: Request) -> Dict[str, Any]:
    """List model registry candidates, tiers, and router matrices."""
    settings = load_all_config()
    bench_cfg = settings.get("benchmark", {})
    candidates = get_candidate_models(settings)
    tiers = bench_cfg.get("tiers", {})
    router_matrix = get_router_matrix(settings)

    return {
        "candidates": candidates,
        "tiers": tiers,
        "router_matrix": router_matrix,
        "defaults": {
            "judge_model": bench_cfg.get("default_judge_model", "claude-sonnet-5"),
            "reference_model": bench_cfg.get("default_reference_model", "claude-sonnet-5"),
            "default_symbol": bench_cfg.get("default_symbol", "EURUSD"),
            "use_fixtures": bench_cfg.get("use_fixtures", False),
        }
    }


@benchmark_router.get("/runs")
@require_role(Role.VIEWER)
async def list_benchmark_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List past benchmark runs."""
    try:
        async with get_session() as session:
            stmt = (
                select(BenchmarkRun)
                .order_by(desc(BenchmarkRun.started_at))
                .offset(offset)
                .limit(limit)
            )
            runs = (await session.execute(stmt)).scalars().all()

            results = []
            for r in runs:
                tasks = _safe_json(r.tasks_json, [])
                models = _safe_json(r.models_json, [])
                results.append({
                    "id": r.id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "judge_model": r.judge_model,
                    "reference_model": r.reference_model,
                    "tasks_count": len(tasks) if isinstance(tasks, list) else 0,
                    "models_count": len(models) if isinstance(models, list) else 0,
                    "is_running": r.finished_at is None,
                })

            return {
                "total": len(results),
                "runs": results,
            }
    except Exception as e:
        logger.warning(f"Error querying benchmark runs (table may not exist yet): {e}")
        return {
            "total": 0,
            "runs": [],
        }


@benchmark_router.get("/runs/{run_id}")
@require_role(Role.VIEWER)
async def get_benchmark_run_detail(
    run_id: int,
    request: Request,
) -> Dict[str, Any]:
    """Get full details and individual results for a benchmark run."""
    async with get_session() as session:
        run = await session.get(BenchmarkRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Benchmark run {run_id} not found")

        stmt = (
            select(BenchmarkResult)
            .where(BenchmarkResult.run_id == run_id)
            .order_by(BenchmarkResult.task_id.asc(), BenchmarkResult.model_name.asc())
        )
        items = (await session.execute(stmt)).scalars().all()

        report_md = await build_report(run_id)

        return {
            "run": {
                "id": run.id,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "judge_model": run.judge_model,
                "reference_model": run.reference_model,
                "tasks": _safe_json(run.tasks_json, []),
                "models": _safe_json(run.models_json, []),
            },
            "total_results": len(items),
            "report_markdown": report_md,
            "results": [
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "category": item.category,
                    "model_name": item.model_name,
                    "provider": item.provider,
                    "context_key": item.context_key,
                    "cost_usd": item.cost_usd,
                    "latency_s": item.latency_s,
                    "input_tokens": item.input_tokens,
                    "output_tokens": item.output_tokens,
                    "schema_valid": item.schema_valid,
                    "deterministic_score": item.deterministic_score,
                    "judge_overall": item.judge_overall,
                    "overall_score": item.overall_score,
                    "judge_scores": _safe_json(item.judge_scores_json, {}),
                    "error": item.error,
                }
                for item in items
            ]
        }


@benchmark_router.get("/quadrant/{run_id}")
@require_role(Role.VIEWER)
async def get_benchmark_quadrant_chart_data(
    run_id: int,
    request: Request,
) -> Dict[str, Any]:
    """Get quadrant matrix data (Cost / Latency vs Quality Score) for bubble chart visualization."""
    async with get_session() as session:
        stmt = select(BenchmarkResult).where(BenchmarkResult.run_id == run_id)
        items = (await session.execute(stmt)).scalars().all()

        points = []
        for item in items:
            if item.error and not item.overall_score:
                continue
            points.append({
                "model_name": item.model_name,
                "task_id": item.task_id,
                "category": item.category,
                "cost_usd": item.cost_usd or 0.0,
                "latency_s": item.latency_s or 0.0,
                "overall_score": item.overall_score or 0.0,
                "total_tokens": (item.input_tokens or 0) + (item.output_tokens or 0),
                "is_error": bool(item.error),
            })

        return {
            "run_id": run_id,
            "points": points,
        }


@benchmark_router.get("/leaderboard")
@require_role(Role.VIEWER)
async def get_benchmark_leaderboard(
    request: Request,
    run_id: Optional[int] = Query(default=None),
) -> Dict[str, Any]:
    """Get aggregated model rankings across tasks (Accuracy, Cost, Latency, ELO)."""
    try:
        async with get_session() as session:
            if run_id:
                stmt = select(BenchmarkResult).where(BenchmarkResult.run_id == run_id)
            else:
                # Latest run
                latest_run = (await session.execute(
                    select(BenchmarkRun).order_by(desc(BenchmarkRun.started_at)).limit(1)
                )).scalar_one_or_none()
                if not latest_run:
                    return {"leaderboard": [], "message": "No benchmark runs found."}
                run_id = latest_run.id
                stmt = select(BenchmarkResult).where(BenchmarkResult.run_id == run_id)

            rows = (await session.execute(stmt)).scalars().all()

            model_stats: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                m = r.model_name
                if m not in model_stats:
                    model_stats[m] = {
                        "model_name": m,
                        "total_tasks": 0,
                        "passed_tasks": 0,
                        "total_score": 0.0,
                        "total_cost": 0.0,
                        "total_latency": 0.0,
                        "total_tokens": 0,
                        "errors": 0,
                    }
                st = model_stats[m]
                st["total_tasks"] += 1
                st["total_cost"] += (r.cost_usd or 0.0)
                st["total_latency"] += (r.latency_s or 0.0)
                st["total_tokens"] += (r.input_tokens or 0) + (r.output_tokens or 0)
                if r.error:
                    st["errors"] += 1
                else:
                    score = r.overall_score if r.overall_score is not None else 0.0
                    st["total_score"] += score
                    if score >= 0.70:
                        st["passed_tasks"] += 1

            leaderboard = []
            for m, st in model_stats.items():
                cnt = max(st["total_tasks"], 1)
                avg_score = st["total_score"] / cnt
                avg_latency = st["total_latency"] / cnt
                avg_cost = st["total_cost"] / cnt
                pass_rate = (st["passed_tasks"] / cnt) * 100.0

                # Rank score = composite of Quality (70%) + Cost efficiency (15%) + Speed (15%)
                cost_penalty = min(avg_cost * 100.0, 0.5)
                latency_penalty = min(avg_latency / 20.0, 0.5)
                composite_rank = max(0.0, avg_score - cost_penalty - latency_penalty)

                leaderboard.append({
                    "model_name": m,
                    "avg_score": round(avg_score, 3),
                    "pass_rate_pct": round(pass_rate, 1),
                    "avg_latency_s": round(avg_latency, 2),
                    "avg_cost_usd": round(avg_cost, 5),
                    "total_tokens": st["total_tokens"],
                    "total_tasks": st["total_tasks"],
                    "errors": st["errors"],
                    "composite_rank": round(composite_rank, 3),
                })

            leaderboard.sort(key=lambda x: x["composite_rank"], reverse=True)
            return {
                "run_id": run_id,
                "leaderboard": leaderboard,
            }
    except Exception as e:
        logger.warning(f"Error querying benchmark leaderboard (table may not exist yet): {e}")
        return {
            "run_id": None,
            "leaderboard": [],
        }


async def _execute_background_benchmark(
    task_ids: List[str],
    model_names: List[str],
    symbols: Optional[List[str]],
    judge_model: str,
    reference_model: str,
    concurrency: int,
    judge_models: Optional[List[str]],
    use_fixtures: bool,
):
    """Run benchmark asynchronously in background task and broadcast updates."""
    try:
        await broadcast_live_event("benchmark_started", {
            "tasks_count": len(task_ids),
            "models_count": len(model_names),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        run_id = await run_benchmark(
            task_ids=task_ids,
            model_names=model_names,
            symbols=symbols,
            judge_model=judge_model,
            reference_model=reference_model,
            concurrency=concurrency,
            judge_models=judge_models,
            use_fixtures=use_fixtures,
        )

        await broadcast_live_event("benchmark_completed", {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Dashboard-triggered benchmark completed successfully: run_id={run_id}")
    except Exception as e:
        logger.error(f"Background benchmark run failed: {e}", exc_info=True)
        await broadcast_live_event("benchmark_failed", {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@benchmark_router.post("/run")
@require_role(Role.OPERATOR)
async def trigger_benchmark_run(
    req: BenchmarkRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> Dict[str, Any]:
    """Trigger a new asynchronous benchmark execution."""
    settings = load_all_config()
    bench_cfg = settings.get("benchmark", {})

    models = req.models
    tasks = req.tasks

    if req.compare_routers:
        router_mat = get_router_matrix(settings)
        models = []
        for group in router_mat.values():
            models.extend(group)
        models = list(dict.fromkeys(models))
    elif req.tier:
        tier_cfg = bench_cfg.get("tiers", {}).get(req.tier, {})
        if not models:
            models = get_tier_models(req.tier, settings)
        if not tasks and isinstance(tier_cfg, dict) and tier_cfg.get("target_tasks"):
            tasks = tier_cfg["target_tasks"]

    if not models:
        models = get_candidate_models(settings)
    if not tasks:
        tasks = list(TASKS.keys())

    judge_model = req.judge_model or bench_cfg.get("default_judge_model", "claude-sonnet-5")
    reference_model = req.reference_model or bench_cfg.get("default_reference_model", "claude-sonnet-5")
    use_fixtures = req.use_fixtures if req.use_fixtures is not None else bench_cfg.get("use_fixtures", False)

    background_tasks.add_task(
        _execute_background_benchmark,
        task_ids=tasks,
        model_names=models,
        symbols=req.symbols,
        judge_model=judge_model,
        reference_model=reference_model,
        concurrency=req.concurrency or 4,
        judge_models=req.judge_models,
        use_fixtures=use_fixtures,
    )

    return {
        "status": "queued",
        "message": f"Benchmark queued: {len(tasks)} tasks evaluated against {len(models)} models.",
        "tasks_count": len(tasks),
        "models_count": len(models),
        "tier": req.tier or "Custom",
        "use_fixtures": use_fixtures,
    }
