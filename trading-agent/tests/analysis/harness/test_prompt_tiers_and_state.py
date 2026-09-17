"""Unit tests for prompt tiers and harness state machine (Phase 4)."""

import pytest
from utils.llm.prompt_tiers import (
    PromptTier,
    TieredSystemPrompt,
    TieredPrompt,
    build_tiered_prompt,
)
from analysis.harness.harness_state import (
    PhaseAction,
    PhaseVerdict,
    HarnessState,
)


def test_prompt_tier_dataclass():
    tier = PromptTier(content="Stable identity", cache_control={"type": "ephemeral"})
    assert tier.content == "Stable identity"
    assert tier.cache_control == {"type": "ephemeral"}


def test_tiered_system_prompt_assemble_default():
    prompt = TieredSystemPrompt(
        tier1_stable="Identity rules",
        tier2_context="Skills catalog",
        tier3_volatile="Market snapshot 2026-09-07",
    )
    assembled = prompt.assemble(provider="openai")
    assert isinstance(assembled, str)
    assert "Identity rules" in assembled
    assert "Skills catalog" in assembled
    assert "Market snapshot 2026-09-07" in assembled


def test_tiered_system_prompt_assemble_anthropic():
    prompt = TieredSystemPrompt(
        tier1_stable="Identity rules",
        tier2_context="Skills catalog",
        tier3_volatile="Market snapshot",
    )
    blocks = prompt.assemble(provider="anthropic")
    assert isinstance(blocks, list)
    assert len(blocks) == 3
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in blocks[2]


def test_tiered_system_prompt_compile_tuple():
    prompt = TieredSystemPrompt(
        tier1_stable="Identity rules",
        tier2_context="Skills catalog",
        tier3_volatile="Volatile state",
    )
    prefix, suffix = prompt.compile_tuple()
    assert "Identity rules\n\nSkills catalog" == prefix
    assert "Volatile state" == suffix


def test_tiered_system_prompt_ephemeral_overlay():
    prompt = TieredSystemPrompt(tier1_stable="Identity")
    overlay = prompt.get_ephemeral_overlay({
        "budget_warning": "AI budget 85% consumed",
        "context_pressure": 90,
        "session_hint": "London open in 15m",
    })
    assert "[System: AI budget 85% consumed]" in overlay
    assert "[System: Context at 90% capacity]" in overlay
    assert "London open in 15m" in overlay


def test_harness_state_lifecycle():
    state = HarnessState(max_turns=10, stage_name="per_asset_EURUSD")
    assert not state.is_turn_limit_reached()
    assert state.can_retry_error()

    state.record_tokens(input_tokens=1000, output_tokens=200, cached_tokens=500, thinking_tokens=100)
    assert state.total_input_tokens == 1000
    assert state.total_output_tokens == 200
    assert state.total_cached_tokens == 500
    assert state.total_thinking_tokens == 100

    state.record_error()
    state.record_error()
    assert state.can_retry_error()
    state.record_error()
    assert not state.can_retry_error()

    state.reset_errors()
    assert state.can_retry_error()
    assert state.consecutive_errors == 0


def test_phase_verdict():
    verdict = PhaseVerdict(
        action=PhaseAction.CONTINUE,
        messages=[{"role": "user", "content": "hello"}],
    )
    assert verdict.action == PhaseAction.CONTINUE
    assert len(verdict.messages) == 1


def test_prepare_turn_phase():
    from analysis.harness.harness_state import prepare_turn_phase

    state = HarnessState(max_turns=3)
    msgs = [{"role": "user", "content": "hello"}]
    v1 = prepare_turn_phase(state, msgs)
    assert v1.action == PhaseAction.CONTINUE
    assert state.turn_count == 1

    state.turn_count = 3
    v2 = prepare_turn_phase(state, msgs)
    assert v2.action == PhaseAction.BREAK


def test_evaluate_response_phase_and_handle_error_phase():
    from analysis.harness.harness_state import evaluate_response_phase, handle_error_phase

    state = HarnessState()

    # Truncated response with tools
    v_trunc = evaluate_response_phase(
        state=state,
        response={"stop_reason": "length"},
        stop_reason="length",
        assistant_content=[{"type": "tool_use", "id": "t1", "name": "foo", "input": {}}],
    )
    assert v_trunc.action == PhaseAction.CONTINUE
    assert v_trunc.tool_results is not None
    assert len(v_trunc.tool_results) == 1

    # Normal successful response resets errors
    state.record_error()
    assert state.consecutive_errors == 1
    v_norm = evaluate_response_phase(
        state=state,
        response={"stop_reason": "stop"},
        stop_reason="stop",
        final_text="Analysis complete.",
    )
    assert v_norm.action == PhaseAction.CONTINUE
    assert state.consecutive_errors == 0

    # Error handling phase
    v_err = handle_error_phase(state, RuntimeError("Connection timeout"))
    assert v_err.action in (PhaseAction.RETRY, PhaseAction.ERROR)


def test_prompt_assembler_tiered_integration():
    from utils.llm.prompt_assembler import PromptAssembler
    from utils.llm.prompt_tiers import TieredSystemPrompt

    assembler = PromptAssembler()
    tiered_s1 = assembler.assemble_stage1_tiered(core_memory="Sample memory")
    assert isinstance(tiered_s1, TieredSystemPrompt)
    assert len(tiered_s1.tier1_stable) > 0
    assert len(tiered_s1.tier2_context) > 0

    blocks = tiered_s1.assemble(provider="anthropic")
    assert isinstance(blocks, list)
    assert len(blocks) >= 2


