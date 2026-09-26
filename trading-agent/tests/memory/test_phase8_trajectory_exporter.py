# ==============================================================================
# File: tests/memory/test_phase8_trajectory_exporter.py
# ==============================================================================

"""
Unit tests for Phase 8: Trajectory Fine-Tuning & ShareGPT Normalization.
Tests scratchpad-to-think conversion, ShareGPT and OpenAI formats, cross-platform file locking,
head/tail turn preservation, and middle tool truncation budgeting.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from analysis.memory.sharegpt_exporter import (
    ShareGptExporter,
    convert_scratchpad_to_think,
)
from analysis.memory.trajectory_compressor import (
    TrajectoryCompressor,
    TrajectoryCompressionConfig,
    estimate_tokens,
    truncate_middle_text,
)


def test_scratchpad_to_think_conversion():
    """Verify reasoning scratchpad tags are converted to standard think tags."""
    raw = "Let's check MT5.<REASONING_SCRATCHPAD>Checking EURUSD spread.</REASONING_SCRATCHPAD>Spread is 0.8 pips."
    converted = convert_scratchpad_to_think(raw)
    assert "<think>Checking EURUSD spread.</think>" in converted
    assert "<REASONING_SCRATCHPAD>" not in converted

    raw_alt = "<scratchpad>DeepSeek R1 reasoning</scratchpad>Final answer"
    converted_alt = convert_scratchpad_to_think(raw_alt)
    assert "<think>DeepSeek R1 reasoning</think>" in converted_alt


def test_sharegpt_format_conversion():
    """Verify conversion to ShareGPT format."""
    messages = [
        {"role": "system", "content": "You are Monika AI Trading Agent."},
        {"role": "user", "content": "What is current Gold trend?"},
        {
            "role": "assistant",
            "content": "Let me query MT5 indicators.",
            "tool_calls": [{"function": {"name": "mt5_get_price", "arguments": '{"symbol": "XAUUSD"}'}}],
        },
        {"role": "tool", "content": '{"price": 2650.50, "spread": 1.2}'},
        {"role": "assistant", "content": "Gold is bullish at 2650.50."},
    ]

    sharegpt_convs = ShareGptExporter.to_sharegpt_format(messages)
    assert len(sharegpt_convs) == 5

    assert sharegpt_convs[0]["from"] == "system"
    assert sharegpt_convs[0]["value"] == "You are Monika AI Trading Agent."

    assert sharegpt_convs[1]["from"] == "human"
    assert sharegpt_convs[1]["value"] == "What is current Gold trend?"

    assert sharegpt_convs[2]["from"] == "gpt"
    assert "<tool_call>mt5_get_price" in sharegpt_convs[2]["value"]

    assert sharegpt_convs[3]["from"] == "gpt"
    assert "<tool_response>" in sharegpt_convs[3]["value"]

    assert sharegpt_convs[4]["from"] == "gpt"
    assert "Gold is bullish" in sharegpt_convs[4]["value"]


def test_openai_format_conversion():
    """Verify conversion to OpenAI fine-tuning format."""
    messages = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "User question."},
        {"role": "assistant", "content": "<scratchpad>Reasoning</scratchpad>Answer."},
    ]

    openai_msgs = ShareGptExporter.to_openai_format(messages)
    assert len(openai_msgs) == 3
    assert openai_msgs[0]["role"] == "system"
    assert openai_msgs[1]["role"] == "user"
    assert openai_msgs[2]["role"] == "assistant"
    assert "<think>Reasoning</think>" in openai_msgs[2]["content"]


def test_save_trajectory_atomic_file_locking():
    """Verify atomic write with lock and proper metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "trajectories.jsonl"
        messages = [
            {"role": "user", "content": "Test prompt"},
            {"role": "assistant", "content": "Test answer"},
        ]

        # Save success trajectory
        res = ShareGptExporter.save_trajectory(
            messages,
            model="claude-sonnet-5",
            completed=True,
            output_file=out_file,
            schema="sharegpt",
            metadata={"strategy": "BreakoutAlpha", "pnl": 125.50},
        )

        assert res is not None
        assert out_file.exists()

        with open(out_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        entry = lines[0]
        assert entry["model"] == "claude-sonnet-5"
        assert entry["completed"] is True
        assert entry["metadata"]["strategy"] == "BreakoutAlpha"
        assert len(entry["conversations"]) == 2


def test_trajectory_compressor_preserves_head_tail_truncates_middle():
    """Verify that head (system, human, assistant) and last N turns stay intact while middle tool dumps truncate."""
    huge_tool_data = "TICK_DATA_" * 1500  # ~15,000 characters
    messages = [
        {"role": "system", "content": "System Directive Alpha"},
        {"role": "user", "content": "Execute backtest"},
        {"role": "assistant", "content": "Starting backtest query"},
        {"role": "tool", "content": huge_tool_data},  # Unprotected middle turn
        {"role": "assistant", "content": "Evaluating intermediate results..."},  # Unprotected middle turn
        {"role": "tool", "content": huge_tool_data},  # Unprotected middle turn
        {"role": "user", "content": "Confirm trade execution"},  # Protected tail turn
        {"role": "assistant", "content": "Order dispatched: BUY 1.00 lot"},  # Protected tail turn
        {"role": "tool", "content": "EXECUTION_CONFIRMED_TICKET_998811"},  # Protected tail turn
    ]

    cfg = TrajectoryCompressionConfig(
        target_max_tokens=2000,
        protect_first_system=True,
        protect_first_user=True,
        protect_first_assistant=True,
        protect_last_n_turns=3,
        tool_output_max_chars=600,
    )
    compressor = TrajectoryCompressor(cfg)
    compressed = compressor.compress(messages)

    assert len(compressed) == 9

    # Head turns intact
    assert compressed[0]["content"] == "System Directive Alpha"
    assert compressed[1]["content"] == "Execute backtest"
    assert compressed[2]["content"] == "Starting backtest query"

    # Middle tool turns truncated
    assert len(compressed[3]["content"]) < len(huge_tool_data)
    assert "[... " in compressed[3]["content"]
    assert "characters omitted ...]" in compressed[3]["content"]

    assert len(compressed[5]["content"]) < len(huge_tool_data)
    assert "[... " in compressed[5]["content"]

    # Tail turns intact
    assert compressed[6]["content"] == "Confirm trade execution"
    assert compressed[7]["content"] == "Order dispatched: BUY 1.00 lot"
    assert compressed[8]["content"] == "EXECUTION_CONFIRMED_TICKET_998811"


def test_trajectory_compressor_file_batch():
    """Verify JSONL batch processing with compressor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_file = Path(tmpdir) / "raw.jsonl"
        out_file = Path(tmpdir) / "compressed.jsonl"

        record1 = {
            "model": "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": "Sys"},
                {"role": "user", "content": "Hi"},
                {"role": "tool", "content": "LONG_" * 500},
                {"role": "assistant", "content": "Done"},
            ],
        }

        with open(in_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(record1) + "\n")

        compressor = TrajectoryCompressor(TrajectoryCompressionConfig(tool_output_max_chars=100))
        stats = compressor.compress_jsonl_file(in_file, out_file)

        assert stats["processed"] == 1
        assert stats["written"] == 1
        assert out_file.exists()

        with open(out_file, "r", encoding="utf-8") as f:
            res_rec = json.loads(f.readline())
        assert "[... " in res_rec["messages"][2]["content"]
