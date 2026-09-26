# ==============================================================================
# File: tests/agent/test_phase7_moa_loop.py
# ==============================================================================

"""
Unit tests for Phase 7: Mixture of Agents (MoA) Runtime & Modern Reasoning Orchestrator.
Tests cutting-edge models (Claude Sonnet 5, DeepSeek V4 Pro/V4.1 Flash, Gemini 3.8 Flash, GPT-6 Astra),
parallel fan-out, degradation handling, role alternation, and JSONL trace persistence.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from agent.moa_alternation import (
    destination_key,
    merge_same_role_messages,
    is_role_alternation_rejection,
)
from agent.moa_trace import (
    save_moa_turn,
    get_trace_history,
    slot_metrics,
)
from agent.moa_loop import (
    MoARuntime,
    MOA_PRESETS,
    MoAResult,
)


def test_moa_alternation_merging():
    """Verify consecutive same-role messages are merged without losing data."""
    raw_msgs = [
        {"role": "user", "content": "Analyze EURUSD trend."},
        {"role": "user", "content": "Also consider macro Fed rate expectations."},
        {"role": "assistant", "content": "EURUSD is testing key resistance at 1.0950."},
        {"role": "assistant", "content": "Hawkish Fed sentiment may cause a rejection."},
        {"role": "user", "content": "What is the stop loss?"},
    ]

    merged = merge_same_role_messages(raw_msgs)
    assert len(merged) == 3
    assert merged[0]["role"] == "user"
    assert "Analyze EURUSD trend." in merged[0]["content"]
    assert "Also consider macro Fed rate expectations." in merged[0]["content"]

    assert merged[1]["role"] == "assistant"
    assert "testing key resistance" in merged[1]["content"]
    assert "Hawkish Fed sentiment" in merged[1]["content"]

    assert merged[2]["role"] == "user"
    assert merged[2]["content"] == "What is the stop loss?"


def test_role_alternation_rejection_detection():
    """Verify alternation error recognition."""
    exc1 = ValueError("Invalid request: roles must alternate between user and assistant")
    exc2 = RuntimeError("400 Bad Request: Two consecutive user messages detected")
    exc3 = ConnectionError("Socket timeout")

    assert is_role_alternation_rejection(exc1) is True
    assert is_role_alternation_rejection(exc2) is True
    assert is_role_alternation_rejection(exc3) is False


def test_moa_trace_persistence():
    """Verify trace saving and reading."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sid = "session_test_001"
        proposer_traces = [
            slot_metrics({"model": "deepseek-v4-pro", "provider": "deepseek"}, label="DeepSeek-V4-Pro", output="Quant edge: Long", latency_ms=120.0, cost_usd=0.0004),
            slot_metrics({"model": "gemini-3.8-flash", "provider": "google"}, label="Gemini-3.8-Flash", output="Macro context: Neutral", latency_ms=85.0, cost_usd=0.0001),
        ]
        aggregator_trace = slot_metrics(
            {"model": "claude-sonnet-5", "provider": "anthropic"},
            label="Claude-Sonnet-5",
            output="Consensus: Execute selective scale-in",
            latency_ms=210.0,
            cost_usd=0.0012,
        )

        trace_file = save_moa_turn(
            session_id=sid,
            preset_name="trading_quant_moa",
            proposer_traces=proposer_traces,
            aggregator_trace=aggregator_trace,
            user_prompt="Analyze Gold H4 breakout",
            total_latency_ms=330.0,
            trace_dir=tmpdir,
        )

        assert trace_file is not None
        assert os.path.exists(trace_file)

        history = get_trace_history(sid, trace_dir=tmpdir)
        assert len(history) == 1
        rec = history[0]
        assert rec["session_id"] == sid
        assert rec["preset_name"] == "trading_quant_moa"
        assert len(rec["proposers"]) == 2
        assert rec["aggregator"]["label"] == "Claude-Sonnet-5"
        assert rec["total_cost_usd"] > 0


