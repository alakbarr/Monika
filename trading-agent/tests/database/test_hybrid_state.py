# ==============================================================================
# File: tests/database/test_hybrid_state.py
# ==============================================================================

"""
Unit Test Suite for Stage 3:
Hybrid State, SQLite WAL with Bounded Read Pool, FileLockGuard, FTS5 Fail-Open,
and Session Lifecycle Lineage & Portability.
"""

import json
import sqlite3
import tempfile
import threading
from pathlib import Path
import pytest

from database.session_db_wal import (
    SessionDbWal,
    SessionDbReadPool,
    FileLockGuard,
    check_fd_headroom,
)
from database.fts5_cjk import tokenize_cjk_bigram, sanitize_fts5_term, Fts5SessionSearch
from database.session_lifecycle import (
    SessionLifecycleManager,
    derive_session_title,
    EXPORT_SCHEMA_VERSION,
)
from agent.state_rewind import StateRewindManager, CARRIER_SIDE_EFFECT_PERSISTED


# ==============================================================================
# 1. Bounded Read Pool & Headroom Tests
# ==============================================================================

def test_fd_headroom_check():
    """Headroom check must return boolean without raising."""
    assert isinstance(check_fd_headroom(), bool)


def test_session_db_read_pool_bounded():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_pool.sqlite"
        wal_db = SessionDbWal(db_path, enable_read_pool=True)
        wal_db.append_message("sess_pool", "user", "Test content", 1)

        # Acquire readers concurrently
        readers = []
        for _ in range(4):
            gen = wal_db.acquire_reader()
            conn = gen.__enter__()
            readers.append((gen, conn))
            cursor = conn.execute("SELECT COUNT(*) FROM session_messages;")
            assert cursor.fetchone()[0] == 1

        # Release readers
        for gen, _ in readers:
            gen.__exit__(None, None, None)

        wal_db.close()


def test_file_lock_guard_exclusive():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lock_file = Path(tmp_dir) / "test.lock"
        with FileLockGuard(lock_file) as guard:
            assert guard._fd is not None

        # Lock should be released and re-acquirable
        with FileLockGuard(lock_file) as guard2:
            assert guard2._fd is not None


# ==============================================================================
# 2. WAL Pragmas, Checkpoint & Hot Backup
# ==============================================================================

def test_wal_pragmas_checkpoint_and_vacuum():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_wal_ops.sqlite"
        wal_db = SessionDbWal(db_path)

        for i in range(10):
            wal_db.append_message("s_wal", "user", f"Turn {i} message", i)

        # Test WAL checkpoint
        busy, log, ckpt = wal_db.wal_checkpoint("PASSIVE")
        assert isinstance(busy, int)
        assert isinstance(log, int)
        assert isinstance(ckpt, int)

        # Test hot backup via vacuum_into
        backup_path = Path(tmp_dir) / "backup.sqlite"
        wal_db.vacuum_into(backup_path)
        assert backup_path.exists()

        # Verify backup integrity
        backup_conn = sqlite3.connect(str(backup_path))
        cur = backup_conn.execute("SELECT COUNT(*) FROM session_messages;")
        assert cur.fetchone()[0] == 10
        backup_conn.close()

        wal_db.close()


# ==============================================================================
# 3. FTS5 with CJK Bigram and Fail-Open Resilience
# ==============================================================================

def test_fts5_sanitize_term():
    raw = 'EURUSD "breakout" +strategy: (H1)*'
    cleaned = sanitize_fts5_term(raw)
    assert '"' not in cleaned
    assert '*' not in cleaned
    assert ':' not in cleaned
    assert 'breakout strategy H1' in cleaned


def test_fts5_search_fail_open_on_malformed_query():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_fts_failopen.sqlite"
        wal_db = SessionDbWal(db_path)
        conn = wal_db.get_connection()

        fts = Fts5SessionSearch(conn)
        fts.index_message(1, "s1", "user", "Gold analysis on 15m timeframe")
        fts.index_message(2, "s1", "assistant", "XAUUSD rejected key level 2650")

        # Standard match
        res = fts.search("Gold analysis", session_id="s1")
        assert len(res) == 1
        assert res[0]["row_id"] == 1

        # Malformed search with unclosed quotes and operators that would crash raw FTS5
        res_malformed = fts.search('"""(((+++ Gold ***:::')
        assert len(res_malformed) >= 1
        assert res_malformed[0]["row_id"] == 1

        wal_db.close()


