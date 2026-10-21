"""Unit tests for the point-in-time LLM replay helpers and runner."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from monika.application.evals.llm_replay import (
    TEXT_ONLY_NUDGE,
    audit_sl_geometry,
    build_decision_prompt,
    compare_submissions,
    parse_sl_risk_inputs,
    run_decision_replay,
    serialize_transcript,
    summarize_results,
    truncate_before_last_submit,
)

pytestmark = pytest.mark.unit


def _record() -> dict:
    return {
        "analysis_id": 1,
        "symbol": "EURUSD",
        "generated_at": "2026-10-16T10:40:38+00:00",
        "decision": "sell",
        "final_text": "",
        "messages": [
            {"role": "user", "content": "Analyze EURUSD and provide a structured trading decision."},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_news",
                        "name": "get_news_items",
                        "input": {"currency_filter": "USD"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_news",
                        "content": '{"news": []}',
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "submit_first",
                        "name": "submit_asset_analysis",
                        "input": {
                            "symbol": "EURUSD",
                            "decision": "sell",
                            "confidence": 0.6,
                            "stop_loss": 1.11,
                            "take_profit": 1.08,
                            "rationale": "first submission",
                        },
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "submit_first",
                        "content": '{"status": "validation_failed", "errors": ["bad factor"]}',
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "submit_final",
                        "name": "submit_asset_analysis",
                        "input": {
                            "symbol": "EURUSD",
                            "decision": "sell",
                            "confidence": 0.6,
                            "stop_loss": 1.11,
                            "take_profit": 1.08,
                            "rationale": "FINAL_UNIQUE_RATIONALE",
                        },
                    }
                ],
            },
        ],
    }


class FakeProvider:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def run_tool_agent(self, *, messages: list, tools: list, system_prompt: str) -> SimpleNamespace:
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )
        return self._responses.pop(0)


def _response(
    content: list[dict], input_tokens: int = 0, output_tokens: int = 0, thinking_tokens: int = 0, cached_tokens: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cached_tokens=cached_tokens,
    )


def test_build_decision_prompt_excludes_final_submit() -> None:
    record = _record()
    prompt, index = build_decision_prompt(record)

    assert index == len(record["messages"]) - 1
    assert "FINAL_UNIQUE_RATIONALE" not in prompt
    assert "validation_failed" in prompt
    assert "get_news_items" in prompt
    assert "REPLAY FINAL DECISION TURN" in prompt


def test_serialize_transcript_labels_tools_and_results() -> None:
    record = _record()
    context, index = truncate_before_last_submit(record["messages"])
    transcript = serialize_transcript(context)

    assert index == len(record["messages"]) - 1
    assert "[Assistant tool call] get_news_items" in transcript
    assert "[Tool result: get_news_items]" in transcript
    assert "validation_failed" in transcript


def test_build_decision_prompt_requires_submit() -> None:
    with pytest.raises(ValueError, match="submit_asset_analysis"):
        build_decision_prompt({"messages": [{"role": "user", "content": "no submit"}]})


def test_compare_submissions_exact_and_different() -> None:
    original = {
        "symbol": "EURUSD",
        "decision": "sell",
        "confidence": 0.6,
        "stop_loss": 1.11,
        "take_profit": 1.08,
        "entry_condition": {"type": "market", "price": 1.1},
        "confluence_score": 7,
        "priced_in_score": 6,
    }
    replay = copy.deepcopy(original)
    comparison = compare_submissions(original, replay)

    assert comparison["decision_match"] is True
    assert comparison["symbol_match"] is True
    assert comparison["confidence_delta"] == 0
    assert comparison["confluence_score_delta"] == 0
    assert comparison["priced_in_delta"] == 0
    assert comparison["stop_loss_pct_diff"] == 0
    assert comparison["take_profit_pct_diff"] == 0
    assert comparison["entry_pct_diff"] == 0
    assert comparison["entry_type_match"] is True

    changed = dict(replay)
    changed["decision"] = "buy"
    changed["confidence"] = 0.5
    changed["stop_loss"] = 1.12
    changed_comparison = compare_submissions(original, changed)
    assert changed_comparison["decision_match"] is False
    assert changed_comparison["confidence_delta"] == pytest.approx(0.1)
    assert changed_comparison["stop_loss_pct_diff"] == pytest.approx(0.9009, abs=1e-3)


def test_audit_sl_geometry_fail_closed_and_valid() -> None:
    valid = audit_sl_geometry(
        decision="buy",
        entry_price=100,
        stop_loss=98,
        atr_h4=2,
        adr_ceiling=5,
        atr_multiplier=1.0,
    )
    assert valid["risk_blocked"] is False
    assert valid["effective_decision"] == "buy"
    assert valid["sl_distance"] == 2

    floor_above_ceiling = audit_sl_geometry(
        decision="buy",
        entry_price=100,
        stop_loss=98,
        atr_h4=2,
        adr_ceiling=1,
        atr_multiplier=1.0,
    )
    assert floor_above_ceiling["risk_blocked"] is True
    assert floor_above_ceiling["effective_decision"] == "wait"
    assert floor_above_ceiling["floor_above_ceiling"] is True

    too_tight = audit_sl_geometry(
        decision="sell",
        entry_price=100,
        stop_loss=99,
        atr_h4=2,
        adr_ceiling=5,
        atr_multiplier=1.0,
    )
    assert too_tight["risk_blocked"] is True
    assert too_tight["effective_decision"] == "wait"

    too_wide = audit_sl_geometry(
        decision="sell",
        entry_price=100,
        stop_loss=94,
        atr_h4=2,
        adr_ceiling=5,
        atr_multiplier=1.0,
    )
    assert too_wide["risk_blocked"] is True
    assert too_wide["effective_decision"] == "wait"

    missing = audit_sl_geometry(
        decision="buy",
        entry_price=None,
        stop_loss=98,
        atr_h4=2,
        adr_ceiling=5,
    )
    assert missing["risk_blocked"] is True
    assert missing["effective_decision"] == "wait"

    nan = audit_sl_geometry(
        decision="buy",
        entry_price=float("nan"),
        stop_loss=98,
        atr_h4=2,
        adr_ceiling=5,
    )
    assert nan["risk_blocked"] is True
    assert nan["effective_decision"] == "wait"

    non_directional = audit_sl_geometry(
        decision="wait",
        entry_price=100,
        stop_loss=98,
        atr_h4=2,
        adr_ceiling=5,
    )
    assert non_directional["risk_checked"] is False
    assert non_directional["effective_decision"] == "wait"


def test_parse_sl_risk_inputs() -> None:
    text = """
    ATR_14: 3.22753 (prev: 3.40426)
    ATR_14: 1.03475 (prev: 1.05435)
    ATR_14: 0.47397 (prev: 0.47428)
    ATR_14: 0.32885 (prev: 0.34569)
    MANDATORY SL max distance: 0.93714 (35% of ADR)
    - [DO NOT][SL_TOO_TIGHT] For XBRUSD: Enforce minimum Stop Loss distance >= 1.2x ATR from entry.
    Price 103.89 (ground truth)
    """
    parsed = parse_sl_risk_inputs(text, "XBRUSD")

    assert parsed["atr_h4"] == 1.03475
    assert parsed["adr_ceiling"] == 0.93714
    assert parsed["atr_multiplier"] == 1.2
    assert parsed["fallback_entry"] == 103.89


def test_parse_sl_risk_inputs_falls_back_to_rationale_price() -> None:
    parsed = parse_sl_risk_inputs(
        "",
        "XBRUSD",
        "Price is extended; price 103.99 in premium with no unmitigated zone.",
    )

    assert parsed["fallback_entry"] == 103.99


async def test_run_decision_replay_handles_tool_then_submit() -> None:
    first_tool = _response(
        [
            {
                "type": "tool_use",
                "id": "call_size",
                "name": "calculate_position_size",
                "input": {"symbol": "EURUSD"},
            }
        ],
        input_tokens=10,
        output_tokens=2,
        thinking_tokens=1,
    )
    submit = _response(
        [
            {
                "type": "tool_use",
                "id": "submit_replay",
                "name": "submit_asset_analysis",
                "input": {
                    "symbol": "EURUSD",
                    "decision": "sell",
                    "confidence": 0.6,
                    "stop_loss": 1.11,
                    "take_profit": 1.08,
                    "entry_condition": {"type": "market", "price": 1.1},
                },
            }
        ],
        input_tokens=20,
        output_tokens=5,
        thinking_tokens=2,
        cached_tokens=10,
    )
    provider = FakeProvider([first_tool, submit])
    record = _record()

    result = await run_decision_replay(provider, record, tools=[], system_prompt="STATIC")

    assert result["status"] == "ok"
    assert result["comparison"]["decision_match"] is True
    assert len(provider.calls) == 2
    assert result["usage_total"] == {
        "input_tokens": 30,
        "output_tokens": 7,
        "thinking_tokens": 3,
        "cached_tokens": 10,
    }
    assert provider.calls[0]["system_prompt"] == "STATIC"
    assert "FINAL_UNIQUE_RATIONALE" not in provider.calls[0]["messages"][0]["content"]
    assert provider.calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    assert "replay_unavailable" in provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert result["turns"][0]["tool_calls"][0]["name"] == "calculate_position_size"


async def test_run_decision_replay_nudges_text_only_then_submits() -> None:
    text_only = _response([{"type": "text", "text": "I need more data"}], input_tokens=5, output_tokens=1)
    submit = _response(
        [
            {
                "type": "tool_use",
                "id": "submit_after_nudge",
                "name": "submit_asset_analysis",
                "input": {
                    "symbol": "EURUSD",
                    "decision": "sell",
                    "confidence": 0.6,
                    "stop_loss": 1.11,
                    "take_profit": 1.08,
                },
            }
        ],
        input_tokens=8,
        output_tokens=2,
    )
    provider = FakeProvider([text_only, submit])

    result = await run_decision_replay(provider, _record(), tools=[], system_prompt="STATIC")

    assert result["status"] == "ok"
    assert result["comparison"]["decision_match"] is True
    assert len(provider.calls) == 2
    assert provider.calls[1]["messages"][-1]["content"] == TEXT_ONLY_NUDGE
    assert result["turns"][1]["elapsed_seconds"] >= 0


async def test_run_decision_replay_no_tool_call_after_all_nudges() -> None:
    provider = FakeProvider(
        [
            _response([{"type": "text", "text": "I need more data"}], input_tokens=5, output_tokens=1),
            _response([{"type": "text", "text": "Still thinking"}], input_tokens=5, output_tokens=1),
            _response([{"type": "text", "text": "No tool call"}], input_tokens=5, output_tokens=1),
        ]
    )
    result = await run_decision_replay(provider, _record(), tools=[], system_prompt="STATIC", max_turns=3)

    assert result["status"] == "no_tool_call"
    assert result["replay_submit"] is None
    assert result["comparison"]["replay_decision"] is None
    assert len(provider.calls) == 3
    assert provider.calls[1]["messages"][-1]["content"] == TEXT_ONLY_NUDGE


def test_summarize_results_aggregates_raw_and_effective_parity() -> None:
    match = {
        "analysis_id": 1,
        "symbol": "EURUSD",
        "status": "ok",
        "effective_match": True,
        "comparison": {
            "decision_match": True,
            "original_decision": "sell",
            "replay_decision": "sell",
            "confidence_delta": 0,
            "confluence_score_delta": 0,
            "priced_in_delta": 0,
            "stop_loss_pct_diff": 0,
            "take_profit_pct_diff": 0,
            "entry_pct_diff": 0,
            "entry_type_match": True,
        },
        "usage_total": {"input_tokens": 10, "output_tokens": 2, "thinking_tokens": 1, "cached_tokens": 0},
        "turns": [{"elapsed_seconds": 1.0}],
    }
    mismatch = {
        "analysis_id": 2,
        "symbol": "XBRUSD",
        "status": "ok",
        "effective_match": True,
        "risk_audit": {"risk_blocked": True},
        "comparison": {
            "decision_match": False,
            "original_decision": "wait",
            "replay_decision": "buy",
            "confidence_delta": None,
            "confluence_score_delta": None,
            "priced_in_delta": None,
            "stop_loss_pct_diff": None,
            "take_profit_pct_diff": None,
            "entry_pct_diff": None,
            "entry_type_match": False,
        },
        "usage_total": {"input_tokens": 20, "output_tokens": 3, "thinking_tokens": 2, "cached_tokens": 1},
        "turns": [{"elapsed_seconds": 2.0}],
    }

    summary = summarize_results([match, mismatch])

    assert summary["total"] == 2
    assert summary["raw_matches"] == 1
    assert summary["raw_parity_pct"] == 50.0
    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["symbol"] == "XBRUSD"
    assert summary["directional_matches"] == 1
    assert summary["directional_metrics"]["confidence_delta"]["n"] == 1
    assert summary["entry_type_matches"] == 1
    assert summary["tokens"] == {
        "input_tokens": 30,
        "output_tokens": 5,
        "thinking_tokens": 3,
        "cached_tokens": 1,
    }
    assert summary["turns"] == 2
    assert summary["max_turn_seconds"] == 2.0
    assert summary["risk_blocked"] == 1
    assert summary["effective_matches"] == 2
