"""
Typed state machine and phase models for autonomous agent harness loop.
Enforces loop invariants, phase actions, and structured execution lifecycle.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


from datetime import datetime, timezone


class PhaseAction(Enum):
    CONTINUE = "continue"    # Proceed to next phase or next turn
    RETRY = "retry"          # Retry current phase with backoff
    COMPACT = "compact"      # Trigger context compaction, then retry
    BREAK = "break"          # Exit loop successfully (agent completed work)
    ERROR = "error"          # Exit loop on fatal unrecoverable error


@dataclass
class SteeringMessage:
    """External steering directive or follow-up instruction injected into active harness loop."""
    content: str
    sender: str = "operator"
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    mode: str = "immediate"  # 'immediate' (drains next turn) or 'follow_up' (drains after completion)


@dataclass
class PhaseVerdict:
    """Result of executing a single turn phase in the harness loop."""
    action: PhaseAction
    messages: Optional[List[dict]] = None
    tool_results: Optional[List[dict]] = None
    response: Optional[dict] = None
    error: Optional[Exception] = None
    nudge_text: Optional[str] = None


@dataclass
class HarnessState:
    """Complete mutable state for one execution of the AgentHarness."""
    messages: List[dict] = field(default_factory=list)
    system_prompt: Any = ""
    turn_count: int = 0
    max_turns: int = 15
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_call_hashes: Set[str] = field(default_factory=set)
    cycle_id: str = ""
    stage_name: str = "unknown"
    is_paid: bool = False

    # Budget & resource tracking
    budget_remaining_usd: float = 1.0
    context_usage_pct: float = 0.0

    # Error tracking
    consecutive_errors: int = 0
    max_consecutive_errors: int = 3

    # Dual-queue steering & safety guards
    steering_queue: List[SteeringMessage] = field(default_factory=list)
    follow_up_queue: List[SteeringMessage] = field(default_factory=list)
    length_truncated: bool = False

    def enqueue_steering(self, message: SteeringMessage) -> None:
        """Enqueue an incoming steering or follow-up directive."""
        if message.mode == "follow_up":
            self.follow_up_queue.append(message)
        else:
            self.steering_queue.append(message)

    def drain_steering(self) -> List[SteeringMessage]:
        """Drain and clear all pending immediate steering messages."""
        msgs = list(self.steering_queue)
        self.steering_queue.clear()
        return msgs

    def drain_follow_up(self) -> List[SteeringMessage]:
        """Drain and clear all pending follow-up messages."""
        msgs = list(self.follow_up_queue)
        self.follow_up_queue.clear()
        return msgs

    def record_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        thinking_tokens: int = 0,
    ) -> None:
        """Accumulate token telemetry across loop turns."""
        self.total_input_tokens += max(0, input_tokens)
        self.total_output_tokens += max(0, output_tokens)
        self.total_cached_tokens += max(0, cached_tokens)
        self.total_thinking_tokens += max(0, thinking_tokens)

    def record_error(self) -> None:
        """Increment consecutive error counter."""
        self.consecutive_errors += 1

    def reset_errors(self) -> None:
        """Reset error counter on successful turn."""
        self.consecutive_errors = 0

    def can_retry_error(self) -> bool:
        """Check if consecutive error limit has not been reached."""
        return self.consecutive_errors < self.max_consecutive_errors

    def is_turn_limit_reached(self) -> bool:
        """Check if max allowed turns have been consumed."""
        return self.turn_count >= self.max_turns


def prepare_turn_phase(state: HarnessState, current_messages: List[dict]) -> PhaseVerdict:
    """Pre-LLM phase: Validate turn bounds and enforce role alternation."""
    if state.is_turn_limit_reached():
        return PhaseVerdict(
            action=PhaseAction.BREAK,
            nudge_text="Maximum allowed turns reached.",
        )

    state.turn_count += 1
    from analysis.harness.agent_harness import AgentHarness
    role_safe = AgentHarness._enforce_role_alternation(current_messages)
    return PhaseVerdict(
        action=PhaseAction.CONTINUE,
        messages=role_safe,
    )


def evaluate_response_phase(
    state: HarnessState,
    response: Any,
    stop_reason: str = "",
    assistant_content: Optional[list] = None,
    final_text: str = "",
    reasoning_content: Optional[str] = None,
) -> PhaseVerdict:
    """Post-LLM phase: Check truncation, safety refusals, and response quality."""
    from analysis.harness.agent_harness import AgentHarness
    from analysis.harness.error_classifier import ErrorClassifier, RecoveryAction

    # 1. Truncation guard
    if AgentHarness._check_truncation(response, stop_reason):
        tool_blocks = [
            b for b in (assistant_content or [])
            if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
        ]
        if tool_blocks:
            tool_results = AgentHarness._fail_truncated_tool_calls(tool_blocks)
            return PhaseVerdict(
                action=PhaseAction.CONTINUE,
                tool_results=tool_results,
                nudge_text="Truncated response with tool calls blocked.",
            )

    # 2. Structured response classification
    resp_dict = {
        "stop_reason": stop_reason,
        "content": final_text,
        "tool_calls": [
            b for b in (assistant_content or [])
            if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
        ],
        "reasoning": reasoning_content or "",
    }
    issue = ErrorClassifier.classify_response(resp_dict)
    if issue:
        if issue.recovery in (RecoveryAction.INJECT_NUDGE, RecoveryAction.INJECT_CONTINUATION):
            return PhaseVerdict(
                action=PhaseAction.CONTINUE,
                nudge_text=issue.nudge_text or "[System: Please proceed.]",
            )
        elif issue.recovery == RecoveryAction.RETRY_WITH_REDUCED_EFFORT:
            return PhaseVerdict(
                action=PhaseAction.RETRY,
                nudge_text="[System: Thinking budget exhausted without answer. Conclude directly.]",
            )

    state.reset_errors()
    return PhaseVerdict(action=PhaseAction.CONTINUE)


def handle_error_phase(state: HarnessState, exc: Exception) -> PhaseVerdict:
    """Error handling phase: Classify exception and assign recovery verdict."""
    from analysis.harness.error_classifier import ErrorClassifier, RecoveryAction

    state.record_error()
    classified = ErrorClassifier.classify(exc)

    if classified.recovery == RecoveryAction.RETRY_WITH_COMPACTION:
        return PhaseVerdict(
            action=PhaseAction.COMPACT,
            error=exc,
            nudge_text=classified.message,
        )

    if classified.recovery in (RecoveryAction.RETRY_SAME, RecoveryAction.ROTATE_CREDENTIAL) and state.can_retry_error():
        return PhaseVerdict(
            action=PhaseAction.RETRY,
            error=exc,
            nudge_text=classified.message,
        )

    return PhaseVerdict(
        action=PhaseAction.ERROR,
        error=exc,
        nudge_text=classified.message,
    )

