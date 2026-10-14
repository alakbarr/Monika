"""
Generate Leaderboard and Detailed Scoring Report for Monika Benchmark (Stage 1 & Stage 2).
"""

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from monika.application.benchmark.benchmark_scorer import (
    generate_leaderboard_data,
    generate_leaderboard_markdown,
)


def main():
    s1_path = REPO_ROOT / "src" / "monika" / "application" / "benchmark" / "results" / "benchmark_stage1_results.json"
    s2_path = REPO_ROOT / "src" / "monika" / "application" / "benchmark" / "results" / "benchmark_stage2_results.json"
    out_json = REPO_ROOT / "src" / "monika" / "application" / "benchmark" / "results" / "benchmark_leaderboard.json"
    out_md = REPO_ROOT / "src" / "monika" / "application" / "benchmark" / "results" / "benchmark_leaderboard.md"

    s1_data = json.load(open(s1_path, encoding="utf-8")).get("results", [])
    s2_data = json.load(open(s2_path, encoding="utf-8")).get("results", [])

    leaderboard = generate_leaderboard_data(s1_data, s2_data)

    print("\n" + "=" * 80)
    print("🏆 MONIKA FRONTIER LLM BENCHMARK LEADERBOARD (9 MODELS)")
    print("=" * 80)
    for item in leaderboard:
        medal = (
            "🥇"
            if item["rank"] == 1
            else "🥈"
            if item["rank"] == 2
            else "🥉"
            if item["rank"] == 3
            else f"#{item['rank']}"
        )
        print(
            f"{medal:<4} {item['display_name']:<30} | "
            f"Score: {item['composite_score']:>5.1f} (S1: {item['stage1_score']:>4.1f}, S2: {item['stage2_score']:>4.1f}) | "
            f"Decision: {item['decision_s2'].upper():<4} | "
            f"Time: {item['total_latency_s']:>6.1f}s | "
            f"Cost: ${item['total_cost_usd']:.4f}"
        )
    print("=" * 80)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2, ensure_ascii=False)

    md_report = generate_leaderboard_markdown(leaderboard)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md_report)

    print(f"\n[OK] Leaderboard saved to:\n  - {out_json}\n  - {out_md}\n")


if __name__ == "__main__":
    main()