def test_moa_loop_full_consensus():
    """Verify parallel proposer execution and synthesis by aggregator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        def mock_llm(slot, messages):
            model = slot.get("model", "")
            if "deepseek-v4-pro" in model:
                return "DeepSeek V4 Pro: High statistical edge for Long; variance ratio 1.45."
            elif "deepseek-v4.1-flash" in model:
                return "DeepSeek V4.1 Flash: Scenario stress test passed with 8.2% max tail risk."
            elif "gemini-3.8-flash" in model:
                return "Gemini 3.8 Flash: Macro news tailwind positive for commodities."
            elif "gpt-6-astra" in model:
                return "GPT-6 Astra: Liquidity sweep below 2640 absorbed by institutional buyers."
            elif "claude-sonnet-5" in model:
                return "Claude Sonnet 5: Unanimous consensus synthesized. Enter Long at 2645 with SL 2638."
            return f"Generic response from {model}"

        runtime = MoARuntime(
            llm_caller=mock_llm,
            default_preset="trading_quant_moa",
            trace_dir=tmpdir,
        )

        result: MoAResult = runtime.run_moa(
            user_prompt="Evaluate Gold XAUUSD H4 potential breakout.",
            session_id="moa_test_session_1",
        )

        assert result is not None
        assert "Claude Sonnet 5" in result.synthesis
        assert "Unanimous consensus" in result.synthesis
        assert result.aggregator_label == "Claude-Sonnet-5"
        assert len(result.proposer_metrics) == 4
        assert result.is_degraded is False
        assert result.total_latency_ms >= 0


def test_moa_loop_graceful_degradation_one_failed():
    """Verify that if one proposer crashes, the council proceeds smoothly in degraded mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        def mock_llm_with_failure(slot, messages):
            model = slot.get("model", "")
            if "deepseek-v4.1-flash" in model:
                raise TimeoutError("Model gateway timed out after 30s")
            elif "claude-sonnet-5" in model:
                return "Claude Sonnet 5: Synthesized from remaining active advisors."
            return f"Healthy insight from {model}"

        runtime = MoARuntime(
            llm_caller=mock_llm_with_failure,
            default_preset="trading_quant_moa",
            trace_dir=tmpdir,
        )

        result = runtime.run_moa(
            user_prompt="Evaluate Nasdaq futures trend.",
            session_id="degraded_test_session",
        )

        assert result is not None
        assert result.is_degraded is True
        assert "Claude Sonnet 5" in result.synthesis

        # Find the failed proposer metric
        failed_proposers = [p for p in result.proposer_metrics if p.get("is_failed")]
        assert len(failed_proposers) == 1
        assert "deepseek-v4.1-flash" in failed_proposers[0]["model"]
        assert "timed out" in failed_proposers[0]["output"]


def test_moa_loop_all_proposers_failed():
    """Verify that if all proposers fail, aggregator runs in standalone mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        def mock_all_fail(slot, messages):
            model = slot.get("model", "")
            if "claude-sonnet-5" in model:
                return "Claude Sonnet 5: Standalone assessment delivered successfully."
            raise ConnectionResetError("Remote server disconnected")

        runtime = MoARuntime(
            llm_caller=mock_all_fail,
            default_preset="trading_quant_moa",
            trace_dir=tmpdir,
        )

        result = runtime.run_moa(
            user_prompt="Evaluate BTCUSD liquidation cascade.",
            session_id="all_failed_test_session",
        )

        assert result is not None
        assert result.is_degraded is True
        assert "Claude Sonnet 5: Standalone assessment" in result.synthesis


@pytest.mark.asyncio
async def test_moa_async_execution():
    """Verify asynchronous MoA execution wrapper."""
    with tempfile.TemporaryDirectory() as tmpdir:
        def mock_llm(slot, messages):
            return f"Async response from {slot.get('label')}"

        runtime = MoARuntime(
            llm_caller=mock_llm,
            default_preset="fast_scalp_moa",
            trace_dir=tmpdir,
        )

        result = await runtime.run_moa_async(
            user_prompt="Quick scalp check on GBPUSD.",
            session_id="async_session",
        )

        assert result is not None
        assert result.preset_name == "fast_scalp_moa"
        assert result.aggregator_label == "GPT-6-Astra"
        assert len(result.proposer_metrics) == 2
