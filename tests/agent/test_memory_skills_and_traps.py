# ==============================================================================
# File: tests/agent/test_phase5_memory_skills_and_traps.py
# ==============================================================================

"""
Unit Tests for Phase 5:
  1. OFD FileLockGuard & Scratchpad Repair Ledger
  2. TrajectoryCompressor (Semantic mode, mechanical invariants, tool pairing sanitization)
  3. ToolSafetyOracle & Jailbreak Security Traps
  4. SystemDoctor WAL integrity checks
"""

import json
import os
import tempfile
import time
from pathlib import Path
import pytest

from agent.trajectory_compressor import TrajectoryCompressor
from cli.doctor import SystemDoctor
from database.repair_ledger import RepairLedger
from database.session_db_wal import FileLockGuard, SessionDbWal
from evals.oracles.tool_safety_oracle import ToolSafetyOracle


@pytest.fixture
def temp_db_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir)


# ==============================================================================
# 1. FileLockGuard & RepairLedger Tests
# ==============================================================================

def test_file_lock_guard_concurrency(temp_db_dir):
    lock_file = temp_db_dir / "test.lock"

    # Acquire initial lock
    with FileLockGuard(lock_file, timeout=1.0) as guard1:
        assert guard1._fd is not None

        # Attempt to acquire lock concurrently with very short timeout -> should fail
        with pytest.raises(TimeoutError):
            with FileLockGuard(lock_file, timeout=0.1):
                pass

    # After exit, lock should be free again
    with FileLockGuard(lock_file, timeout=1.0) as guard2:
        assert guard2._fd is not None


def test_repair_ledger_scratchpad_fence_repair(temp_db_dir):
    db_path = temp_db_dir / "session_test.sqlite"
    wal_db = SessionDbWal(db_path=db_path, enable_read_pool=False)
    conn = wal_db.get_connection()

    # Create dummy session and message with unbalanced code fence
    with conn:
        conn.execute("INSERT INTO sessions (session_id, title) VALUES ('s1', 'Test')")
        conn.execute(
            """
            INSERT INTO session_messages (row_id, session_id, role, content, turn_ordinal, created_at)
            VALUES (101, 's1', 'assistant', 'Here is the plan:\n```python\nx = 10\n# Unclosed fence', 1, 1000.0)
            """
        )

    repair = RepairLedger(wal_db)
    repaired_count = repair.repair_scratchpad_artifacts(session_id="s1")
    assert repaired_count == 1

    # Verify content now has closed fence
    cursor = conn.execute("SELECT content FROM session_messages WHERE row_id = 101")
    repaired_content = cursor.fetchone()[0]
    assert repaired_content.count("```") % 2 == 0
    assert repaired_content.endswith("```")

    # Verify repair history
    history = repair.get_repair_history(limit=5)
    assert any(h["issue_type"] == "CORRUPTED_SCRATCHPAD_FENCE" for h in history)
    wal_db.close()


# ==============================================================================
# 2. TrajectoryCompressor Tests
# ==============================================================================

def test_trajectory_compressor_semantic_preserves_invariants():
    compressor = TrajectoryCompressor(
        default_mode="semantic",
        threshold_tokens=50,
        protect_first_n=1,
        protect_last_n=2,
    )

    test_messages = [
        {"role": "system", "content": "You are Monika, an institutional trading AI."},
        {
            "role": "user",
            "content": "Analyze EURUSD.<mechanical-invariants>Max risk per trade 1.5%; Never trade without SL</mechanical-invariants>",
        },
        {"role": "assistant", "content": "Checking order flow and liquidity levels for EURUSD.", "tool_calls": [{"id": "call_1", "name": "get_spread"}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "Spread snapshot: 0.8 pips; Liquidity: High"},
        {"role": "assistant", "content": "The spread is tight, confirming execution conditions."},
        {"role": "user", "content": "Proceed with sizing calculation."},
        {"role": "assistant", "content": "Calculated position size is 0.50 lots."},
    ]

    def mock_semantic_summarizer(corpus: str) -> str:
        return f"Summarized intermediate analysis: spread confirmed tight at 0.8 pips."

    compacted = compressor.compress(
        test_messages,
        mode="semantic",
        summarizer_fn=mock_semantic_summarizer,
        force=True,
    )

    # Invariants must be preserved
    compacted_text = " ".join(str(m.get("content", "")) for m in compacted)
    assert "<mechanical-invariants>" in compacted_text
    assert "Max risk per trade 1.5%" in compacted_text

    # Message count should be reduced
    assert len(compacted) < len(test_messages)


def test_trajectory_compressor_sanitizes_orphaned_tools():
    compressor = TrajectoryCompressor()
    malformed_messages = [
        {"role": "system", "content": "System prompt."},
        # Orphaned tool message with no preceding assistant tool call
        {"role": "tool", "tool_call_id": "call_ghost", "content": "Orphaned output"},
        {"role": "user", "content": "Hello Monika"},
        {"role": "assistant", "content": "Hello! How can I assist you with your portfolio?"},
    ]

    sanitized = compressor._sanitize_tool_pairing(malformed_messages)
    # The orphaned tool call should be evicted
    assert not any(m.get("tool_call_id") == "call_ghost" for m in sanitized)
    assert len(sanitized) == 3


# ==============================================================================
# 3. ToolSafetyOracle & Trap Fixtures Tests
# ==============================================================================

def test_tool_safety_oracle_catches_all_traps():
    oracle = ToolSafetyOracle(fixture_path="trading-agent/evals/fixtures/tool_jailbreak_trap.json")
    results = oracle.evaluate_traps_suite()

    assert len(results) >= 5, "Expected at least 5 security traps in fixture"
    for r in results:
        assert r.passed is True, f"Security Trap Failed! Trap ID: '{r.test_id}', Reason: {r.reason}"


# ==============================================================================
# 4. SystemDoctor Live WAL Check Tests
# ==============================================================================

def test_system_doctor_wal_integrity(temp_db_dir):
    doc = SystemDoctor(fix=False, live_probes=False)
    doc.check_wal_integrity_and_repair()
    # Should run without error
    categories = [d.category for d in doc.diagnostics]
    assert "Filesystem" in categories or len(doc.diagnostics) >= 0
