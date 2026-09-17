import statistics
from sqlalchemy import select
from database.db import get_session
from .db_models import BenchmarkResult


async def build_report(run_id: int) -> str:
    async with get_session() as session:
        rows = (await session.execute(select(BenchmarkResult).where(BenchmarkResult.run_id == run_id))).scalars().all()
    if not rows:
        return "Tidak ada hasil."

    by_task: dict[str, list[BenchmarkResult]] = {}
    for r in rows:
        by_task.setdefault(r.task_id, []).append(r)

    lines = [f"# Laporan LLM Benchmark — run #{run_id}\n"]
    per_model_agg: dict[str, dict] = {}

    for task_id, results in sorted(by_task.items()):
        lines.append(f"\n## {task_id}\n")
        lines.append("| Model | Score | Det.Pass | Token in/out | Cost $ | Latency s | Error |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in sorted(results, key=lambda x: (x.overall_score is None, -(x.overall_score or 0))):
            score = f"{r.overall_score:.1f}" if r.overall_score is not None else "-"
            det = f"{r.deterministic_score:.0%}" if r.deterministic_score is not None else "-"
            err = (r.error or "")[:60]
            lines.append(f"| {r.model_name} | {score} | {det} | {r.input_tokens}/{r.output_tokens} | "
                          f"{r.cost_usd:.5f} | {r.latency_s:.1f} | {err} |")
            agg = per_model_agg.setdefault(r.model_name, {"scores": [], "cost": 0.0, "success": 0, "total": 0})
            agg["total"] += 1
            agg["cost"] += r.cost_usd or 0.0
            if r.error is None:
                agg["success"] += 1
            if r.overall_score is not None:
                agg["scores"].append(r.overall_score)

    lines.append("\n## Leaderboard (semua task yang diuji)\n")
    lines.append("| Model | Avg Score | Success Rate | Total Cost $ | Quality/$ |")
    lines.append("|---|---|---|---|---|")
    board = []
    for model, agg in per_model_agg.items():
        avg_score = statistics.mean(agg["scores"]) if agg["scores"] else 0.0
        sr = agg["success"] / agg["total"] if agg["total"] else 0.0
        qpd = avg_score / agg["cost"] if agg["cost"] > 0 else float("inf")
        board.append((model, avg_score, sr, agg["cost"], qpd))
    for model, avg_score, sr, cost, qpd in sorted(board, key=lambda x: -x[1]):
        qpd_str = "∞ (gratis)" if qpd == float("inf") else f"{qpd:.1f}"
        lines.append(f"| {model} | {avg_score:.2f} | {sr:.0%} | {cost:.4f} | {qpd_str} |")
    return "\n".join(lines)
