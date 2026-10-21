"""Point-in-time LLM replay for historical per-asset analyses.

Historical analyses were produced by Gemini 3.x with tool calling. The stored
``context_messages`` contain the user/assistant/tool transcript, but not the
Gemini ``thought_signature`` values. Gemini 3.x rejects replaying those stored
function-call parts directly, so exact API-level replay of the old transcript is
not possible.

This module implements the primary replay method: a *decision-turn* replay.
The stored transcript up to (but not including) the final
``submit_asset_analysis`` call is serialised as text. That gives the model the
same point-in-time observations without any historical function-call parts, so
Gemini accepts the request. The model must then produce the final
``submit_asset_analysis`` call, which is compared with the stored final submit.

The module is provider-agnostic: ``run_decision_replay`` accepts any object with
``async run_tool_agent(messages=..., tools=..., system_prompt=...)``. It never
performs live tool lookups. If the model asks for another tool, it receives a
deterministic "replay unavailable" tool result and is asked to submit the
decision. This keeps the replay zero-lookahead.

The optional ``audit_sl_geometry`` function applies the deterministic SL
floor/ceiling rule used by the historical submission validator. It is a
post-hoc verification layer, not a replacement for the production RiskGate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import statistics
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]

DECISION_INSTRUCTION = (
    "=== REPLAY FINAL DECISION TURN ===\n"
    "You are now at the exact final decision turn of the historical analysis. "
    "Every observation above is verbatim from the historical run and is point-in-time; "
    "no future data is available. Do not call any tool other than submit_asset_analysis. "
    "Call submit_asset_analysis now with your final decision and the full structured fields, "
    "using only the information above. If a previous submission above was rejected by "
    "validation, correct the rejected fields in your new submission."
)

REPLAY_UNAVAILABLE = (
    "The full historical observations are already in the transcript. "
    "Do not call additional tools; call submit_asset_analysis now."
)

TEXT_ONLY_NUDGE = (
    "Your previous response did not call submit_asset_analysis. "
    "You must call submit_asset_analysis now with the final structured decision. "
    "Do not return a text-only answer."
)


class ToolAgentProvider(Protocol):
    """Minimal provider interface required by the replay runner."""

    async def run_tool_agent(
        self,
        *,
        messages: list[JsonDict],
        tools: list[JsonDict],
        system_prompt: str,
    ) -> Any: ...


def _content_blocks(message: Mapping[str, Any]) -> list[JsonDict]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def tool_uses(message: Mapping[str, Any]) -> list[JsonDict]:
    """Return ``tool_use`` blocks from a message."""
    return [block for block in _content_blocks(message) if block.get("type") == "tool_use"]


def find_submit_indices(messages: Sequence[Mapping[str, Any]]) -> list[int]:
    """Return indexes of assistant messages that call ``submit_asset_analysis``."""
    indices: list[int] = []
    for index, message in enumerate(messages):
        if any(block.get("name") == "submit_asset_analysis" for block in tool_uses(message)):
            indices.append(index)
    return indices


def last_submit_index(messages: Sequence[Mapping[str, Any]]) -> int | None:
    indices = find_submit_indices(messages)
    return indices[-1] if indices else None


def last_submit_input(messages: Sequence[Mapping[str, Any]]) -> JsonDict | None:
    """Return the input of the last historical ``submit_asset_analysis`` call."""
    index = last_submit_index(messages)
    if index is None:
        return None
    for block in tool_uses(messages[index]):
        if block.get("name") != "submit_asset_analysis":
            continue
        value = block.get("input")
        if isinstance(value, dict):
            return value
    return None


def truncate_before_last_submit(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], int | None]:
    """Return the transcript before the final submit, plus that submit's index."""
    index = last_submit_index(messages)
    if index is None:
        return list(messages), None
    return list(messages[:index]), index


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def serialize_transcript(messages: Sequence[Mapping[str, Any]]) -> str:
    """Serialise stored provider messages into a deterministic text transcript.

    The first user message is emitted verbatim (it contains the reconstructed
    dynamic overlay). Later text, tool calls, and tool results are labelled so
    the replay model can distinguish observations from its own output.
    """
    id_to_name: dict[str, str] = {}
    for message in messages:
        for block in tool_uses(message):
            use_id = block.get("id")
            name = block.get("name")
            if isinstance(use_id, str) and isinstance(name, str):
                id_to_name[use_id] = name

    parts: list[str] = []
    for index, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content if index == 0 else f"\n[User]\n{content}")
            continue
        for block in _content_blocks(message):
            block_type = block.get("type")
            if block_type == "text":
                speaker = "Assistant" if role == "assistant" else "User"
                parts.append(f"\n[{speaker}]\n{block.get('text') or ''}")
            elif block_type == "tool_use":
                parts.append(
                    f"\n[Assistant tool call] {block.get('name')}\n"
                    f"{json.dumps(block.get('input') or {}, ensure_ascii=False, indent=2, default=str)}"
                )
            elif block_type == "tool_result":
                use_id = block.get("tool_use_id")
                name = id_to_name.get(use_id, "unknown_tool") if isinstance(use_id, str) else "unknown_tool"
                parts.append(f"\n[Tool result: {name}]\n{_json_text(block.get('content'))}")
    return "\n".join(parts).strip()


