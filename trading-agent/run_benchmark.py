import argparse
import asyncio
import logging
import sys

from benchmark.task_specs import TASKS
from benchmark.model_registry import CANDIDATE_MODELS
from benchmark.runner import run_benchmark
from benchmark.report import build_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def parse_args():
    p = argparse.ArgumentParser(
        description="Benchmark setiap LLM task-role terhadap setiap model kandidat, "
                    "pakai data live dari Postgres/MT5 (tidak ada yang di-hardcode)."
    )
    p.add_argument("--tasks", nargs="*", default=list(TASKS.keys()), help="Subset task id.")
    p.add_argument("--models", nargs="*", default=CANDIDATE_MODELS, help="Subset model id.")
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
    p.add_argument("--output", default="benchmark_report.md")
    return p.parse_args()


async def main():
    args = parse_args()
    unknown = [t for t in args.tasks if t not in TASKS]
    if unknown:
        raise SystemExit(f"Task id tidak dikenal: {unknown}. Valid: {list(TASKS.keys())}")

    run_id = await run_benchmark(
        task_ids=args.tasks,
        model_names=args.models,
        symbols=args.symbols,
        judge_model=args.judge_model,
        reference_model=args.reference_model,
        concurrency=args.concurrency,
        judge_models=args.judge_models
    )
    report = await build_report(run_id)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nTersimpan di {args.output} (run_id={run_id}); query detail via tabel llm_benchmark_result.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
