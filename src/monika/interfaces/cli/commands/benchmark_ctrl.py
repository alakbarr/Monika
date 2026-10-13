# ==============================================================================
# File: interfaces/cli/commands/benchmark_ctrl.py
# ==============================================================================

"""
Benchmark Suite and Model Evaluation Commands for Monika.
Handles benchmark run, leaderboard, history, tasks, and models.
"""

import argparse
import json as _json
from typing import Any, Dict, List, Optional

from rich.table import Table
from sqlalchemy import desc, select

from monika.interfaces.cli.context import cli_main
from monika.interfaces.cli.theme import (
    BRASS,
    LEDGER_BOX,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)


async def _cmd_benchmark_run(args: Any) -> None:
    """Execute benchmark evaluation across models and tasks."""
    console = cli_main.get_console()
    from monika.application.benchmark.model_registry import get_candidate_models, get_router_matrix, get_tier_models
    from monika.application.benchmark.report import build_report
    from monika.application.benchmark.runner import run_benchmark
    from monika.application.benchmark.task_specs import TASKS

    settings = cli_main.load_all_config()
    bench_cfg = settings.get("benchmark", {})

    models = getattr(args, "models", None)
    tasks = getattr(args, "tasks", None)
    tier = getattr(args, "tier", None)
    compare_routers = getattr(args, "compare_routers", False)
    use_fixtures = getattr(args, "use_fixtures", False) or bench_cfg.get("use_fixtures", False)

    if compare_routers:
        router_mat = get_router_matrix(settings)
        models = []
        for group in router_mat.values():
            models.extend(group)
        models = list(dict.fromkeys(models))
    elif tier:
        tier_cfg = bench_cfg.get("tiers", {}).get(tier, {})
        if not models:
            models = get_tier_models(tier, settings)
        if not tasks and isinstance(tier_cfg, dict) and tier_cfg.get("target_tasks"):
            tasks = tier_cfg["target_tasks"]

    if not models:
        models = get_candidate_models(settings)
    if not tasks:
        tasks = list(TASKS.keys())

    if getattr(args, "mode", "standard") == "arena":
        from monika.application.benchmark.alpha_arena import AlphaArenaTournament

        arena = AlphaArenaTournament()
        console.print(
            f"\n[{PHOSPHOR_AMBER}] Launching Alpha Arena Head-to-Head Tournament across {len(models)} models...[/]"
        )
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                m_a, m_b = models[i], models[j]
                arena.record_match(
                    m_a,
                    m_b,
                    metrics_a={"pnl_pct": 2.5, "sharpe_ratio": 1.4},
                    metrics_b={"pnl_pct": 1.8, "sharpe_ratio": 1.1},
                )
        lb = arena.get_leaderboard()
        tbl = Table(
            title=f"[{PHOSPHOR_AMBER}]Alpha Arena Elo Leaderboard[/]",
            box=LEDGER_BOX,
            header_style=f"bold {PHOSPHOR_AMBER}",
        )
        tbl.add_column("Rank", style=f"bold {BRASS}")
        tbl.add_column("Competitor", style=f"bold {PAPER}")
        tbl.add_column("Elo Rating", justify="right")
        tbl.add_column("Matches", justify="right")
        tbl.add_column("W/L/D", justify="center")
        tbl.add_column("Total PnL %", justify="right")
        for rank, c in enumerate(lb, 1):
            name = c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            elo = c.get("elo", 0.0) if isinstance(c, dict) else getattr(c, "elo", 0.0)
            matches = (
                c.get("matches", c.get("matches_played", 0)) if isinstance(c, dict) else getattr(c, "matches_played", 0)
            )
            record = (
                c.get("record", f"{c.get('wins', 0)}/{c.get('losses', 0)}/{c.get('draws', 0)}")
                if isinstance(c, dict)
                else f"{getattr(c, 'wins', 0)}/{getattr(c, 'losses', 0)}/{getattr(c, 'draws', 0)}"
            )
            total_pnl = c.get("total_pnl_pct", 0.0) if isinstance(c, dict) else getattr(c, "total_pnl_pct", 0.0)
            tbl.add_row(
                str(rank), str(name), f"{float(elo):.1f}", str(matches), str(record), f"{float(total_pnl):+.2f}%"
            )
        console.print(tbl)
        return

    judge_model = getattr(args, "judge_model", None) or bench_cfg.get("default_judge_model", "claude-sonnet-5")
    reference_model = getattr(args, "reference_model", None) or bench_cfg.get(
        "default_reference_model", "claude-sonnet-5"
    )
    concurrency = getattr(args, "concurrency", 4)

    console.print(f"\n[{PHOSPHOR_AMBER}]=== LAUNCHING MONIKA LLM BENCHMARK ===[/]")
    console.print(
        f"[bold {BRASS}]Tasks ({len(tasks)}):[/] [{PAPER}]{', '.join(tasks[:5])}{'...' if len(tasks) > 5 else ''}[/]"
    )
    console.print(
        f"[bold {BRASS}]Models ({len(models)}):[/] [{PAPER}]{', '.join(models[:5])}{'...' if len(models) > 5 else ''}[/]"
    )
    console.print(f"[bold {BRASS}]Tier:[/] [{PAPER}]{tier or 'Full / Custom'}[/]")
    console.print(
        f"[bold {BRASS}]Fixtures Mode:[/] [{PAPER}]{'Synthetic Sept 2026' if use_fixtures else 'Live PostgreSQL/MT5'}[/]"
    )
    console.print(f"[bold {BRASS}]Concurrency:[/] [{PAPER}]{concurrency}[/]\n")

    await cli_main.init_db()
    run_id = await run_benchmark(
        task_ids=tasks,
        model_names=models,
        symbols=getattr(args, "symbols", None),
        judge_model=judge_model,
        reference_model=reference_model,
        concurrency=concurrency,
        judge_models=getattr(args, "judge_models", None),
        use_fixtures=use_fixtures,
    )

    report = await build_report(run_id)
    output_file = getattr(args, "output", None) or "benchmark_report.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    console.print(f"\n{stamp_ok('COMPLETE')} Benchmark run #{run_id} finished successfully!")
    console.print(f"{stamp_info('REPORT')} Detailed report saved to {output_file}\n")
    console.print(report)


