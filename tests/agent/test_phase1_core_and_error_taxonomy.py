# ==============================================================================
# File: tests/agent/test_phase1_core_and_error_taxonomy.py
# ==============================================================================

import asyncio
import pytest
from agent.error_classifier import FailoverReason, classify_api_error
from agent.deadline import SuspectableBackend, run_bounded_async, run_bounded_sync
from agent.bounded_response import truncate_text_middle
from agent.thinking_timeout_guidance import detect_thinking_timeout
from agent.turn_stop_gates import (
    StopGateContext,
    TradingRiskStopGate,
    CodeVerifyStopGate,
    apply_stop_gates,
)
from agent.turn_phase_machine import (
    IterationBudget,
    TurnPhaseMachine,
    TurnState,
    TurnVerdict,
)


class MockSuspectBackend:
    def __init__(self):
        self.suspect_reasons = []
        self.retired = False

    def mark_suspect(self, reason: str) -> None:
        self.suspect_reasons.append(reason)

    def is_suspect(self) -> bool:
        return len(self.suspect_reasons) > 0

    def retire_socket_safe(self) -> None:
        self.retired = True


def test_error_classifier_trading_sub_taxonomy():
    # 1. Broker disconnect
    err = classify_api_error(RuntimeError("MT5 terminal dead: socket closed by server"))
    assert err.reason == FailoverReason.BROKER_DISCONNECTED
    assert err.retryable is True

    # 2. Insufficient margin
    err_margin = classify_api_error(ValueError("Order failed: insufficient margin on account"))
    assert err_margin.reason == FailoverReason.INSUFFICIENT_MARGIN
    assert err_margin.should_quarantine_symbol is True

    # 3. Off quotes
    err_quotes = classify_api_error(Exception("Execution rejected: Off quotes from dealer"))
    assert err_quotes.reason == FailoverReason.OFF_QUOTES
    assert err_quotes.retryable is True

    # 4. Context overflow
    err_ctx = classify_api_error(Exception("Invalid request: prompt is too long, context_length_exceeded"))
    assert err_ctx.reason == FailoverReason.CONTEXT_OVERFLOW
    assert err_ctx.should_compress is True

    # 5. Rate limit 429
    class DummyHTTPError(Exception):
        status_code = 429

    err_rl = classify_api_error(DummyHTTPError("Rate limit exceeded"))
    assert err_rl.reason == FailoverReason.RATE_LIMIT
    assert err_rl.should_rotate_credential is True


@pytest.mark.asyncio
async def test_deadline_bounded_async_and_suspect():
    backend = MockSuspectBackend()

    async def slow_task():
        await asyncio.sleep(0.5)
        return "done"

    with pytest.raises(TimeoutError):
        await run_bounded_async(slow_task(), timeout_seconds=0.05, backend=backend)

    assert backend.is_suspect() is True
    assert backend.retired is True


def test_deadline_bounded_sync():
    def fast_fn(x, y):
        return x + y

    res = run_bounded_sync(fast_fn, args=(10, 20), timeout_seconds=2.0)
    assert res == 30


def test_truncate_text_middle():
    short_text = "Hello world"
    assert truncate_text_middle(short_text, max_chars=50) == short_text

    long_text = "A" * 100 + "B" * 100
    truncated = truncate_text_middle(long_text, max_chars=40)
    assert len(truncated) <= 100
    assert "omitted for brevity" in truncated
    assert truncated.startswith("A" * 20)
    assert truncated.endswith("B" * 20)


def test_thinking_timeout_guidance():
    is_timeout, guidance = detect_thinking_timeout(
        error_message="Connection reset by peer: broken pipe",
        model_name="deepseek-reasoner",
        elapsed_seconds=45.0,
    )
    assert is_timeout is True
    assert "Detected reverse-proxy idle timeout" in guidance

    # Unrelated error
    not_timeout, _ = detect_thinking_timeout("Invalid API key")
    assert not_timeout is False


def test_turn_stop_gates():
    ctx = StopGateContext(turn_id="turn-1")

    # Clean text with no trade intent
    can_stop, msg = apply_stop_gates("Here is the technical analysis overview.", ctx)
    assert can_stop is True
    assert msg is None

    # Text proposing action without registering proposal
    ctx.has_unregistered_trade_proposals = True
    can_stop_trade, msg_trade = apply_stop_gates("I recommend placing an order to buy XAUUSD.", ctx)
    assert can_stop_trade is False
    assert "Financial Safety Invariant" in msg_trade

    # File mutation without verification
    ctx.has_unregistered_trade_proposals = False
    ctx.has_unverified_file_edits = True
    ctx.mutated_files = ["main.py"]
    can_stop_code, msg_code = apply_stop_gates("I have updated the file.", ctx)
    assert can_stop_code is False
    assert "Verification Invariant" in msg_code


@pytest.mark.asyncio
async def test_turn_phase_machine_async_execution():
    call_log = []

    async def mock_prepare(state: TurnState):
        call_log.append("prepare")
        return TurnVerdict.FALLTHROUGH

    async def mock_api(state: TurnState):
        call_log.append("api")
        state.extracted_text = "All systems operational."
        return TurnVerdict.FALLTHROUGH

    machine = TurnPhaseMachine(
        budget=IterationBudget(max_iterations=5),
        prepare_handler=mock_prepare,
        api_call_handler=mock_api,
    )

    state = TurnState(turn_id="t-001", session_id="s-001", user_prompt="Status check")
    final_state = await machine.run_turn_async(state)

    assert final_state.has_final_response is True
    assert "prepare" in call_log
    assert "api" in call_log
