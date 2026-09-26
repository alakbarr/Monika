# ==============================================================================
# File: tests/database/test_phase2_unified_state_and_compression.py
# ==============================================================================

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock

from database.session_db_wal import SessionDbWal, FileLockGuard, check_fd_headroom
from database.models import AgentSession, AgentSessionMessage, SystemPrompt
from analysis.memory.prompt_cache_boundary import (
    PromptCacheBoundaryPlanner,
    PromptCacheProfile,
    CacheBoundaryPlan,
)
from agent.three_part_context_compressor import ThreePartContextCompressor
from agent.state_rewind import (
    StateRewindManager,
    RewindOutcome,
    ConcurrencyConflictError,
    CARRIER_SIDE_EFFECT_PERSISTED,
)


def test_fd_headroom_check():
    """Verify that file descriptor headroom check runs safely."""
    assert check_fd_headroom(reserve=16) is True


def test_session_db_wal_basic_and_checkpoint(tmp_path: Path):
    """Test SQLite WAL mode, session insertion, messages, tool records, and WAL checkpoint."""
    db_file = tmp_path / "test_wal.sqlite"
    wal_mgr = SessionDbWal(db_path=db_file, enable_read_pool=True)

    # 1. Create or touch session
    wal_mgr.create_or_touch_session(
        session_id="sess_001",
        title="Test Trading Session",
        metadata={"user": "trader_1", "env": "paper"},
        root_session_id="sess_root",
    )

    sess = wal_mgr.get_session("sess_001")
    assert sess is not None
    assert sess["session_id"] == "sess_001"
    assert sess["title"] == "Test Trading Session"
    assert sess["root_session_id"] == "sess_root"

    # 2. Append messages
    m1_id = wal_mgr.append_message("sess_001", "user", "Analyze EURUSD", 1)
    m2_id = wal_mgr.append_message("sess_001", "assistant", "EURUSD is bullish", 1, carrier_marker="turn_1")
    assert m1_id > 0
    assert m2_id > m1_id

    msgs = wal_mgr.get_messages("sess_001")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["carrier_marker"] == "turn_1"

    # 3. Record tool execution
    t1_id = wal_mgr.record_tool_execution(
        session_id="sess_001",
        turn_ordinal=1,
        tool_name="market_data",
        arguments={"symbol": "EURUSD"},
        output="1.0850",
        is_error=False,
    )
    assert t1_id > 0
    tools = wal_mgr.get_tool_records("sess_001")
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "market_data"

    # 4. Checkpoint
    busy, log_pages, checkpointed = wal_mgr.wal_checkpoint("PASSIVE")
    assert isinstance(busy, int)
    assert isinstance(log_pages, int)

    # 5. Vacuum into
    backup_file = tmp_path / "backup.sqlite"
    wal_mgr.vacuum_into(backup_file)
    assert backup_file.exists()

    wal_mgr.close()


def test_prompt_cache_boundary_planner():
    """Verify prompt cache boundary planning and breakpoint tagging."""
    planner = PromptCacheBoundaryPlanner(
        profile=PromptCacheProfile(min_cacheable_tokens=50, max_breakpoints=3)
    )

    # Register stable prefix
    planner.register_stable_prefix("prefix_core", "System prompt: Trading agent core instructions and risk rules." * 5)

    messages = [
        {"role": "system", "content": "System prompt: Trading agent core instructions and risk rules." * 5},
        {"role": "user", "content": "Can you check gold price action over the last 4 hours?"},
        {"role": "assistant", "content": "Gold is consolidating near 2050 resistance with declining volume."},
        {"role": "user", "content": "What about silver?"},
    ]

    plan: CacheBoundaryPlan = planner.plan_boundaries(messages, provider="anthropic")
    assert len(plan.messages) == 4
    assert len(plan.breakpoint_indices) >= 1 or "cache_control" in str(plan.messages[0])


