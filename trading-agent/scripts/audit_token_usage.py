"""
Audit Token Usage CLI Tool — Analisis mendalam konsumsi token AI per Task Role & Subsystem.

Usage:
    python scripts/audit_token_usage.py
    python scripts/audit_token_usage.py --days 7 --by-role
    python scripts/audit_token_usage.py --hours 12 --by-subsystem
    python scripts/audit_token_usage.py --by-symbol
    python scripts/audit_token_usage.py --json
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import asyncio

import argparse
import json
from utils.analytics.token_auditor import TokenAuditor


async def run_audit(args):
    hours = args.hours
    if args.days:
        hours = args.days * 24

    summary = await TokenAuditor.get_summary(hours=hours)

    if args.json:
        full_data = {
            "summary": summary,
            "by_role": await TokenAuditor.get_role_breakdown(hours=hours),
            "by_subsystem": await TokenAuditor.get_subsystem_breakdown(hours=hours),
            "by_symbol": await TokenAuditor.get_symbol_breakdown(hours=hours),
            "by_provider": await TokenAuditor.get_provider_breakdown(hours=hours),
        }
        print(json.dumps(full_data, indent=2))
        return

    # Text / Table Output
    print("\n" + "=" * 80)
    print(f"📊 AI AGENT TOKEN AUDIT REPORT ({hours} Hours Window)")
    print("=" * 80)
    print(f"Total API Calls        : {summary['total_calls']:,} (Success: {summary['success_count']:,} | Fallbacks: {summary['fallback_count']:,} | Errors: {summary['error_count']:,})")
    print(f"Total Tokens Consumed  : {summary['total_tokens']:,} (Input: {summary['input_tokens']:,} | Output: {summary['output_tokens']:,})")
    print(f"Prompt Caching Savings : {summary['cached_tokens']:,} tokens ({summary['cache_hit_rate_pct']:.2f}% hit rate)")
    print(f"Total Cost Estimate    : ${summary['total_cost_usd']:.6f} USD")
    if summary['avg_latency_ms'] > 0:
        print(f"Average API Latency    : {summary['avg_latency_ms']:.1f} ms")
    print("=" * 80)

    if args.by_subsystem or not (args.by_role or args.by_symbol or args.by_provider or args.recent):
        print("\n📂 BREAKDOWN PER SUBSYSTEM:")
        print(f"{'Subsystem':<15} | {'Calls':<8} | {'Total Tokens':<14} | {'Cached':<10} | {'Cost (USD)':<12} | {'% Cost':<8}")
        print("-" * 75)
        subsystems = await TokenAuditor.get_subsystem_breakdown(hours=hours)
        for s in subsystems:
            print(f"{s['subsystem']:<15} | {s['calls']:<8} | {s['sum_total']:<14,} | {s['sum_cached']:<10,} | ${s['sum_cost_usd']:<11.4f} | {s['pct_cost']:>5.1f}%")

    if args.by_role or not (args.by_subsystem or args.by_symbol or args.by_provider or args.recent):
        print("\n🤖 BREAKDOWN PER TASK ROLE (32 Task Roles):")
        print(f"{'Task Role':<35} | {'Subsystem':<12} | {'Calls':<6} | {'Avg In':<9} | {'Avg Out':<8} | {'Avg Total':<10} | {'Cost (USD)':<10}")
        print("-" * 100)
        roles = await TokenAuditor.get_role_breakdown(hours=hours)
        for r in roles:
            print(f"{r['task_role']:<35} | {r['subsystem']:<12} | {r['calls']:<6} | {r['avg_input']:<9,.0f} | {r['avg_output']:<8,.0f} | {r['avg_total']:<10,.0f} | ${r['sum_cost_usd']:<9.4f}")

    if args.by_symbol:
        print("\n💱 BREAKDOWN PER SYMBOL / ASSET:")
        print(f"{'Symbol':<15} | {'Calls':<8} | {'Total Tokens':<14} | {'Cached':<10} | {'Cost (USD)':<12}")
        print("-" * 65)
        symbols = await TokenAuditor.get_symbol_breakdown(hours=hours)
        for sym in symbols:
            print(f"{sym['symbol']:<15} | {sym['calls']:<8} | {sym['sum_total']:<14,} | {sym['sum_cached']:<10,} | ${sym['sum_cost_usd']:<11.4f}")

    if args.by_provider:
        print("\n🏢 BREAKDOWN PER PROVIDER & MODEL:")
        print(f"{'Provider':<12} | {'Model':<32} | {'Calls':<6} | {'Total Tokens':<14} | {'Cost (USD)':<10}")
        print("-" * 80)
        providers = await TokenAuditor.get_provider_breakdown(hours=hours)
        for p in providers:
            print(f"{p['provider']:<12} | {p['model_name']:<32} | {p['calls']:<6} | {p['sum_total']:<14,} | ${p['sum_cost_usd']:<9.4f}")

    if args.recent:
        print(f"\n⏱️ RECENT {args.recent} TOKEN LOG ENTRIES:")
        print(f"{'Timestamp':<20} | {'Role/Task':<30} | {'Model':<25} | {'In/Out':<14} | {'Cost':<9}")
        print("-" * 105)
        recent = await TokenAuditor.get_recent_logs(limit=args.recent)
        for rec in recent:
            ts = rec['timestamp'][:19] if rec['timestamp'] else "-"
            role_label = rec['task_role'] or rec['task_name']
            in_out = f"{rec['input_tokens']}/{rec['output_tokens']}"
            cost_str = f"${rec['cost_estimate']:.4f}" if rec['cost_estimate'] is not None else "$0.0000"
            print(f"{ts:<20} | {role_label[:30]:<30} | {rec['model_name'][:25]:<25} | {in_out:<14} | {cost_str:<9}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Audit token consumption of AI Trading Agent.")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours (default: 24)")
    parser.add_argument("--days", type=int, default=None, help="Time window in days (overrides --hours)")
    parser.add_argument("--by-role", action="store_true", help="Show breakdown per task role")
    parser.add_argument("--by-subsystem", action="store_true", help="Show breakdown per subsystem")
    parser.add_argument("--by-symbol", action="store_true", help="Show breakdown per currency/symbol")
    parser.add_argument("--by-provider", action="store_true", help="Show breakdown per provider & model")
    parser.add_argument("--recent", type=int, default=0, help="Show N most recent token log entries")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.run(run_audit(args), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_audit(args))


if __name__ == "__main__":
    main()
