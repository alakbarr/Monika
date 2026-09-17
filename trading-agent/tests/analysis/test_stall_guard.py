import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.harness.stall_guard import StallGuard
from analysis.harness.agent_harness import AgentHarness


def test_stall_guard_read_only_classification():
    guard = StallGuard()

    # Read-only tools
    assert guard.is_read_only("get_price_history") is True
    assert guard.is_read_only("get_technical_indicators") is True
    assert guard.is_read_only("get_news_items") is True
    assert guard.is_read_only("search_tools") is True
    assert guard.is_read_only("execute_analysis_code") is True

    # State advancing tools
    assert guard.is_read_only("submit_asset_analysis") is False
    assert guard.is_read_only("submit_fundamental_brief") is False
    assert guard.is_read_only("propose_action") is False


def test_stall_guard_consecutive_read_trigger_and_reset():
    guard = StallGuard(warning_threshold=3, force_terminate_threshold=5)

    # 1. First two read calls: OK
    guard.record_call("get_price_history", {"data": [1, 2, 3]})
    guard.record_call("get_technical_indicators", {"rsi": 50})
    is_warn, is_term, msg = guard.check_stall()
    assert is_warn is False
    assert is_term is False

    # 2. Third read call: Warning triggered
    guard.record_call("get_atr", {"atr": 0.0015})
    is_warn, is_term, msg = guard.check_stall()
    assert is_warn is True
    assert is_term is False
    assert "[STALL GUARD WARNING]" in (msg or "")

    # 3. State-advancing action resets the guard
    guard.record_call("submit_asset_analysis", {"decision": "buy"})
    is_warn, is_term, msg = guard.check_stall()
    assert is_warn is False
    assert is_term is False
    assert guard.consecutive_read_count == 0


def test_stall_guard_execute_analysis_code_does_not_reset():
    guard = StallGuard(warning_threshold=3, force_terminate_threshold=5)
    guard.record_call("get_price_history", {"data": [1, 2, 3]})
    assert guard.consecutive_read_count == 1
    # execute_analysis_code should NOT reset stall guard
    guard.record_call("execute_analysis_code", {"stdout": "result"})
    assert guard.consecutive_read_count == 2
    # Check warning triggers on 3rd call
    guard.record_call("execute_analysis_code", {"stdout": "result2"})
    assert guard.consecutive_read_count == 3
    is_warn, is_term, msg = guard.check_stall()
    assert is_warn is True
    assert is_term is False


def test_stall_guard_force_terminate():
    guard = StallGuard(warning_threshold=2, force_terminate_threshold=4)

    # Call 4 read-only tools in a row
    for i in range(4):
        guard.record_call(f"get_data_{i}", {"val": i})

    is_warn, is_term, msg = guard.check_stall()
    assert is_term is True
    assert "[STALL GUARD CRITICAL]" in (msg or "")


def test_stall_guard_identical_result_loop():
    guard = StallGuard(warning_threshold=5, force_terminate_threshold=8)
    identical_payload = {"error": "symbol not found"}

    # Repeated identical responses across 3 calls
    for _ in range(3):
        guard.record_call("get_tick", identical_payload)

    is_warn, is_term, msg = guard.check_stall()
    assert is_warn is True
    assert "[STALL GUARD WARNING]" in (msg or "")


@pytest.mark.asyncio
async def test_agent_harness_stall_guard_integration():
    mock_client = MagicMock()
    mock_client.run_tool_agent = AsyncMock()
    mock_client.model = "test-model"
    mock_client.provider_name = "test-provider"

    harness = AgentHarness(
        llm_client=mock_client,
        settings={"stall_warning_threshold": 2, "stall_terminate_threshold": 4},
        max_tool_turns=10,
    )

    assert harness.stall_guard is not None
    assert harness.stall_guard.warning_threshold == 2
    assert harness.stall_guard.force_terminate_threshold == 4
