"""
Comprehensive Test Suite for Advanced Harness Enhancements.

Verifies:
1. Cryptographic Evidence Hashing & Proposal Integrity Ledger (Phase 1).
2. Mandatory Read-Before-Mutate Guardrail (Phase 2).
3. Interactive Multi-Step Planning & TODO State Machine (Phase 3).
4. Physical Deliverable Git-Porcelain Gate & Anti-Hallucination Audit (Phase 4).
5. Token Economics: General Tool Pruning & Replay-Prefix KV-Cache Preserving Summarization (Phase 5).
6. In-Flight Emergency Steering Cancellation, Narrative Truncation, and Escalating Tool Reminders.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.agent.harness.agent_harness import AgentHarness
from monika.application.agent.harness.context_compressor import ContextCompressor
from monika.application.agent.harness.general_tool_pruner import (
    GeneralToolPruner,
    truncate_head,
    truncate_line,
    truncate_tail,
)
from monika.application.agent.harness.interactive_todo import TodoListState
from monika.application.agent.harness.physical_deliverable_gate import PhysicalDeliverableGate
from monika.application.agent.harness.verification_evidence_ledger import (
    VerificationEvidenceLedger,
    compute_evidence_hash,
)
from monika.application.analysis.tools.tool_guardrails import (
    ReadBeforeMutateGuard,
    ToolGuardrailController,
)


# ==============================================================================
# Phase 1: Cryptographic Evidence Hashing & Proposal Integrity
# ==============================================================================


def test_compute_evidence_hash_deterministic():
    """Verify compute_evidence_hash produces identical deterministic fingerprint."""
    h1 = compute_evidence_hash(symbol="EURUSD", entry=1.0850, stop_loss=1.0800, take_profit=1.0950, lot_size=0.50)
    h2 = compute_evidence_hash(symbol="EURUSD", entry=1.0850, stop_loss=1.0800, take_profit=1.0950, lot_size=0.50)
    assert h1 == h2
    assert len(h1) == 16


def test_verification_ledger_cryptographic_matching():
    """Verify ledger records SHA-256 hash and verifies proposal integrity against recorded evidence."""
    ledger = VerificationEvidenceLedger()
    tool_input = {"symbol": "EURUSD", "entry": 1.0850, "sl": 1.0800, "tp": 1.0950, "lots": 0.45}
    result = {"status": "ok", "lot_size": 0.45}
    record = ledger.record_tool_execution("calculate_position_size", tool_input, result)
    assert record is not None
    assert record.evidence_hash is not None

    # Matching proposal passes
    ok, reason = ledger.verify_proposal_integrity(
        symbol="EURUSD",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        lot_size=0.45,
        expected_hash=record.evidence_hash,
    )
    assert ok is True
    assert "Cryptographically verified" in reason

    # Mismatched stop loss fails
    ok_bad, reason_bad = ledger.verify_proposal_integrity(
        symbol="EURUSD",
        entry_price=1.0850,
        stop_loss=1.0600,
        take_profit=1.0950,
        lot_size=0.45,
        expected_hash=None,
    )
    assert ok_bad is False
    assert "Stop loss in proposal" in reason_bad


# ==============================================================================
# Phase 2: Read-Before-Mutate Guardrail
# ==============================================================================


def test_read_before_mutate_guard_lifecycle(tmp_path):
    """Verify ReadBeforeMutateGuard blocks mutation of unread existing files and permits after reading."""
    guard = ReadBeforeMutateGuard()

    # Create an existing file
    existing_file = tmp_path / "target.py"
    existing_file.write_text("initial_code = True", encoding="utf-8")
    existing_path = str(existing_file)

    # 1. Mutating unread existing file must be rejected
    v1 = guard.validate_mutation("edit_file", {"Path": existing_path})
    assert v1.allowed is False
    assert "READ-BEFORE-MUTATE VIOLATION" in v1.reason

    # 2. Recording observation allows subsequent mutation
    guard.record_read(existing_path)
    v2 = guard.validate_mutation("edit_file", {"Path": existing_path})
    assert v2.allowed is True

    # 3. Non-existent new file does not require prior read
    non_existent = str(tmp_path / "brand_new_file.py")
    v3 = guard.validate_mutation("write_file", {"Path": non_existent})
    assert v3.allowed is True


def test_tool_guardrail_controller_integration(tmp_path):
    """Verify ToolGuardrailController integrates ReadBeforeMutateGuard cleanly."""
    controller = ToolGuardrailController()
    existing_file = tmp_path / "module.py"
    existing_file.write_text("x = 1\n", encoding="utf-8")
    p = str(existing_file)

    # Validate before read
    v_reject = controller.validate_tool_call("edit_file", {"Path": p})
    assert v_reject.action == "reject"
    assert "READ-BEFORE-MUTATE" in v_reject.reason

    # Record read
    controller.record_tool_call("read_file", {"Path": p}, {"status": "ok"})
    controller.reset_turn()

    # Validate after read
    v_ok = controller.validate_tool_call("edit_file", {"Path": p, "content": "x = 2"})
    assert v_ok.action == "allow"


# ==============================================================================
# Phase 3: Interactive Multi-Step Planning & TODO State Machine
# ==============================================================================


def test_todo_state_machine_strict_invariants():
    """Verify single in_progress invariant and state transitions."""
    todo_state = TodoListState()

    # Initial update: 3 tasks
    raw_todos = [
        {"id": "1", "content": "Analyze requirements", "status": "pending"},
        {"id": "2", "content": "Implement changes", "status": "pending"},
        {"id": "3", "content": "Run test suite", "status": "pending"},
    ]
    ok, msg = todo_state.update_todos(raw_todos)
    assert ok is True
    assert todo_state.has_todos() is True
    assert todo_state.has_items() is True

    # Start step 1 -> valid
    ok, _ = todo_state.update_todos(
        [
            {"id": "1", "content": "Analyze requirements", "status": "in_progress"},
            {"id": "2", "content": "Implement changes", "status": "pending"},
            {"id": "3", "content": "Run test suite", "status": "pending"},
        ]
    )
    assert ok is True
    task = todo_state.get_in_progress_task()
    assert task is not None
    assert task.id == "1"

    # Attempting to have two in_progress tasks simultaneously -> rejected
    ok, err = todo_state.update_todos(
        [
            {"id": "1", "content": "Analyze requirements", "status": "in_progress"},
            {"id": "2", "content": "Implement changes", "status": "in_progress"},
            {"id": "3", "content": "Run test suite", "status": "pending"},
        ]
    )
    assert ok is False
    assert "At most one task may be 'in_progress'" in err

    # Audit completion with incomplete tasks returns False
    all_done, audit_msg = todo_state.audit_completion()
    assert all_done is False
    assert "Incomplete tasks remain" in audit_msg

    # Mark all done or cancelled
    ok, _ = todo_state.update_todos(
        [
            {"id": "1", "content": "Analyze requirements", "status": "completed"},
            {"id": "2", "content": "Implement changes", "status": "completed"},
            {"id": "3", "content": "Run test suite", "status": "cancelled"},
        ]
    )
    assert ok is True
    all_done, _ = todo_state.audit_completion()
    assert all_done is True


def test_todo_scaffold_formatting():
    """Verify markdown scaffold format for turn injection."""
    todo_state = TodoListState()
    todo_state.update_todos(
        [
            {"id": "1", "content": "Step A", "status": "completed"},
            {"id": "2", "content": "Step B", "status": "in_progress"},
            {"id": "3", "content": "Step C", "status": "pending"},
        ]
    )
    scaffold = todo_state.format_scaffold()
    assert "- [x] Step A" in scaffold
    assert "IN_PROGRESS: Step B" in scaffold
    assert "- [ ] Step C" in scaffold


# ==============================================================================
# Phase 4: Physical Deliverable Git-Porcelain Gate
# ==============================================================================


def test_git_porcelain_snapshot_and_deliverable_gate(tmp_path):
    """Verify PhysicalDeliverableGate git snapshotting and modification auditing."""
    gate = PhysicalDeliverableGate(workspace_root=str(tmp_path))
    test_file = tmp_path / "strategy.py"
    test_file.write_text("class Strategy: pass\n", encoding="utf-8")

    # Audit claiming completion on unmodified non-existent files
    fake_file = str(tmp_path / "non_existent.py")
    verdict = gate.audit_claimed_completion("Done", touched_files=[fake_file])
    assert verdict.is_valid is False
    assert "missing or empty on disk" in verdict.message

    # Audit with real existing file
    verdict_real = gate.audit_claimed_completion("Done", touched_files=[str(test_file)])
    assert verdict_real.is_valid is True


# ==============================================================================
# Phase 5: Token Economics, Pruning & Context Compaction
# ==============================================================================


def test_general_tool_pruner_targeted_truncation():
    """Verify truncate_head, truncate_tail, truncate_line, and prune_by_tool_type."""
    # 1. Truncate line
    long_line = "a" * 800
    pruned_line = truncate_line(long_line, max_chars=500)
    assert len(pruned_line) <= 550
    assert "[line truncated]" in pruned_line

    # 2. Truncate head (preserves top lines for file reads)
    head_content = "\n".join([f"line_{i}" for i in range(1, 200)])
    pruned_head = truncate_head(head_content, max_chars=500, max_lines=20)
    assert "line_1" in pruned_head
    assert "line_2" in pruned_head
    assert "remaining lines" in pruned_head

    # 3. Truncate tail (preserves bottom lines for execution logs)
    tail_content = "\n".join([f"log_entry_{i}" for i in range(1, 200)])
    pruned_tail = truncate_tail(tail_content, max_chars=500, max_lines=20)
    assert "log_entry_199" in pruned_tail
    assert "earlier lines" in pruned_tail or "omitted" in pruned_tail

    # 4. Prune by tool type
    file_pruned = GeneralToolPruner.prune_by_tool_type("read_file", head_content, max_chars=600)
    assert "line_1" in file_pruned

    bash_pruned = GeneralToolPruner.prune_by_tool_type("execute_command", tail_content, max_chars=600)
    assert "log_entry_199" in bash_pruned


def test_balanced_tool_boundary_snapping():
    """Verify is_balanced_tool_boundary prevents slicing between tool_use and tool_result."""
    messages = [
        {"role": "user", "content": "Analyze"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "get_rate"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "1.0850"}]},
        {"role": "assistant", "content": "Rate is 1.0850. Continuing."},
    ]

    # Index 2 is right after tool_use (before tool_result) -> Unbalanced!
    assert ContextCompressor.is_balanced_tool_boundary(messages, 2) is False

    # Index 3 is after tool_result -> Balanced!
    assert ContextCompressor.is_balanced_tool_boundary(messages, 3) is True


@pytest.mark.asyncio
async def test_replay_prefix_summarization():
    """Verify summarize_with_replay_prefix preserves prefix for KV-cache reuse."""
    compressor = ContextCompressor()
    mock_client = MagicMock()
    mock_resp = MagicMock(content="<compacted-summary>\n- Market regime: Trending\n</compacted-summary>")
    mock_client.generate_from_messages = AsyncMock(return_value=mock_resp)

    head = [{"role": "user", "content": "Initial prompt"}]
    middle = [
        {"role": "assistant", "content": "Exploring data"},
        {"role": "user", "content": "Tool result data"},
    ]

    summary = await compressor.summarize_with_replay_prefix(head, middle, mock_client)
    assert "<compacted-summary>" in summary
    assert "Trending" in summary
    mock_client.generate_from_messages.assert_called_once()
    payload = mock_client.generate_from_messages.call_args.kwargs.get("messages")
    # Verify replay prefix structure: initial messages preserved in order, concluding with compression prompt
    assert len(payload) == len(head) + len(middle) + 1


# ==============================================================================
# Phase 6: Agent Harness Integration (Emergency Steering, Truncation, Reminders)
# ==============================================================================


@pytest.mark.asyncio
async def test_in_flight_emergency_steering_cancellation():
    """Verify emergency steering keywords trigger in-flight turn cancellation."""
    mock_client = MagicMock()
    mock_client.provider_name = "test_provider"
    mock_client.model = "test_model"

    harness = AgentHarness(llm_client=mock_client)

    # Simulate an active turn task
    async def dummy_slow_turn():
        await asyncio.sleep(10.0)

    task = asyncio.create_task(dummy_slow_turn())
    harness._active_turn_task = task

    # Enqueue emergency steering
    harness.enqueue_steering("ESTOP: Market halt declared", sender="risk_gate", mode="immediate")

    # In-flight task must be cancelled immediately
    assert task.cancelling() or task.cancelled()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_narrative_truncation_continuation_injection():
    """Verify narrative truncation without tools triggers a continuation prompt."""
    mock_client = MagicMock()
    mock_client.provider_name = "test_provider"
    mock_client.model = "test_model"

    # Turn 1: Narrative truncated by max_tokens without tools
    resp_truncated = MagicMock(
        choices=[
            MagicMock(
                finish_reason="length",
                message=MagicMock(
                    content="Based on macroeconomic indicators such as CPI and NFP, the monetary stance",
                    tool_calls=[],
                    reasoning_content=None,
                ),
            )
        ]
    )

    # Turn 2: Recovered clean response
    resp_recovered = MagicMock(
        choices=[
            MagicMock(
                finish_reason="stop",
                message=MagicMock(
                    content="remains moderately hawkish with expectations of higher terminal rates.",
                    tool_calls=[],
                    reasoning_content=None,
                ),
            )
        ]
    )

    mock_client.run_tool_agent = AsyncMock(side_effect=[resp_truncated, resp_recovered])

    harness = AgentHarness(llm_client=mock_client)
    result = await harness.run_agent_from_messages(
        session=None,
        system_prompt="Analyze economics.",
        messages=[{"role": "user", "content": "Analyze USD"}],
        tools=[],
        stage_name="test_macro",
        max_tool_turns=4,
    )

    assert result["success"] is True
    assert result["turns"] == 2
    context = result["context_messages"]
    assert any("truncated by max_tokens" in str(m.get("content", "")) for m in context)


@pytest.mark.asyncio
async def test_dynamic_tool_stubbing_turn_6():
    """Verify heavy exploration tools have their descriptions stubbed on Turn >= 6."""
    tools = [
        {
            "name": "get_historical_candles",
            "description": "Very long multi-paragraph description explaining all 20 indicator arguments and data formats in extreme detail...",
            "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}},
        },
        {
            "name": "submit_asset_analysis",
            "description": "Final trading decision submission.",
            "input_schema": {"type": "object", "properties": {"decision": {"type": "string"}}},
        },
    ]

    called = {"get_historical_candles"}
    stubbed = AgentHarness._stub_exploration_tools(tools, called)

    # get_historical_candles should be stubbed with concise description
    candle_tool = next(t for t in stubbed if t["name"] == "get_historical_candles")
    assert "previously executed exploration tool" in candle_tool["description"]
    assert len(candle_tool["description"]) < 120

    # submit_asset_analysis must retain original description
    submit_tool = next(t for t in stubbed if t["name"] == "submit_asset_analysis")
    assert submit_tool["description"] == "Final trading decision submission."
