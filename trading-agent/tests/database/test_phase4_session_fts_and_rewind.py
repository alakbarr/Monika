# ==============================================================================
# File: tests/database/test_phase4_session_fts_and_rewind.py
# ==============================================================================

"""
Unit Test Suite for Phase 4:
SessionDB SQLite WAL, FTS5 CJK Bigram Tokenizer, and Carrier-Aware State Rewind (/undo).
"""

import tempfile
from pathlib import Path
import pytest

from database.session_db_wal import SessionDbWal
from database.fts5_cjk import tokenize_cjk_bigram, Fts5SessionSearch
from agent.state_rewind import (
    StateRewindManager,
    RewindTargetUnavailableError,
    CARRIER_SIDE_EFFECT_PERSISTED,
)


# ==============================================================================
# 1. SessionDbWal Tests
# ==============================================================================

def test_session_db_wal_mode_and_message_crud():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sessions.sqlite"
        db = SessionDbWal(db_path)
        conn = db.get_connection()

        # Check WAL mode
        cursor = conn.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"

        # Append messages
        s_id = "sess_001"
        r1 = db.append_message(s_id, role="user", content="Analyze EURUSD trend", turn_ordinal=1)
        r2 = db.append_message(s_id, role="assistant", content="EURUSD is in bullish structure", turn_ordinal=1)
        assert r1 > 0
        assert r2 > r1

        msgs = db.get_messages(s_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        db.close()


# ==============================================================================
# 2. FTS5 CJK Bigram Tokenizer Tests
# ==============================================================================

def test_cjk_bigram_tokenizer():
    # Pure latin
    res1 = tokenize_cjk_bigram("EURUSD breakout strategy")
    assert res1 == "EURUSD breakout strategy"

    # CJK characters
    res2 = tokenize_cjk_bigram("今天天气很好")
    assert "今天" in res2
    assert "天天" in res2
    assert "很好" in res2

    # Mixed Latin and CJK
    res3 = tokenize_cjk_bigram("XAUUSD 突破 策略")
    assert "XAUUSD" in res3
    assert "突破" in res3
    assert "策略" in res3


def test_fts5_indexing_and_search():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_fts.sqlite"
        db = SessionDbWal(db_path)
        conn = db.get_connection()

        fts = Fts5SessionSearch(conn)

        # Index multiple messages
        fts.index_message(row_id=1, session_id="s1", role="user", content="Berapa stop loss ideal untuk EURUSD hari ini?")
        fts.index_message(row_id=2, session_id="s1", role="assistant", content="Gunakan 25 pips stop loss di bawah support 1.0820.")
        fts.index_message(row_id=3, session_id="s1", role="user", content="XAUUSD 黄金 突破 策略 分析")

        # Search Latin query
        results_latin = fts.search("stop loss", session_id="s1")
        assert len(results_latin) >= 2
        matched_ids = {r["row_id"] for r in results_latin}
        assert 1 in matched_ids
        assert 2 in matched_ids

        # Search CJK query
        results_cjk = fts.search("黄金 突破", session_id="s1")
        assert len(results_cjk) == 1
        assert results_cjk[0]["row_id"] == 3

        db.close()


# ==============================================================================
# 3. Carrier-Aware State Rewind Tests (/undo)
# ==============================================================================

def test_state_rewind_normal_turn():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_rewind.sqlite"
        db = SessionDbWal(db_path)
        rewind_mgr = StateRewindManager(db)

        s_id = "sess_undo"
        # Turn 1
        db.append_message(s_id, role="user", content="Turn 1 User Question", turn_ordinal=1)
        db.append_message(s_id, role="assistant", content="Turn 1 Assistant Answer", turn_ordinal=1)

        # Turn 2
        db.append_message(s_id, role="user", content="Turn 2 User Question", turn_ordinal=2)
        db.append_message(s_id, role="assistant", content="Turn 2 Assistant Answer", turn_ordinal=2)

        # Record normal tool call (no side effect)
        db.record_tool_execution(s_id, turn_ordinal=2, tool_name="get_market_quote", arguments={"sym": "EURUSD"}, output="1.0850", has_side_effects=False)

        # Rewind Turn 2 (user_ordinal = -1)
        outcome = rewind_mgr.rewind_session(s_id, user_ordinal=-1)
        assert not outcome.carrier_side_effect_persisted
        assert outcome.undone_count == 2
        assert len(outcome.active_prefix) == 2
        assert outcome.active_prefix[-1]["role"] == "assistant"

        # Check DB rows
        remaining_msgs = db.get_messages(s_id)
        assert len(remaining_msgs) == 2
        assert remaining_msgs[0]["content"] == "Turn 1 User Question"
        db.close()


def test_state_rewind_with_carrier_financial_side_effects():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_rewind_side_effect.sqlite"
        db = SessionDbWal(db_path)
        rewind_mgr = StateRewindManager(db)

        s_id = "sess_trade"
        # Turn 1: user triggers an order execution
        db.append_message(s_id, role="user", content="Buy 0.1 lots EURUSD now", turn_ordinal=1)
        db.append_message(s_id, role="assistant", content="Order executed successfully ticket #987654", turn_ordinal=1)

        # Record financial transaction tool execution
        db.record_tool_execution(
            s_id,
            turn_ordinal=1,
            tool_name="execute_order",
            arguments={"symbol": "EURUSD", "lots": 0.1},
            output="Order filled",
            has_side_effects=True,
        )

        # Rewind Turn 1
        outcome = rewind_mgr.rewind_session(s_id, user_ordinal=-1)
        assert outcome.carrier_side_effect_persisted
        assert "remain permanently recorded" in outcome.status_message

        # Verify DB records were NOT deleted, but annotated with CARRIER_SIDE_EFFECT_PERSISTED
        remaining = db.get_messages(s_id)
        assert len(remaining) == 2
        assert remaining[0]["carrier_marker"] == CARRIER_SIDE_EFFECT_PERSISTED
        db.close()


def test_state_rewind_empty_history_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_rewind_empty.sqlite"
        db = SessionDbWal(db_path)
        rewind_mgr = StateRewindManager(db)

        with pytest.raises(RewindTargetUnavailableError):
            rewind_mgr.rewind_session("non_existent_session")
        db.close()