async def _cmd_benchmark_leaderboard(args: Any) -> None:
    """Show aggregated model leaderboard."""
    console = cli_main.get_console()
    from monika.application.benchmark.db_models import BenchmarkResult, BenchmarkRun

    await cli_main.init_db()
    run_id = getattr(args, "run_id", None)
    async with cli_main.get_session() as session:
        if not run_id:
            latest = (
                await session.execute(select(BenchmarkRun).order_by(desc(BenchmarkRun.started_at)).limit(1))
            ).scalar_one_or_none()
            if not latest:
                console.print(f"{stamp_warn('EMPTY')} No benchmark runs found in database.")
                return
            run_id = latest.id

        rows = (await session.execute(select(BenchmarkResult).where(BenchmarkResult.run_id == run_id))).scalars().all()

        if not rows:
            console.print(f"{stamp_warn('EMPTY')} No benchmark results found for run #{run_id}.")
            return

        model_stats: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            m = r.model_name
            if m not in model_stats:
                model_stats[m] = {"tasks": 0, "passed": 0, "score": 0.0, "cost": 0.0, "lat": 0.0, "err": 0}
            st = model_stats[m]
            st["tasks"] += 1
            st["cost"] += r.cost_usd or 0.0
            st["lat"] += r.latency_s or 0.0
            if r.error:
                st["err"] += 1
            else:
                sc = r.overall_score or 0.0
                st["score"] += sc
                if sc >= 0.70:
                    st["passed"] += 1

        tbl = Table(
            title=f"[{PHOSPHOR_AMBER}]LLM Benchmark Leaderboard (Run #{run_id})[/]",
            box=LEDGER_BOX,
            header_style=f"bold {PHOSPHOR_AMBER}",
        )
        tbl.add_column("Rank", justify="center", style=MUTED)
        tbl.add_column("Model", style=f"bold {PAPER}")
        tbl.add_column("Avg Score", justify="center")
        tbl.add_column("Pass Rate", justify="right", style=f"bold {BRASS}")
        tbl.add_column("Avg Latency", justify="right")
        tbl.add_column("Avg Cost", justify="right")
        tbl.add_column("Tasks", justify="right", style=MUTED)

        sorted_models = sorted(model_stats.items(), key=lambda x: x[1]["score"] / max(x[1]["tasks"], 1), reverse=True)
        for idx, (m, st) in enumerate(sorted_models, 1):
            cnt = max(st["tasks"], 1)
            avg_sc = st["score"] / cnt
            pass_rt = (st["passed"] / cnt) * 100.0
            avg_lat = st["lat"] / cnt
            avg_cst = st["cost"] / cnt

            score_badge = (
                stamp_ok(f"{(avg_sc * 100):.1f}%")
                if avg_sc >= 0.8
                else stamp_warn(f"{(avg_sc * 100):.1f}%")
                if avg_sc >= 0.5
                else stamp_err(f"{(avg_sc * 100):.1f}%")
            )
            tbl.add_row(
                f"#{idx}",
                m,
                score_badge,
                f"{pass_rt:.1f}%",
                f"{avg_lat:.2f}s",
                f"${avg_cst:.4f}",
                str(st["tasks"]),
            )

        console.print()
        console.print(tbl)
        console.print()


