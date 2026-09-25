# ==============================================================================
# File: tests/graph/test_state_pruner_and_checkpointer.py
# ==============================================================================

import os
import tempfile
import pytest
from graph.nodes.state_pruner import prune_after_fundamental, prune_after_debate, prune_before_execution
from graph.checkpointers.sqlite_checkpointer import SqliteCheckpointSaver


from graph.state import merge_dicts


def test_prune_after_fundamental():
    """Verify pruning sets tombstone and removes heavy raw conversations via merge_dicts."""
    state = {
        "summary": {
            "fundamental": {
                "brief": "US Dollar remains strong due to hawkish Fed tone.",
                "confidence": 0.85,
                "raw_conversation": [{"role": "user", "content": "10000 characters of raw data"}],
                "raw_tool_observations": {"get_price_data": "raw text"},
            }
        }
    }
    pruned = prune_after_fundamental(state)
    fund = pruned["summary"]["fundamental"]
    assert fund["brief"] == "US Dollar remains strong due to hawkish Fed tone."
    assert fund["confidence"] == 0.85
    assert fund["raw_conversation"] == "_DELETED_"
    assert fund["raw_tool_observations"] == "_DELETED_"

    merged = merge_dicts(state["summary"], pruned["summary"])
    merged_fund = merged["fundamental"]
    assert "raw_conversation" not in merged_fund
    assert "raw_tool_observations" not in merged_fund


def test_prune_after_debate():
    """Verify pruning sets tombstone and removes raw dialogue transcripts via merge_dicts."""
    state = {
        "debate_states": {
            "EURUSD": {
                "consensus": "Neutral to Bearish",
                "raw_bull_text": "Massive wall of text from bull analyst...",
                "raw_bear_text": "Massive wall of text from bear analyst...",
                "raw_judge_text": "Judge deliberation transcript...",
            }
        }
    }
    pruned = prune_after_debate(state)
    eur = pruned["debate_states"]["EURUSD"]
    assert eur["consensus"] == "Neutral to Bearish"
    assert eur["raw_bull_text"] == "_DELETED_"
    assert eur["raw_bear_text"] == "_DELETED_"
    assert eur["raw_judge_text"] == "_DELETED_"

    merged = merge_dicts(state["debate_states"], pruned["debate_states"])
    merged_eur = merged["EURUSD"]
    assert "raw_bull_text" not in merged_eur
    assert "raw_bear_text" not in merged_eur
    assert "raw_judge_text" not in merged_eur


def test_sqlite_checkpointer_persistence():
    """Verify SqliteCheckpointSaver stores and restores checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_checkpoints.sqlite")
        saver1 = SqliteCheckpointSaver(db_path=db_file)

        config = {"configurable": {"thread_id": "t1", "checkpoint_ns": "ns1", "checkpoint_id": "c0"}}
        checkpoint = {
            "id": "c1",
            "ts": "2026-09-06T00:00:00Z",
            "channel_values": {"step": 1},
            "channel_versions": {"step": 1},
            "versions_seen": {},
        }
        metadata = {"source": "input", "step": 1, "writes": {}}

        saver1.put(config, checkpoint, metadata)

        # Restore in brand new saver instance from same sqlite file
        saver2 = SqliteCheckpointSaver(db_path=db_file)
        assert "t1" in saver2.storage
        assert "ns1" in saver2.storage["t1"]
        assert "c1" in saver2.storage["t1"]["ns1"]
        saved_entry = saver2.storage["t1"]["ns1"]["c1"]
        if isinstance(saved_entry, tuple):
            restored_chk = saver2.serde.loads_typed(saved_entry[0])
        else:
            restored_chk = saved_entry["checkpoint"]
        assert restored_chk["channel_values"]["step"] == 1


@pytest.mark.asyncio
async def test_sqlite_checkpointer_async_and_writes():
    """Verify SqliteCheckpointSaver stores and restores writes and async checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_writes.sqlite")
        saver1 = SqliteCheckpointSaver(db_path=db_file)

        config = {"configurable": {"thread_id": "t2", "checkpoint_ns": "ns2", "checkpoint_id": "c2"}}
        checkpoint = {
            "id": "c2",
            "ts": "2026-09-06T00:00:00Z",
            "channel_values": {"stage": "analysis"},
            "channel_versions": {"stage": 1},
            "versions_seen": {},
        }
        metadata = {"source": "loop", "step": 2, "writes": {}}

        # Async put checkpoint
        await saver1.aput(config, checkpoint, metadata)

        # Async put writes
        writes = [("output_channel", {"action": "buy", "confidence": 0.85})]
        await saver1.aput_writes(config, writes, task_id="task_abc")

        # Sync put writes
        writes2 = [("log_channel", "Order approved")]
        saver1.put_writes(config, writes2, task_id="task_def")

        # Restore in new saver instance
        saver2 = SqliteCheckpointSaver(db_path=db_file)
        assert "t2" in saver2.storage
        assert "c2" in saver2.storage["t2"]["ns2"]

        outer_key = ("t2", "ns2", "c2")
        assert outer_key in saver2.writes
        inner_keys = list(saver2.writes[outer_key].keys())
        assert len(inner_keys) >= 2
        # Verify restored channel
        task_id, channel, val_tuple, _ = saver2.writes[outer_key][inner_keys[0]]
        assert channel in ("output_channel", "log_channel")