def test_three_part_compressor_micro_compaction():
    """Verify micro compaction of old exchanges and role alternation safety."""
    compressor = ThreePartContextCompressor(
        protect_first_n=1,
        protect_last_n=2,
        max_tool_output_chars=100,
        compression_threshold_tokens=50,
    )

    # Construct conversation history with tool calls
    history = [
        {"role": "system", "content": "You are Monika, institutional quant assistant."},
        {"role": "user", "content": "Run quick diagnostic on volatility surfaces."},
        {
            "role": "assistant",
            "content": "Checking orderbook",
            "tool_calls": [{"id": "c1", "function": {"name": "fetch_book", "arguments": "{}"}}],
        },
        {"role": "tool", "content": "Bids: 100 @ 1.0850, Asks: 100 @ 1.0852", "tool_call_id": "c1"},
        {"role": "assistant", "content": "Book confirms liquidity."},
        {"role": "user", "content": "Synthesize risk outlook."},
    ]

    # Test micro compaction with summarizer
    compacted = compressor.micro_compact_exchange(
        history,
        exchange_summarizer=lambda txt: "Checked orderbook and confirmed liquidity.",
    )
    assert len(compacted) < len(history)
    # Ensure role alternation is preserved
    for i in range(1, len(compacted)):
        assert compacted[i]["role"] != compacted[i-1]["role"]


def test_state_rewind_concurrency_and_carrier_splitting(tmp_path: Path):
    """Test concurrency verification and composite carrier splitting in StateRewindManager."""
    db_file = tmp_path / "test_rewind.sqlite"
    wal_mgr = SessionDbWal(db_path=db_file)
    rewind_mgr = StateRewindManager(wal_mgr)

    # Create session with 3 turns
    wal_mgr.create_or_touch_session("sess_rewind", title="Rewind Test")
    wal_mgr.append_message("sess_rewind", "user", "T1: Start session", 1)
    wal_mgr.append_message("sess_rewind", "assistant", "T1: Started", 1, carrier_marker="turn_1")
    wal_mgr.append_message("sess_rewind", "user", "T2: Check risk", 2)
    wal_mgr.append_message("sess_rewind", "assistant", "T2: Risk OK", 2, carrier_marker="turn_2")
    wal_mgr.append_message("sess_rewind", "user", "T3: Place order", 3)
    wal_mgr.append_message("sess_rewind", "assistant", "T3: Placed", 3, carrier_marker="turn_3")

    initial_msgs = wal_mgr.get_messages("sess_rewind")
    assert len(initial_msgs) == 6
    active_ids = [m["row_id"] for m in initial_msgs]

    # 1. Test failed concurrency check (stale active IDs)
    stale_ids = active_ids[:-1]
    with pytest.raises(ConcurrencyConflictError):
        rewind_mgr.rewind_session("sess_rewind", user_ordinal=-1, expected_active_ids=stale_ids)

    # 2. Test successful rewind to last user turn (turn 3)
    outcome: RewindOutcome = rewind_mgr.rewind_session(
        "sess_rewind", user_ordinal=-1, expected_active_ids=active_ids
    )
    assert outcome.undone_count == 2
    assert not outcome.carrier_side_effect_persisted

    remaining_msgs = wal_mgr.get_messages("sess_rewind")
    assert len(remaining_msgs) == 4
    assert max(m["turn_ordinal"] for m in remaining_msgs) == 2

    # 3. Test carrier preservation with side-effects
    # Append a turn that has financial side-effects
    wal_mgr.append_message("sess_rewind", "user", "T3: Submit real order", 3)
    wal_mgr.append_message("sess_rewind", "assistant", "T3: Order sent to MT5", 3)
    wal_mgr.record_tool_execution(
        session_id="sess_rewind",
        turn_ordinal=3,
        tool_name="mt5_order_send",
        arguments={"symbol": "EURUSD", "volume": 0.1},
        output="Ticket 12345",
        has_side_effects=True,
    )
    
    msgs_with_trade = wal_mgr.get_messages("sess_rewind")
    active_ids2 = [m["row_id"] for m in msgs_with_trade]
    
    outcome_trade = rewind_mgr.rewind_session("sess_rewind", user_ordinal=-1, expected_active_ids=active_ids2)
    assert outcome_trade.carrier_side_effect_persisted
    
    # Verify carrier marker updated in DB
    updated_msgs = wal_mgr.get_messages("sess_rewind")
    assert any(m.get("carrier_marker") == CARRIER_SIDE_EFFECT_PERSISTED for m in updated_msgs)

    wal_mgr.close()

