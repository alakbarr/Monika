# ==============================================================================
# File: tests/agent/test_phase3_multiagent_and_delegation.py
# ==============================================================================

import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from utils.worktree import SubagentWorktree
from logging_observability.delegation_live_log import LiveTranscriptWriter
from analysis.tools.domain.delegate_tool import handle_delegate_task, DelegateTaskInput
from agent.moa_loop import (
    MoARuntime,
    MoAChatCompletions,
    trim_head_tail_context,
)
from analysis.debate.discussion_engine import DiscussionCouncil, DiscussionOutcome


def test_subagent_worktree_lifecycle(tmp_path: Path):
    """Test SubagentWorktree creation, diff inspection, and cleanup."""
    with SubagentWorktree(subagent_id="test_sub_1", base_dir=tmp_path, use_git=False) as wt_path:
        assert wt_path.exists()
        # Create a file inside worktree
        test_file = wt_path / "hello.py"
        test_file.write_text("print('hello subagent')", encoding="utf-8")
        assert test_file.exists()

    # After exit with auto_cleanup, directory should be removed
    assert not wt_path.exists()


def test_live_transcript_writer(tmp_path: Path):
    """Test LiveTranscriptWriter live emission and reading recent events."""
    with LiveTranscriptWriter(subagent_id="test_sub_log", log_dir=tmp_path) as writer:
        writer.emit_event("start", "Subagent starting task")
        writer.emit_event("thought", "Analyzing technical indicators")
        writer.emit_event("finish", "Task completed", {"status": "ok"})

        events = writer.get_recent_events(limit=10)
        assert len(events) == 3
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "thought"
        assert events[2]["type"] == "finish"
        assert events[2]["metadata"]["status"] == "ok"


@pytest.mark.asyncio
async def test_delegate_tool_execution(tmp_path: Path):
    """Test the first-class delegate_task LLM tool."""
    params = DelegateTaskInput(
        task="Audit EURUSD trendline breakout on 1H timeframe",
        role="quant_analyst",
        context="RSI is 64, MACD bullish crossover",
        isolated_worktree=False,
    )
    result = await handle_delegate_task(params)
    assert "[SUBAGENT EXECUTION COMPLETE]" in result
    assert "Role: quant_analyst" in result
    assert "Status: Success" in result


def test_moa_context_trimming():
    """Verify trim_head_tail_context truncates long tool outputs and limits message depth."""
    long_tool_output = "X" * 2000
    messages = [
        {"role": "system", "content": "You are Monika"},
        {"role": "user", "content": "Fetch market data"},
        {"role": "tool", "content": long_tool_output},
        {"role": "assistant", "content": "Received data"},
    ]

    pruned = trim_head_tail_context(messages, max_tool_chars=200, max_total_messages=10)
    assert len(pruned) == 4
    tool_msg = pruned[2]
    assert len(tool_msg["content"]) < 300
    assert "... [truncated" in tool_msg["content"]


def test_moa_chat_completions_facade():
    """Verify MoAChatCompletions produces OpenAI-compatible responses."""
    def mock_llm_caller(slot, msgs):
        label = slot.get("label", "Mock")
        return f"Response from {label}"

    runtime = MoARuntime(llm_caller=mock_llm_caller, default_preset="fast_scalp_moa")
    facade = MoAChatCompletions(runtime=runtime)

    messages = [
        {"role": "system", "content": "You are Monika"},
        {"role": "user", "content": "What is the scalping signal for BTC?"},
    ]

    res = facade.create(messages)
    assert "choices" in res
    assert len(res["choices"]) == 1
    assert "message" in res["choices"][0]
    assert "Response from" in res["choices"][0]["message"]["content"]
    assert "usage" in res


def test_discussion_council_pass_protocol():
    """Verify DiscussionCouncil delta watermarks, (pass) protocol, and early consensus."""
    participants = [
        {"name": "BullAnalyst", "role_prompt": "You focus on bullish arguments."},
        {"name": "BearAnalyst", "role_prompt": "You focus on bearish arguments."},
        {"name": "RiskManager", "role_prompt": "You evaluate overall portfolio risk."},
    ]

    turn_counter = 0

    def mock_council_llm(slot, msgs):
        nonlocal turn_counter
        turn_counter += 1
        name = slot.get("name")
        if name == "CouncilArbiter":
            return "CouncilArbiter: Consensus reached to buy breakout above 2050 with tight stop_loss."
        # In round 1, participants speak; in round 2, all pass
        if turn_counter <= 3:
            return f"{name}: I see potential breakout."
        else:
            return "(pass)"

    council = DiscussionCouncil(
        participants=participants,
        llm_caller=mock_council_llm,
        max_rounds=3,
        allow_early_consensus=True,
    )

    outcome: DiscussionOutcome = council.run_discussion(
        topic="Evaluate breakout trade on XAUUSD",
        initial_context="Gold tested 2050 resistance 3 times.",
    )

    assert outcome.rounds_executed == 2
    assert outcome.unanimous_consensus is True
    assert len(outcome.transcript) > 0
    assert outcome.trade_signal_detected is True
