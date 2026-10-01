import argparse
import asyncio
import logging
import sys

from benchmark.task_specs import TASKS
from benchmark.model_registry import CANDIDATE_MODELS, get_candidate_models, get_tier_models, get_router_matrix
from benchmark.runner import run_benchmark
from benchmark.report import build_report
from config.settings import load_all_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args():
    p = argparse.ArgumentParser(
        description="Benchmark setiap LLM task-role terhadap model kandidat, "
                    "mendukung live DB, synthetic 2026 fixtures, tier filtering, dan router comparison."
    )
    p.add_argument("--tasks", nargs="*", default=None, help="Subset task id (default: semua atau target_tasks dari tier).")
    p.add_argument("--models", nargs="*", default=None, help="Subset model id.")
    p.add_argument("--tier", choices=["system_one", "cheap_efficient", "cheap_smart", "high_intelligence"],
                   default=None, help="Pilih kelompok tier model & task.")
    p.add_argument("--use-fixtures", action="store_true", default=False,
                   help="Gunakan synthetic market fixtures September 2026 (tanpa perlu DB live terisi).")
    p.add_argument("--compare-routers", action="store_true", default=False,
                   help="Bandingkan model yang sama di direct provider vs OpenRouter vs 9router.")
    p.add_argument("--symbols", nargs="*", default=None,
                   help="Symbol untuk task per-asset (default: symbol pertama di asset_universe).")
    p.add_argument("--judge-model", default="claude-sonnet-5",
                   help="Model tunggal yang menilai output setiap kandidat.")
    p.add_argument("--judge-models", nargs="*", default=None,
                   help="Daftar model untuk Multi-Judge Ensemble (mis. claude-sonnet-5 gpt-4o deepseek-chat).")
    p.add_argument("--reference-model", default="claude-sonnet-5",
                   help="Model yang HANYA dipakai bikin artefak upstream tetap "
                        "(bull claim utk debate_bear, bull+bear utk debate_judge) supaya perbandingan adil.")
    p.add_argument("--concurrency", type=int, default=4,
                   help="Concurrency utk task json/text/custom. Task agent/chat selalu diserialkan.")
    p.add_argument("--mode", choices=["standard", "arena"], default="standard",
                   help="Mode eksekusi: 'standard' (evaluasi task) atau 'arena' (turnamen head-to-head via AlphaArenaTournament).")
    p.add_argument("--output", default="benchmark_report.md")
    return p.parse_args()


async def main():
    args = parse_args()
    settings = load_all_config()
    bench_cfg = settings.get("benchmark", {})

    models = args.models
    tasks = args.tasks

    if args.compare_routers:
        router_mat = get_router_matrix(settings)
        models = []
        for group in router_mat.values():
            models.extend(group)
        models = list(dict.fromkeys(models))
    elif args.tier:
        tier_cfg = bench_cfg.get("tiers", {}).get(args.tier, {})
        if not models:
            models = get_tier_models(args.tier, settings)
        if not tasks and isinstance(tier_cfg, dict) and tier_cfg.get("target_tasks"):
            tasks = tier_cfg["target_tasks"]

    if not models:
        models = get_candidate_models(settings)
    if not tasks:
        tasks = list(TASKS.keys())

    unknown = [t for t in tasks if t not in TASKS]
    if unknown:
        raise SystemExit(f"Task id tidak dikenal: {unknown}. Valid: {list(TASKS.keys())}")

    judge_model = args.judge_model or bench_cfg.get("default_judge_model", "claude-sonnet-5")
    reference_model = args.reference_model or bench_cfg.get("default_reference_model", "claude-sonnet-5")
    use_fixtures = args.use_fixtures or bench_cfg.get("use_fixtures", False)

    print(f"=== MONIKA LLM BENCHMARK ===")
    print(f"Tasks ({len(tasks)}): {tasks}")
    print(f"Models ({len(models)}): {models}")
    print(f"Tier: {args.tier or 'Custom/All'}")
    print(f"Use Fixtures: {use_fixtures}")
    print(f"Concurrency: {args.concurrency}")
    print(f"=============================\n")

    run_id = await run_benchmark(
        task_ids=tasks,
        model_names=models,
        symbols=args.symbols,
        judge_model=judge_model,
        reference_model=reference_model,
        concurrency=args.concurrency,
        judge_models=args.judge_models,
        use_fixtures=use_fixtures,
    )
    report = await build_report(run_id)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nTersimpan di {args.output} (run_id={run_id}); query detail via tabel llm_benchmark_result.")

    if getattr(args, "mode", "standard") == "arena":
        from benchmark.alpha_arena import AlphaArenaTournament
        tournament = AlphaArenaTournament()
        print("\n=== ALPHA ARENA HEAD-TO-HEAD TOURNAMENT ===")
        import itertools
        from database.db import get_session
        from sqlalchemy import select
        from database.models import LLMBenchmarkResult
        try:
            async with get_session() as sess:
                res_rows = (await sess.execute(
                    select(LLMBenchmarkResult).where(LLMBenchmarkResult.run_id == run_id)
                )).scalars().all()
            model_scores: dict[str, list[float]] = {}
            for r in res_rows:
                model_scores.setdefault(r.model_name, []).append(float(r.normalized_score or 0.0))
            for m_a, m_b in itertools.combinations(models, 2):
                scores_a = model_scores.get(m_a, [50.0])
                scores_b = model_scores.get(m_b, [50.0])
                avg_a = sum(scores_a) / len(scores_a) if scores_a else 50.0
                avg_b = sum(scores_b) / len(scores_b) if scores_b else 50.0
                tournament.record_match(
                    m_a, m_b,
                    metrics_a={"pnl_pct": avg_a, "sharpe_ratio": avg_a / 50.0},
                    metrics_b={"pnl_pct": avg_b, "sharpe_ratio": avg_b / 50.0}
                )
            leaderboard = tournament.get_leaderboard()
            print("\n=== ALPHA ARENA LEADERBOARD ===")
            for lb in leaderboard:
                print(f"#{lb['rank']} {lb['name']}: Elo {lb['elo']} (Record: {lb['record']}, WinRate: {lb['win_rate']}%)")
        except Exception as e_arena:
            print(f"Arena tournament error (non-fatal): {e_arena}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