def build_decision_prompt(record: Mapping[str, Any]) -> tuple[str, int]:
    """Build the decision-turn replay prompt and return the final submit index.

    The final historical submit is deliberately excluded: it is the answer the
    replay must reproduce, and including it would leak the expected decision.
    """
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("record['messages'] must be a list")
    context, index = truncate_before_last_submit(messages)
    if index is None:
        raise ValueError("record has no submit_asset_analysis turn")
    transcript = serialize_transcript(context)
    return f"{transcript}\n\n{DECISION_INSTRUCTION}", index


def response_blocks(response: Any) -> list[JsonDict]:
    """Extract Anthropic-style content blocks from a provider response."""
    content = getattr(response, "content", None)
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, dict):
        inner = content.get("content")
        if isinstance(inner, list):
            return [block for block in inner if isinstance(block, dict)]
        if content.get("type"):
            return [content]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def response_tool_uses(blocks: Sequence[Mapping[str, Any]]) -> list[JsonDict]:
    return [dict(block) for block in blocks if block.get("type") == "tool_use"]


def response_text(blocks: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text").strip()


def _int_attr(response: Any, name: str) -> int:
    value = getattr(response, name, 0)
    try:
        return int(value or 0)
    except TypeError, ValueError:
        return 0


def extract_usage(response: Any) -> JsonDict:
    return {
        "input_tokens": _int_attr(response, "input_tokens"),
        "output_tokens": _int_attr(response, "output_tokens"),
        "thinking_tokens": _int_attr(response, "thinking_tokens"),
        "cached_tokens": _int_attr(response, "cached_tokens"),
    }


def _merge_usage(total: JsonDict, usage: Mapping[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "thinking_tokens", "cached_tokens"):
        total[key] = int(total.get(key, 0)) + int(usage.get(key, 0) or 0)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except TypeError, ValueError:
        return None
    return result if math.isfinite(result) else None


def _entry_price(entry: Any) -> float | None:
    if not isinstance(entry, dict):
        return None
    value = entry.get("price")
    if value is None:
        value = entry.get("market_price")
    return _safe_float(value)


def _entry_type(entry: Any) -> Any:
    return entry.get("type") if isinstance(entry, dict) else None


def _pct_diff(original: Any, replay: Any) -> float | None:
    first = _safe_float(original)
    second = _safe_float(replay)
    if first is None or second is None:
        return None
    if first == 0:
        return 0.0 if second == 0 else None
    return round(abs(second - first) / abs(first) * 100.0, 4)


def compare_submissions(
    original: Mapping[str, Any] | None,
    replay: Mapping[str, Any] | None,
) -> JsonDict:
    """Compare the stored final submit with the replay submit."""
    first: JsonDict = dict(original or {})
    second: JsonDict = dict(replay or {})
    first_entry = first.get("entry_condition")
    second_entry = second.get("entry_condition")

    comparison: JsonDict = {
        "decision_match": first.get("decision") == second.get("decision"),
        "original_decision": first.get("decision"),
        "replay_decision": second.get("decision"),
        "symbol_match": first.get("symbol") == second.get("symbol"),
        "confidence_delta": None,
        "confluence_score_delta": None,
        "priced_in_delta": None,
        "stop_loss_pct_diff": _pct_diff(first.get("stop_loss"), second.get("stop_loss")),
        "take_profit_pct_diff": _pct_diff(first.get("take_profit"), second.get("take_profit")),
        "entry_pct_diff": _pct_diff(_entry_price(first_entry), _entry_price(second_entry)),
        "entry_type_match": _entry_type(first_entry) == _entry_type(second_entry),
    }

    first_confidence = _safe_float(first.get("confidence"))
    second_confidence = _safe_float(second.get("confidence"))
    if first_confidence is not None and second_confidence is not None:
        comparison["confidence_delta"] = round(abs(second_confidence - first_confidence), 4)

    first_confluence = _safe_float(first.get("confluence_score"))
    second_confluence = _safe_float(second.get("confluence_score"))
    if first_confluence is not None and second_confluence is not None:
        comparison["confluence_score_delta"] = round(abs(second_confluence - first_confluence), 2)

    first_priced_in = _safe_float(first.get("priced_in_score"))
    second_priced_in = _safe_float(second.get("priced_in_score"))
    if first_priced_in is not None and second_priced_in is not None:
        comparison["priced_in_delta"] = round(abs(second_priced_in - first_priced_in), 2)

    return comparison


def audit_sl_geometry(
    *,
    decision: str | None,
    entry_price: Any,
    stop_loss: Any,
    atr_h4: Any,
    adr_ceiling: Any,
    atr_multiplier: Any = 1.0,
) -> JsonDict:
    """Apply the historical SL floor/ADR ceiling rule to a replay proposal.

    This is a deterministic post-hoc audit. Missing, non-finite, zero, or
    negative inputs fail closed and produce an effective ``wait`` decision.
    """
    normalized = (decision or "").lower()
    if normalized not in ("buy", "sell"):
        return {
            "risk_checked": False,
            "risk_blocked": False,
            "effective_decision": normalized or None,
            "reason": "non-directional decision; no SL required",
        }

    entry = _safe_float(entry_price)
    stop = _safe_float(stop_loss)
    atr = _safe_float(atr_h4)
    ceiling = _safe_float(adr_ceiling)
    multiplier = _safe_float(atr_multiplier)
    if (
        entry is None
        or stop is None
        or atr is None
        or ceiling is None
        or multiplier is None
        or entry <= 0
        or stop <= 0
        or atr <= 0
        or ceiling <= 0
        or multiplier <= 0
    ):
        return {
            "risk_checked": True,
            "risk_blocked": True,
            "effective_decision": "wait",
            "reason": "missing or invalid entry/stop/ATR/ADR; fail-closed",
        }

    floor = multiplier * atr
    distance = abs(entry - stop)
    result: JsonDict = {
        "risk_checked": True,
        "risk_blocked": False,
        "effective_decision": normalized,
        "entry_price": entry,
        "stop_loss": stop,
        "sl_distance": round(distance, 6),
        "atr_h4": atr,
        "atr_multiplier": multiplier,
        "atr_floor": round(floor, 6),
        "adr_ceiling": ceiling,
        "floor_above_ceiling": floor > ceiling,
    }
    if floor > ceiling:
        result["risk_blocked"] = True
        result["effective_decision"] = "wait"
        result["reason"] = f"no compliant SL: ATR floor {floor:.6f} > ADR ceiling {ceiling:.6f}"
    elif distance < floor:
        result["risk_blocked"] = True
        result["effective_decision"] = "wait"
        result["reason"] = f"SL distance {distance:.6f} < ATR floor {floor:.6f}"
    elif distance > ceiling:
        result["risk_blocked"] = True
        result["effective_decision"] = "wait"
        result["reason"] = f"SL distance {distance:.6f} > ADR ceiling {ceiling:.6f}"
    else:
        result["reason"] = f"SL distance {distance:.6f} within [{floor:.6f}, {ceiling:.6f}]"
    return result


def _first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return _safe_float(match.group(1).replace(",", ""))


def parse_sl_risk_inputs(context_text: str, symbol: str, rationale: str = "") -> JsonDict:
    """Extract the point-in-time SL rule inputs from the stored prompt.

    The pre-fetched prompt lists four ``ATR_14`` values (D1, H4, H1, M15); the
    second value is the H4 ATR used by the historical intraday SL rule. The
    prompt also states the mandatory 35% ADR SL ceiling. Symbol memory may
    raise the floor (for example XBRUSD requires 1.2x ATR).
    """
    atr_values = [
        value
        for value in (_safe_float(match.group(1)) for match in re.finditer(r"ATR_14:\s*([0-9.]+)", context_text))
        if value is not None
    ]
    atr_h4 = atr_values[1] if len(atr_values) > 1 else None
    adr_ceiling = _first_float(r"MANDATORY SL max distance:\s*([0-9.]+)", context_text)
    multiplier_match = re.search(
        rf"For {re.escape(symbol)}:\s*Enforce minimum Stop Loss distance\s*>=\s*([0-9.]+)x ATR",
        context_text,
        re.IGNORECASE,
    )
    multiplier = _safe_float(multiplier_match.group(1)) if multiplier_match else 1.0
    fallback_entry = _first_float(r"Price\s+([0-9.]+)\s+\(ground truth\)", rationale)
    if fallback_entry is None:
        fallback_entry = _first_float(r"verified close\s+([0-9.]+)", rationale)
    if fallback_entry is None:
        fallback_entry = _first_float(r"\bprice\s+([0-9.]+)", rationale)
    if fallback_entry is None:
        fallback_entry = _first_float(r"Price\s+([0-9.]+)\s+\(ground truth\)", context_text)
    if fallback_entry is None:
        fallback_entry = _first_float(r"Price \(ground truth\):\s*([0-9.]+)", context_text)
    if fallback_entry is None:
        fallback_entry = _first_float(r'"(?:close|price)"\s*:\s*([0-9.]+)', context_text)
    return {
        "atr_h4": atr_h4,
        "adr_ceiling": adr_ceiling,
        "atr_multiplier": multiplier,
        "fallback_entry": fallback_entry,
    }


async def run_decision_replay(
    provider: ToolAgentProvider,
    record: Mapping[str, Any],
    *,
    tools: list[JsonDict],
    system_prompt: str,
    max_turns: int = 3,
    timeout_seconds: float = 240.0,
) -> JsonDict:
    """Replay the final decision turn for one stored analysis.

    Returns the raw replay submit, the stored final submit, per-turn usage, and
    the structured comparison. No live tool calls are made.
    """
    prompt, final_submit_index = build_decision_prompt(record)
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("record['messages'] must be a list")
    original_submit = last_submit_input(messages)

    request_messages: list[JsonDict] = [{"role": "user", "content": prompt}]
    usage_total: JsonDict = {
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cached_tokens": 0,
    }
    turns: list[JsonDict] = []
    replay_submit: JsonDict | None = None
    replay_text = ""
    status = "ok"

    for turn in range(1, max_turns + 1):
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await provider.run_tool_agent(
                    messages=request_messages,
                    tools=tools,
                    system_prompt=system_prompt,
                )
        except TimeoutError:
            status = "provider_timeout"
            break
        except Exception as exc:
            logger.warning(
                "LLM replay provider call failed for analysis %s: %s",
                record.get("analysis_id"),
                type(exc).__name__,
            )
            status = f"provider_error: {type(exc).__name__}: {exc}"
            break
        elapsed = time.monotonic() - started

        blocks = response_blocks(response)
        text = response_text(blocks)
        calls = response_tool_uses(blocks)
        usage = extract_usage(response)
        _merge_usage(usage_total, usage)
        turns.append(
            {
                "turn": turn,
                "elapsed_seconds": round(elapsed, 2),
                "text_len": len(text),
                "tool_calls": [{"name": call.get("name"), "input": call.get("input")} for call in calls],
                "usage": usage,
            }
        )

        if not calls:
            if turn < max_turns:
                if blocks:
                    request_messages.append({"role": "assistant", "content": blocks})
                request_messages.append({"role": "user", "content": TEXT_ONLY_NUDGE})
                continue
            status = "no_tool_call"
            replay_text = text
            break

        submit = next((call for call in calls if call.get("name") == "submit_asset_analysis"), None)
        if submit is not None:
            value = submit.get("input")
            replay_submit = dict(value) if isinstance(value, dict) else None
            replay_text = text
            break

        request_messages.append({"role": "assistant", "content": blocks})
        request_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": str(call.get("id") or f"replay_call_{turn}_{position}"),
                        "content": json.dumps({"status": "replay_unavailable", "error": REPLAY_UNAVAILABLE}),
                    }
                    for position, call in enumerate(calls)
                ],
            }
        )
    else:
        status = "max_turns"

    return {
        "analysis_id": record.get("analysis_id"),
        "symbol": record.get("symbol"),
        "generated_at": record.get("generated_at"),
        "db_decision": record.get("decision"),
        "final_text": str(record.get("final_text") or "")[:300],
        "last_submit_index": final_submit_index,
        "original_submit": original_submit,
        "replay_submit": replay_submit,
        "replay_text": replay_text,
        "status": status,
        "turns": turns,
        "usage_total": usage_total,
        "comparison": compare_submissions(original_submit, replay_submit),
    }


