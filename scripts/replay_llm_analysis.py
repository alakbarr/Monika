"""Run a point-in-time LLM replay for stored per-asset analyses.

Usage (from the repository root):

    venv\\Scripts\\python.exe scripts/replay_llm_analysis.py ^
        --contexts C:\\path\\to\\contexts.json ^
        --static-prompt C:\\path\\to\\static_prompt.txt ^
        --tools C:\\path\\to\\tools.json ^
        --date-prefix 2026-10-16 ^
        --output C:\\path\\to\\replay_results.json

The contexts file is the extracted historical analysis list (messages,
decision, final submit). The static prompt and tool schemas must be extracted
from the historical git commit that produced those analyses; the dynamic
overlay is already inside the first stored user message.

This script never writes to the production database. It calls
``GeminiProvider.run_tool_agent``, which does not persist token usage, and it
never performs live tool lookups: a replay that asks for another tool receives
a deterministic "replay unavailable" result.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from monika.application.evals.llm_replay import (
    audit_sl_geometry,
    parse_sl_risk_inputs,
    run_decision_replay,
    summarize_results,
)
from monika.core.config.settings import load_settings
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.interfaces.cli.platform_compat import ensure_utf8_streams


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_user_prompt(record: dict[str, Any]) -> str:
    prompt = record.get("first_user_prompt")
    if isinstance(prompt, str):
        return prompt
    messages = record.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        content = messages[0].get("content")
        if isinstance(content, str):
            return content
    return ""


def _select_records(
    records: list[Any],
    analysis_ids: list[int],
    date_prefix: str | None,
) -> list[dict[str, Any]]:
    wanted = set(analysis_ids)
    selected: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if wanted and record.get("analysis_id") not in wanted:
            continue
        if date_prefix and not str(record.get("generated_at") or "").startswith(date_prefix):
            continue
        selected.append(record)
    return selected


def _apply_mismatch_risk_audit(result: dict[str, Any], record: dict[str, Any]) -> None:
    """Resolve divergent proposals with the historical SL geometry rule.

    Raw matches are already equivalent to the stored, validated final submit;
    they do not need a second gate. Only a divergent replay proposal is checked,
    because the deterministic rule is the mechanism that prevents an invalid
    LLM proposal from becoming a trade.
    """
    original_value = result.get("original_submit")
    replay_value = result.get("replay_submit")
    original = dict(original_value) if isinstance(original_value, dict) else {}
    replay = dict(replay_value) if isinstance(replay_value, dict) else {}
    comparison = result.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    replay_decision = replay.get("decision")

    if comparison.get("decision_match") is True:
        result["risk_audit"] = {
            "risk_checked": False,
            "risk_blocked": False,
            "effective_decision": replay_decision,
            "reason": "raw decision matches the stored validated decision",
        }
        result["effective_decision"] = replay_decision
        result["effective_match"] = True
        return

    risk_inputs = parse_sl_risk_inputs(
        _first_user_prompt(record),
        str(record.get("symbol") or ""),
        str(original.get("rationale") or ""),
    )
    entry_condition = replay.get("entry_condition")
    entry = entry_condition.get("price") if isinstance(entry_condition, dict) else None
    if entry is None:
        entry = risk_inputs["fallback_entry"]
    audit = audit_sl_geometry(
        decision=str(replay_decision) if replay_decision is not None else None,
        entry_price=entry,
        stop_loss=replay.get("stop_loss"),
        atr_h4=risk_inputs["atr_h4"],
        adr_ceiling=risk_inputs["adr_ceiling"],
        atr_multiplier=risk_inputs["atr_multiplier"],
    )
    result["risk_audit"] = audit
    result["effective_decision"] = audit.get("effective_decision")
    result["effective_match"] = audit.get("effective_decision") == original.get("decision")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contexts", required=True, help="JSON list of extracted historical analyses")
    parser.add_argument("--static-prompt", required=True, help="Exact historical static system prompt")
    parser.add_argument("--tools", required=True, help="Exact historical tool schema JSON")
    parser.add_argument("--analysis-id", type=int, action="append", default=[], help="Repeatable analysis id")
    parser.add_argument("--date-prefix", default=None, help="Select generated_at values with this prefix")
    parser.add_argument("--output", default="replay_results.json", help="Result JSON path")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--thinking", default="high")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--max-tool-turns", type=int, default=12)
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=240.0, help="Per-provider-call timeout in seconds")
    return parser


def main() -> int:
    ensure_utf8_streams()
    args = _build_parser().parse_args()

    contexts_path = Path(args.contexts)
    static_prompt_path = Path(args.static_prompt)
    tools_path = Path(args.tools)
    output_path = Path(args.output)

    records_value = _load_json(contexts_path)
    if not isinstance(records_value, list):
        print("contexts must be a JSON list", file=sys.stderr)
        return 2
    selected = _select_records(records_value, args.analysis_id, args.date_prefix)
    if not selected:
        print("no analyses selected", file=sys.stderr)
        return 2

    static_prompt = static_prompt_path.read_text(encoding="utf-8")
    tools_value = _load_json(tools_path)
    if not isinstance(tools_value, list):
        print("tools must be a JSON list", file=sys.stderr)
        return 2
    tools: list[dict[str, Any]] = [tool for tool in tools_value if isinstance(tool, dict)]

    print(f"contexts={contexts_path} selected={len(selected)}")
    print(f"static_chars={len(static_prompt)} sha256={hashlib.sha256(static_prompt.encode('utf-8')).hexdigest()}")
    print(f"tools={len(tools)} sha256={hashlib.sha256(tools_path.read_bytes()).hexdigest()}")
    print("selected=" + json.dumps([(record.get("analysis_id"), record.get("symbol")) for record in selected]))

    settings = load_settings()
    provider = GeminiProvider(
        args.model,
        settings=settings,
        thinking_level=args.thinking,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_tool_turns=args.max_tool_turns,
    )
    print(
        f"provider={provider.resolved_model} thinking={provider.thinking_level} "
        f"free_keys={len(provider.free_api_keys)} paid_key={bool(provider.paid_api_key)}"
    )
    if not provider.free_api_keys and not provider.paid_api_key:
        print("no Gemini API keys available", file=sys.stderr)
        return 1

    async def run() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for record in selected:
            print(
                f"\n=== replay {record.get('analysis_id')} {record.get('symbol')} stored={record.get('decision')} ===",
                flush=True,
            )
            try:
                result = await run_decision_replay(
                    provider,
                    record,
                    tools=tools,
                    system_prompt=static_prompt,
                    max_turns=args.max_turns,
                    timeout_seconds=args.timeout,
                )
            except ValueError as exc:
                print(f"  skipped: {exc}", flush=True)
                continue
            _apply_mismatch_risk_audit(result, record)
            results.append(result)
            comparison = result.get("comparison")
            comparison = comparison if isinstance(comparison, dict) else {}
            risk_audit = result.get("risk_audit")
            risk_audit = risk_audit if isinstance(risk_audit, dict) else {}
            print(
                f"  status={result.get('status')} stored={comparison.get('original_decision')} "
                f"raw={comparison.get('replay_decision')} raw_match={comparison.get('decision_match')} "
                f"effective={result.get('effective_decision')} effective_match={result.get('effective_match')} "
                f"risk_blocked={risk_audit.get('risk_blocked')} tokens={result.get('usage_total')}",
                flush=True,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        return results

    results = asyncio.run(run())
    if not results:
        print("no replay results", file=sys.stderr)
        return 1

    summary = summarize_results(results)
    summary_path = output_path.with_suffix(".summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n=== summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"results={output_path} summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