# ==============================================================================
# 4. Session Lifecycle, Lineage & Portability
# ==============================================================================

def test_derive_session_title():
    messages = [
        {"role": "system", "content": "You are Monika"},
        {"role": "user", "content": "/plan Analisis swing trade GBPUSD untuk minggu depan"},
    ]
    title = derive_session_title(messages)
    assert title == "Analisis swing trade GBPUSD untuk minggu depan"

    # Truncation test
    long_msg = [{"role": "user", "content": "A" * 100}]
    assert len(derive_session_title(long_msg)) <= 50


def test_session_fork_and_lineage():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_lifecycle.sqlite"
        wal_db = SessionDbWal(db_path)
        mgr = SessionLifecycleManager(wal_db)

        # Parent session
        wal_db.create_or_touch_session("parent_sess", title="Parent Trading Session")
        wal_db.append_message("parent_sess", "user", "Initial thought", 1)
        wal_db.append_message("parent_sess", "assistant", "Strategy idea", 1)
        wal_db.append_message("parent_sess", "user", "Second question", 2)
        wal_db.record_tool_execution("parent_sess", 1, "fetch_ticker", {"sym": "EURUSD"}, "1.0850")

        # Fork up to turn 1
        child_id = mgr.fork_session("parent_sess", up_to_turn=1, title="Child Scenario A")

        # Verify child session contains only turn 1
        child_msgs = wal_db.get_messages(child_id)
        assert len(child_msgs) == 2
        assert all(m["turn_ordinal"] == 1 for m in child_msgs)

        child_tools = wal_db.get_tool_records(child_id)
        assert len(child_tools) == 1
        assert child_tools[0]["tool_name"] == "fetch_ticker"

        # Lineage check
        lineage = mgr.get_session_lineage(child_id)
        assert len(lineage) == 2
        assert lineage[0]["session_id"] == child_id
        assert lineage[0]["parent_session_id"] == "parent_sess"
        assert lineage[1]["session_id"] == "parent_sess"

        # Close session
        mgr.mark_session_closed(child_id, reason="compression")
        sess_data = wal_db.get_session(child_id)
        assert sess_data["end_reason"] == "compression"

        wal_db.close()


def test_session_export_and_import_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_export.sqlite"
        wal_db = SessionDbWal(db_path)
        mgr = SessionLifecycleManager(wal_db)

        s_id = "export_sess_01"
        wal_db.create_or_touch_session(s_id, title="Export Test")
        wal_db.append_message(s_id, "user", "Calculate Kelly criterion", 1)
        wal_db.record_tool_execution(s_id, 1, "calc_kelly", {"win_rate": 0.6}, "f=0.2")

        bundle = mgr.export_session_json(s_id)
        assert bundle["schema_version"] == EXPORT_SCHEMA_VERSION
        assert len(bundle["messages"]) == 1
        assert len(bundle["tool_records"]) == 1

        # Import into fresh session
        imported_id = mgr.import_session_json(bundle, override_session_id="imported_sess_01")
        assert imported_id == "imported_sess_01"

        imported_msgs = wal_db.get_messages(imported_id)
        assert len(imported_msgs) == 1
        assert imported_msgs[0]["content"] == "Calculate Kelly criterion"

        imported_tools = wal_db.get_tool_records(imported_id)
        assert len(imported_tools) == 1
        assert imported_tools[0]["tool_name"] == "calc_kelly"

        wal_db.close()


def test_rewind_integration_remains_intact():
    """Verify StateRewindManager operates seamlessly with enhanced SessionDbWal."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_rewind_compat.sqlite"
        wal_db = SessionDbWal(db_path)
        rewind_mgr = StateRewindManager(wal_db)

        s_id = "sess_compat"
        wal_db.append_message(s_id, "user", "Turn 1 Q", 1)
        wal_db.append_message(s_id, "assistant", "Turn 1 A", 1)
        wal_db.append_message(s_id, "user", "Turn 2 Q", 2)
        wal_db.append_message(s_id, "assistant", "Turn 2 A", 2)

        outcome = rewind_mgr.rewind_session(s_id, user_ordinal=-1)
        assert outcome.undone_count == 2
        assert len(outcome.active_prefix) == 2

        wal_db.close()