def summarize_results(results: Sequence[Mapping[str, Any]]) -> JsonDict:
    """Aggregate raw and risk-gated replay parity, deltas, and token usage."""
    comparisons: list[JsonDict] = []
    for result in results:
        comparison = result.get("comparison")
        comparisons.append(dict(comparison) if isinstance(comparison, dict) else {})

    matches = [result for result, comparison in zip(results, comparisons) if comparison.get("decision_match")]
    mismatches = [
        {
            "analysis_id": result.get("analysis_id"),
            "symbol": result.get("symbol"),
            "original": comparison.get("original_decision"),
            "replay": comparison.get("replay_decision"),
        }
        for result, comparison in zip(results, comparisons)
        if not comparison.get("decision_match")
    ]
    directional = [
        comparison
        for comparison in comparisons
        if comparison.get("original_decision") in ("buy", "sell") and comparison.get("decision_match")
    ]

    metrics: JsonDict = {}
    for key in (
        "confidence_delta",
        "confluence_score_delta",
        "priced_in_delta",
        "stop_loss_pct_diff",
        "take_profit_pct_diff",
        "entry_pct_diff",
    ):
        values = [float(comparison[key]) for comparison in directional if comparison.get(key) is not None]
        if values:
            metrics[key] = {
                "n": len(values),
                "mean": round(statistics.mean(values), 4),
                "median": round(statistics.median(values), 4),
                "max": round(max(values), 4),
            }

    tokens = {
        key: sum(int((result.get("usage_total") or {}).get(key, 0) or 0) for result in results)
        for key in ("input_tokens", "output_tokens", "thinking_tokens", "cached_tokens")
    }
    turns = [turn for result in results for turn in (result.get("turns") or []) if isinstance(turn, dict)]
    effective = [result for result in results if result.get("effective_match") is True]
    risk_blocked = [result for result in results if (result.get("risk_audit") or {}).get("risk_blocked") is True]

    return {
        "total": len(results),
        "raw_matches": len(matches),
        "raw_parity_pct": round(len(matches) / len(results) * 100.0, 1) if results else 0.0,
        "mismatches": mismatches,
        "directional_matches": len(directional),
        "directional_metrics": metrics,
        "entry_type_matches": sum(1 for comparison in directional if comparison.get("entry_type_match") is True),
        "tokens": tokens,
        "turns": len(turns),
        "max_turn_seconds": max((float(turn.get("elapsed_seconds") or 0) for turn in turns), default=0.0),
        "statuses": sorted({str(result.get("status")) for result in results}),
        "risk_blocked": len(risk_blocked),
        "effective_matches": len(effective) if any("effective_match" in result for result in results) else None,
    }
