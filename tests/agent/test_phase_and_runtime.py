# ==============================================================================
# File: tests/agent/test_phase_and_runtime.py
# ==============================================================================

import socket
import pytest
from agent.socket_lifecycle_guard import (
    retire_socket_ownership_safe,
    clear_socket_graveyard,
    drain_transports_after_abandonment,
)
from agent.turn_phase_machine import (
    TurnPhaseMachine,
    TurnState,
    TurnVerdict,
    TurnPhase,
    IterationBudget,
)
from agent.auxiliary_model_router import (
    AuxiliaryModelRouter,
    AuxiliaryTaskType,
    ParameterRejectionLadder,
    ReasoningFloorManager,
)
from agent.three_part_context_compressor import ThreePartContextCompressor


def test_socket_lifecycle_guard():
    # Create real socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ret = retire_socket_ownership_safe(s)
    assert ret is True

    # Test none socket
    assert retire_socket_ownership_safe(None) is False

    # Test graveyard cleanup
    cleaned = clear_socket_graveyard()
    assert cleaned >= 1


def test_iteration_budget():
    b = IterationBudget(max_iterations=5)
    assert b.can_proceed() is True
    assert b.consume() == 1
    assert b.consume() == 2

    # Refund
    b.refund(1)
    assert b.current_iteration == 1

    # Derive child budget
    child = b.derive_child(2)
    assert child.max_iterations == 2
    assert child.can_proceed() is True


def test_turn_phase_machine():
    phases_visited = []

    def prepare_h(state):
        phases_visited.append(TurnPhase.PREPARE)
        return TurnVerdict.FALLTHROUGH

    def assemble_h(state):
        phases_visited.append(TurnPhase.ASSEMBLE)
        return TurnVerdict.FALLTHROUGH

    def preflight_h(state):
        phases_visited.append(TurnPhase.PREFLIGHT)
        return TurnVerdict.FALLTHROUGH

    def api_call_h(state):
        phases_visited.append(TurnPhase.API_CALL)
        state.extracted_text = "Analysis complete."
        return TurnVerdict.FALLTHROUGH

    def normalize_h(state):
        phases_visited.append(TurnPhase.NORMALIZE)
        return TurnVerdict.FALLTHROUGH

    def finalize_h(state):
        phases_visited.append(TurnPhase.FINALIZE)
        return TurnVerdict.FALLTHROUGH

    machine = TurnPhaseMachine(
        budget=IterationBudget(max_iterations=3),
        prepare_handler=prepare_h,
        assemble_handler=assemble_h,
        preflight_handler=preflight_h,
        api_call_handler=api_call_h,
        normalize_handler=normalize_h,
        finalize_handler=finalize_h,
    )

    state = TurnState(turn_id="t1", session_id="s1", user_prompt="Analyze EURUSD")
    res = machine.run_turn(state)

    assert res.has_final_response is True
    assert TurnPhase.PREPARE in phases_visited
    assert TurnPhase.API_CALL in phases_visited
    assert TurnPhase.FINALIZE in phases_visited


def test_auxiliary_model_router():
    # Test ladder
    params = {
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.7,
        "top_p": 0.9,
        "presence_penalty": 0.5,
        "max_tokens": 100,
    }
    rung1 = ParameterRejectionLadder.apply_rung(ParameterRejectionLadder.RUNG_DROP_PENALTIES, params)
    assert "presence_penalty" not in rung1
    assert "temperature" in rung1

    rung2 = ParameterRejectionLadder.apply_rung(ParameterRejectionLadder.RUNG_DROP_TEMPERATURE, params)
    assert "temperature" not in rung2

    # Test reasoning floor
    ReasoningFloorManager.record_floored_route("openai", "o3-mini")
    assert ReasoningFloorManager.is_floored("openai", "o3-mini") is True
    adapted = ReasoningFloorManager.adapt_request("openai", "o3-mini", {"messages": []})
    assert adapted.get("reasoning_effort") == "low"

    # Test router dispatch with caller
    def mock_caller(provider, model, p):
        return "Generated Title"

    router = AuxiliaryModelRouter(default_caller=mock_caller)
    res = router.call_auxiliary(AuxiliaryTaskType.TITLE_GENERATION, [{"role": "user", "content": "test"}])
    assert res == "Generated Title"


def test_three_part_context_compressor():
    compressor = ThreePartContextCompressor(
        protect_first_n=1,
        protect_last_n=2,
        max_tool_output_chars=50,
        compression_threshold_tokens=20,
    )

    messages = [
        {"role": "system", "content": "Identity prompt"},  # Head
        {"role": "user", "content": "Old user prompt 1"},  # Middle
        {
            "role": "tool",
            "content": "A" * 200,  # Long tool output to be pruned
        },
        {"role": "assistant", "content": "Old response"},   # Middle
        {"role": "user", "content": "Recent prompt"},      # Tail
        {"role": "assistant", "content": "Recent reply"},   # Tail
    ]

    pruned, saved = compressor.prune_tool_results_determinist(messages)
    assert saved > 50
    assert "[... Deterministically pruned" in pruned[2]["content"]

    def mock_summarizer(text):
        return "Compacted history summary."

    compacted = compressor.compact(messages, summarizer_fn=mock_summarizer, force=True)
    assert len(compacted) < len(messages)
    assert compacted[0]["role"] == "system"  # Head preserved
    assert compacted[-1]["content"] == "Recent reply"  # Tail preserved