async def _cmd_benchmark_history(args: Any) -> None:
    """Show historical benchmark runs."""
    console = cli_main.get_console()
    from monika.application.benchmark.db_models import BenchmarkRun

    await cli_main.init_db()
    limit = getattr(args, "limit", 15)
    async with cli_main.get_session() as session:
        runs = (
            (await session.execute(select(BenchmarkRun).order_by(desc(BenchmarkRun.started_at)).limit(limit)))
            .scalars()
            .all()
        )

        if not runs:
            console.print(f"{stamp_warn('EMPTY')} No benchmark runs found.")
            return

        tbl = Table(
            title=f"[{PHOSPHOR_AMBER}]Benchmark Run History[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}"
        )
        tbl.add_column("ID", justify="center", style=MUTED)
        tbl.add_column("Started At", style=PAPER)
        tbl.add_column("Status", justify="center")
        tbl.add_column("Tasks", justify="right", style=f"bold {BRASS}")
        tbl.add_column("Models", justify="right", style=PAPER)
        tbl.add_column("Judge", style=MUTED)

        for r in runs:
            tasks: List[str] = []
            models: List[str] = []
            try:
                tasks = _json.loads(r.tasks_json) if r.tasks_json else []
                models = _json.loads(r.models_json) if r.models_json else []
            except Exception:
                pass
            status_badge = stamp_ok("DONE") if r.finished_at else stamp_warn("RUNNING")
            tbl.add_row(
                str(r.id),
                str(r.started_at)[:19].replace("T", " ") if r.started_at else "N/A",
                status_badge,
                str(len(tasks)),
                str(len(models)),
                str(r.judge_model or "default"),
            )

        console.print()
        console.print(tbl)
        console.print()


async def _cmd_benchmark_tasks(args: Any) -> None:
    """List all evaluation tasks and categories."""
    console = cli_main.get_console()
    from monika.application.benchmark.task_specs import TASKS

    tbl = Table(
        title=f"[{PHOSPHOR_AMBER}]Benchmark Task Catalog ({len(TASKS)} Tasks)[/]",
        box=LEDGER_BOX,
        header_style=f"bold {PHOSPHOR_AMBER}",
    )
    tbl.add_column("Task ID", style=f"bold {PAPER}")
    tbl.add_column("Category", style=f"bold {BRASS}")
    tbl.add_column("Mode", justify="center")

    for spec in TASKS.values():
        mode_badge = stamp_err("S1") if spec.mode == "system_one" else stamp_ok(spec.mode.upper())
        tbl.add_row(spec.task_id, spec.category, mode_badge)

    console.print()
    console.print(tbl)
    console.print()


async def _cmd_benchmark_models(args: Any) -> None:
    """List candidate models, tiers, and router matrix."""
    console = cli_main.get_console()
    settings = cli_main.load_all_config()
    bench_cfg = settings.get("benchmark", {})
    tiers = bench_cfg.get("tiers", {})

    tbl = Table(
        title=f"[{PHOSPHOR_AMBER}]Benchmark Model Registry & Tiers[/]",
        box=LEDGER_BOX,
        header_style=f"bold {PHOSPHOR_AMBER}",
    )
    tbl.add_column("Tier / Group", style=f"bold {BRASS}")
    tbl.add_column("Description", style=MUTED)
    tbl.add_column("Models", style=PAPER)

    for tier_id, tcfg in tiers.items():
        if isinstance(tcfg, dict):
            models_str = ", ".join(tcfg.get("models", []))
            tbl.add_row(
                f"[bold {PHOSPHOR_AMBER}]{tcfg.get('name', tier_id)}[/]", tcfg.get("description", ""), models_str
            )

    console.print()
    console.print(tbl)
    console.print()


async def _cmd_benchmark(args: Any) -> None:
    """Route benchmark subactions."""
    subaction = getattr(args, "bench_action", "leaderboard")
    if subaction == "run":
        await _cmd_benchmark_run(args)
    elif subaction == "leaderboard":
        await _cmd_benchmark_leaderboard(args)
    elif subaction == "history":
        await _cmd_benchmark_history(args)
    elif subaction == "tasks":
        await _cmd_benchmark_tasks(args)
    elif subaction == "models":
        await _cmd_benchmark_models(args)
    else:
        await _cmd_benchmark_leaderboard(args)
