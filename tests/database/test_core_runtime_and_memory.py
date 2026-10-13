# ==============================================================================
# File: tests/database/test_phase3_core_runtime_and_memory.py
# ==============================================================================

"""
Comprehensive Unit Tests for Phase 3:
  1. Session DB WAL with soft-deactivation (active column)
  2. FTS5 with 8192 char truncation and sync triggers
  3. Session Lifecycle In-Place Soft Rewind
  4. Bounded Crash Repair Ledger
  5. Trajectory Compressor with Boundary Snapping & Tail Watermarking
"""

import json
import os
import tempfile
import time
from pathlib import Path
import pytest

from database.session_db_wal import SessionDbWal
from database.fts5_cjk import Fts5SessionSearch

from database.session_lifecycle import SessionLifecycleManager
from database.repair_ledger import RepairLedger
from analysis.providers.trajectory_compressor import TrajectoryCompressor


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = Path(tf.name)
    db = SessionDbWal(db_path=db_path, enable_read_pool=False)
    yield db
    db.close()
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            pass


# ==============================================================================
# 1. Session DB WAL Soft-Rewind & Active Filtering Tests
# ==============================================================================

def test_session_db_wal_active_column_and_filtering(temp_db):
    session_id = "test_sess_active"
    temp_db.create_or_touch_session(session_id)

    # Append 4 messages across 3 turns
    temp_db.append_message(session_id, "user", "Hello", turn_ordinal=1)
    temp_db.append_message(session_id, "assistant", "Hi there!", turn_ordinal=1)
    temp_db.append_message(session_id, "user", "Buy EURUSD", turn_ordinal=2)
    temp_db.append_message(session_id, "assistant", "Order placed", turn_ordinal=3)

    # Active messages should be 4
    active_msgs = temp_db.get_messages(session_id, active_only=True)
    assert len(active_msgs) == 4

    # Deactivate turns above turn 1
    deactivated = temp_db.deactivate_turns_above(session_id, turn_ordinal=1)
    assert deactivated == 2

    # Active messages should now only be turn 1
    active_after = temp_db.get_messages(session_id, active_only=True)
    assert len(active_after) == 2
    assert all(m["turn_ordinal"] == 1 for m in active_after)

    # Audit history: all messages still exist when active_only=False
    all_msgs = temp_db.get_messages(session_id, active_only=False)
    assert len(all_msgs) == 4


# ==============================================================================
# 2. FTS5 Indexing 8192 Char Bound & Auto-Sync Triggers
# ==============================================================================

def test_fts5_indexing_truncation_and_triggers(temp_db):
    conn = temp_db.get_connection()
    fts = Fts5SessionSearch(conn)

    session_id = "test_sess_fts"
    temp_db.create_or_touch_session(session_id)

    # Generate a massive 20,000-character tool output
    huge_output = "MACD_ANALYSIS " * 1500  # ~21000 chars
    row_id = temp_db.append_message(session_id, "tool", huge_output, turn_ordinal=1)

    # Index message into FTS
    fts.index_message(row_id, session_id, "tool", huge_output)

    # Search should succeed and locate term
    results = fts.search("MACD_ANALYSIS", session_id=session_id)
    assert len(results) >= 1
    assert results[0]["row_id"] == row_id


# ==============================================================================
# 3. Session Lifecycle In-Place Soft Rewind
# ==============================================================================

def test_session_lifecycle_soft_rewind(temp_db):
    mgr = SessionLifecycleManager(temp_db)
    session_id = "test_sess_rewind"
    temp_db.create_or_touch_session(session_id, title="Trading Session")

    # Add 4 turns
    for t in range(1, 5):
        temp_db.append_message(session_id, "user", f"Turn {t} query", turn_ordinal=t)
        temp_db.append_message(
            session_id,
            "assistant",
            f"Turn {t} response",
            turn_ordinal=t,
            carrier_marker=f"carrier_{t}",
        )

    # Rewind to turn 2
    deactivated = mgr.rewind_session(session_id, target_turn=2)
    assert deactivated == 4  # Turns 3 and 4 (2 msgs each = 4 msgs)

    # Verify active messages
    active_msgs = temp_db.get_messages(session_id, active_only=True)
    assert len(active_msgs) == 4
    assert max(m["turn_ordinal"] for m in active_msgs) == 2

    # Verify session metadata records rewind audit
    sess = temp_db.get_session(session_id)
    meta = json.loads(sess["metadata_json"])
    assert meta["last_active_turn"] == 2
    assert len(meta["rewind_history"]) == 1
    assert meta["rewind_history"][0]["target_turn"] == 2


# ==============================================================================
# 4. Crash Repair Ledger
# ==============================================================================

def test_repair_ledger_orphaned_tool_calls(temp_db):
    repair = RepairLedger(temp_db)
    session_id = "test_sess_repair"
    temp_db.create_or_touch_session(session_id)

    # Insert an assistant turn that called a tool with tool_call_id
    tool_content = '{"thought": "Fetch price", "tool_calls": [{"id": "call_mt5_123", "name": "get_quote"}]}'
    temp_db.append_message(session_id, "assistant", tool_content, turn_ordinal=1)

    # Followed immediately by a new user message (meaning the agent was interrupted/crashed!)
    temp_db.append_message(session_id, "user", "What happened?", turn_ordinal=2)

    # Run repair diagnostics
    repaired_count = repair.detect_and_repair_orphaned_tool_calls(session_id)
    assert repaired_count == 1

    # Verify a synthetic tool message was injected
    msgs = temp_db.get_messages(session_id, active_only=True)
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "interrupted" in tool_msgs[0]["content"]

    # Verify audit history
    history = repair.get_repair_history(limit=5)
    assert len(history) >= 1
    assert history[0]["issue_type"] == "ORPHANED_TOOL_CALL"


# ==============================================================================
# 5. Trajectory Compressor Boundary Snapping & Tail Watermarking
# ==============================================================================

def test_trajectory_compressor_boundary_snapping_and_watermark():
    compressor = TrajectoryCompressor(
        max_tool_output_chars=100,
        preserve_recent_turns=1,
        summarize_intermediate_threshold=2,
    )


    # Create a conversation with system, initial user, intermediate turns, and tool calls
    messages = [
        {"role": "system", "content": "You are Monika institutional agent."},
        {"role": "user", "content": "Initialize portfolio setup."},
        {"role": "assistant", "content": "<think>Processing...</think>Setting up database."},
        {"role": "user", "content": "Query account balance."},
        {"role": "assistant", "content": "Querying MT5.", "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "content": "Balance: $500,000 " * 50, "tool_call_id": "call_1"},
        {"role": "assistant", "content": "Balance is $500,000."},
        {"role": "user", "content": "Buy 0.1 lots EURUSD."},
        {"role": "assistant", "content": "Order placed successfully."},
    ]

    compressed = compressor.compress_trajectory(messages)

    # System prompt must be preserved at head
    assert compressed[0]["role"] == "system"
    assert "Monika" in compressed[0]["content"]

    # Initial user prompt must be preserved
    assert compressed[1]["role"] == "user"
    assert "Initialize portfolio" in compressed[1]["content"]

    # Intermediate tool output must be truncated
    tool_msg = [m for m in compressed if m["role"] == "tool"][0]
    assert len(tool_msg["content"]) < 300
    assert "truncated" in tool_msg["content"]

    # Intermediate summary notice should be injected
    assert any("[Context Compaction Notice" in m.get("content", "") for m in compressed)

    # Tail watermark should be attached to the start of tail
    assert any(m.get("_tail_watermark") is True for m in compressed)
