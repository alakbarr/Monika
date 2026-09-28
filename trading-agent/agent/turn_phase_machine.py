# ==============================================================================
# File: agent/turn_phase_machine.py
# ==============================================================================

"""
Turn Phase State Machine & Iteration Budget Controller.
Decoupled turn-loop execution architecture for resilient agent operations.

Replaces monolithic nested while-loops with an explicit phase state machine:
  1. PREPARE_ITERATION: Initialize turn metrics, verify budgets, check cancel flags.
  2. ASSEMBLE_REQUEST: Compile prompt, inject cached tiers, format tool schemas.
  3. PREFLIGHT_GATE: Run token budget check, evaluate context floor and wall-clock time.
  4. API_CALL: Execute inference with streaming watchdog, handle timeouts, and manage retry state.
  5. NORMALIZE_RESPONSE: Parse multimodal tags, scrub reasoning blocks, validate JSON schemas.
  6. TOOL_ROUND / TEXT_RESPONSE: Execute tool batch (enforcing persist-before-execute) or complete turn.
  7. FINALIZE_TURN: Commit turn boundary, update usage counters, export telemetry.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from agent.turn_stop_gates import StopGateContext, apply_stop_gates

logger = logging.getLogger("TradingAgent.Agent.TurnPhaseMachine")


class TurnVerdict(str, enum.Enum):
    """Execution directives returned by each phase step."""
    CONTINUE = "continue"        # Proceed to next iteration in loop
    BREAK = "break"              # Terminate turn loop normally (e.g. final text response rendered)
    RETURN = "return"            # Immediate exit from turn handler
    FALLTHROUGH = "fallthrough"  # Proceed to subsequent phase within current iteration
    RETRY_PHASE = "retry_phase"  # Re-run current phase (e.g. after parameter ladder adjustment)


class TurnPhase(str, enum.Enum):
    """Canonical sequence of turn execution phases."""
    IDLE = "idle"
    PREPARE = "prepare_iteration"
    ASSEMBLE = "assemble_api_request"
    PREFLIGHT = "run_preflight_gate"
    API_CALL = "perform_api_call"
    NORMALIZE = "normalize_model_response"
    TOOL_ROUND = "execute_tool_round"
    FINALIZE = "finalize_turn"


@dataclass
class IterationBudget:
    """
    Manages turn iteration quota with child inheritance and programmatic refunds.
    Prevents runaway tool loops while allowing micro-tool (PTC) refunds.
    """
    max_iterations: int = 25
    current_iteration: int = 0
    refunded_iterations: int = 0
    is_exhausted: bool = False

    def can_proceed(self) -> bool:
        """Returns True if budget has remaining iterations."""
        return self.current_iteration < self.max_iterations

    def consume(self) -> int:
        """Consumes one iteration unit and increments counter."""
        if not self.can_proceed():
            self.is_exhausted = True
            raise RuntimeError(f"IterationBudget exhausted: {self.current_iteration}/{self.max_iterations}")
        self.current_iteration += 1
        return self.current_iteration

    def refund(self, count: int = 1) -> None:
        """
        Refunds iteration quota (e.g. when tool call was purely internal code execution
        or local state search that does not represent external inference progress).
        """
        refund_amount = min(count, self.current_iteration)
        self.current_iteration -= refund_amount
        self.refunded_iterations += refund_amount
        self.is_exhausted = False
        logger.debug(f"[IterationBudget] Refunded {refund_amount} iteration(s). Current: {self.current_iteration}/{self.max_iterations}")

    def derive_child(self, max_child_iterations: Optional[int] = None) -> "IterationBudget":
        """
        Derives an isolated sub-budget for a child or delegated subagent.
        The child budget cannot exceed the remaining budget of the parent.
        """
        remaining = max(1, self.max_iterations - self.current_iteration)
        allocated = min(remaining, max_child_iterations) if max_child_iterations is not None else remaining
        return IterationBudget(max_iterations=allocated)


@dataclass
class TurnState:
    """Carries mutable context and telemetry across all turn phases."""
    turn_id: str
    session_id: str
    user_prompt: str
    iteration: int = 0
    current_phase: TurnPhase = TurnPhase.IDLE
    messages: List[Dict[str, Any]] = field(default_factory=list)
    active_tools: List[Dict[str, Any]] = field(default_factory=list)
    model_response: Optional[Any] = None
    extracted_text: Optional[str] = None
    extracted_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    has_final_response: bool = False
    is_cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    phase_latencies: Dict[str, float] = field(default_factory=dict)
    stop_gate_context: StopGateContext = field(default_factory=lambda: StopGateContext(turn_id=""))

    def __post_init__(self):
        if not self.stop_gate_context.turn_id:
            self.stop_gate_context.turn_id = self.turn_id


PhaseHandler = Union[
    Callable[[TurnState], TurnVerdict],
    Callable[[TurnState], Any],  # Can return Coroutine[Any, Any, TurnVerdict]
]


class TurnPhaseMachine:
    """
    Orchestrates the lifecycle of a single or multi-turn agent interaction
    by evaluating discrete phases with invariant checks, supporting both async and sync dispatch.
    """

    def __init__(
        self,
        budget: Optional[IterationBudget] = None,
        prepare_handler: Optional[PhaseHandler] = None,
        assemble_handler: Optional[PhaseHandler] = None,
        preflight_handler: Optional[PhaseHandler] = None,
        api_call_handler: Optional[PhaseHandler] = None,
        normalize_handler: Optional[PhaseHandler] = None,
        tool_round_handler: Optional[PhaseHandler] = None,
        finalize_handler: Optional[PhaseHandler] = None,
    ):
        self.budget = budget or IterationBudget()
        self._prepare_handler = prepare_handler
        self._assemble_handler = assemble_handler
        self._preflight_handler = preflight_handler
        self._api_call_handler = api_call_handler
        self._normalize_handler = normalize_handler
        self._tool_round_handler = tool_round_handler
        self._finalize_handler = finalize_handler

    async def run_turn_async(self, state: TurnState) -> TurnState:
        """
        Asynchronously executes iterations through the phase machine until a termination
        verdict is reached or the iteration budget is exhausted.
        """
        logger.info(f"[TurnPhaseMachine] Starting async turn {state.turn_id} for session {state.session_id}")

        while self.budget.can_proceed():
            state.iteration = self.budget.consume()
            logger.debug(f"[TurnPhaseMachine] Iteration {state.iteration}/{self.budget.max_iterations}")

            # 1. Prepare Iteration
            verdict = await self._run_phase_async(TurnPhase.PREPARE, self._prepare_handler, state)
            if verdict == TurnVerdict.BREAK:
                break
            elif verdict == TurnVerdict.RETURN:
                return state

            # 2. Assemble Request
            verdict = await self._run_phase_async(TurnPhase.ASSEMBLE, self._assemble_handler, state)
            if verdict == TurnVerdict.BREAK:
                break
            elif verdict == TurnVerdict.RETURN:
                return state

            # 3. Preflight Gate
            verdict = await self._run_phase_async(TurnPhase.PREFLIGHT, self._preflight_handler, state)
            if verdict == TurnVerdict.BREAK:
                break
            elif verdict == TurnVerdict.RETURN:
                return state

            # 4. API Call
            verdict = await self._run_phase_async(TurnPhase.API_CALL, self._api_call_handler, state)
            if verdict == TurnVerdict.BREAK:
                break
            elif verdict == TurnVerdict.RETURN:
                return state
            elif verdict == TurnVerdict.RETRY_PHASE:
                continue

            # 5. Normalize Response
            verdict = await self._run_phase_async(TurnPhase.NORMALIZE, self._normalize_handler, state)
            if verdict == TurnVerdict.BREAK:
                break
            elif verdict == TurnVerdict.RETURN:
                return state

            # 6. Tool Round or Terminal Response
            if state.extracted_tool_calls:
                verdict = await self._run_phase_async(TurnPhase.TOOL_ROUND, self._tool_round_handler, state)
                if verdict == TurnVerdict.BREAK:
                    break
                elif verdict == TurnVerdict.RETURN:
                    return state
            else:
                # Evaluate stop gates before finalizing text response
                can_stop, nudge = apply_stop_gates(state.extracted_text or "", state.stop_gate_context)
                if not can_stop and nudge:
                    logger.warning(f"[TurnPhaseMachine] Stop gate prevented exit: {nudge}")
                    # Inject nudge as user/system correction and proceed to next iteration
                    state.messages.append({"role": "user", "content": f"[SYSTEM SAFETY DIRECTIVE]: {nudge}"})
                    continue

                state.has_final_response = True
                break

        # 7. Finalize Turn
        await self._run_phase_async(TurnPhase.FINALIZE, self._finalize_handler, state)
        logger.info(f"[TurnPhaseMachine] Completed async turn {state.turn_id} in {time.time() - state.start_time:.3f}s")
        return state

    def run_turn(self, state: TurnState) -> TurnState:
        """
        Synchronous execution entrypoint (delegates to async runner if inside event loop or executes sync).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.run_turn_async(state)).result()
        return asyncio.run(self.run_turn_async(state))

    async def _run_phase_async(
        self,
        phase: TurnPhase,
        handler: Optional[PhaseHandler],
        state: TurnState,
    ) -> TurnVerdict:
        """Executes a single phase asynchronously with timing and error isolation."""
        state.current_phase = phase
        t0 = time.perf_counter()

        if handler is None:
            return TurnVerdict.FALLTHROUGH

        try:
            if inspect.iscoroutinefunction(handler):
                verdict = await handler(state)
            else:
                res = handler(state)
                if inspect.iscoroutine(res):
                    verdict = await res
                else:
                    verdict = res
            return verdict or TurnVerdict.FALLTHROUGH
        except Exception as exc:
            logger.error(f"[TurnPhaseMachine] Phase {phase.value} failed with exception: {exc}", exc_info=True)
            raise
        finally:
            elapsed = time.perf_counter() - t0
            state.phase_latencies[phase.value] = state.phase_latencies.get(phase.value, 0.0) + elapsed
