"""Ordered concurrency pool and tool call recovery for tool execution.

Provides the 3-stage ordered concurrency pool and 3-layer ToolCallRecovery:
- Stage 1: Serial preparation in model emission order.
- Stage 2: Concurrency-bounded execution (parallel-safe) or exclusive serial barriers.
- Stage 3: Contiguous Head-of-Line commit order for deterministic replay.
- Missing result synthesis for aborted/unstarted/unresolved tool calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
import inspect
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class PlannedToolCall:
    """A planned tool call emitted by the assistant."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    is_concurrency_safe: bool = False


@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    """Outcome of a tool execution ready for the session surface."""

    call_id: str
    name: str
    content: str
    is_error: bool = False
    error_code: str | None = None
    additional_contexts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _PendingCallState:
    call_id: str
    name: str
    arguments: dict[str, Any]
    dispatched: bool = False
    completed: bool = False


class ToolCallRecovery:
    """Tracks tool call dispatch lifecycle and synthesizes results for dangling calls."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingCallState] = {}

    def register_assistant_tool_calls(
        self,
        calls: Sequence[PlannedToolCall] | Sequence[dict[str, Any]],
    ) -> None:
        for call in calls:
            call_id: str
            name: str
            arguments: dict[str, Any]

            if isinstance(call, PlannedToolCall):
                call_id = call.call_id
                name = call.name
                arguments = dict(call.arguments)
            elif isinstance(call, dict):
                call_id = str(call.get("id") or call.get("call_id") or "")
                fn_obj = call.get("function")
                if isinstance(fn_obj, dict):
                    name = str(fn_obj.get("name") or "")
                    args_val = fn_obj.get("arguments")
                    if isinstance(args_val, str):
                        try:
                            parsed = json.loads(args_val)
                            arguments = dict(parsed) if isinstance(parsed, dict) else {"raw": args_val}
                        except Exception:
                            arguments = {"raw": args_val}
                    elif isinstance(args_val, dict):
                        arguments = dict(args_val)
                    else:
                        arguments = {}
                else:
                    name = str(call.get("name") or "")
                    raw_args = call.get("arguments")
                    arguments = dict(raw_args) if isinstance(raw_args, dict) else {}
            else:
                continue

            if call_id:
                self._pending[call_id] = _PendingCallState(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                    dispatched=False,
                    completed=False,
                )

    def mark_dispatched(self, call_id: str) -> None:
        if call_id in self._pending:
            self._pending[call_id].dispatched = True

    def mark_completed(self, call_id: str) -> None:
        if call_id in self._pending:
            self._pending[call_id].completed = True

    def synthesize_missing_results(self, aborted: bool = False) -> list[ToolCallOutcome]:
        synthesized: list[ToolCallOutcome] = []
        for state in self._pending.values():
            if state.completed:
                continue

            if state.dispatched:
                synthesized.append(
                    ToolCallOutcome(
                        call_id=state.call_id,
                        name=state.name,
                        content=(
                            "The tool call was dispatched, but the step ended before its result was recorded. "
                            "Check whether the effect already occurred; retry only if the operation is read-only or idempotent."
                        ),
                        is_error=True,
                        error_code="TOOL_OUTCOME_UNKNOWN",
                    )
                )
            elif aborted:
                synthesized.append(
                    ToolCallOutcome(
                        call_id=state.call_id,
                        name=state.name,
                        content="The tool call was aborted before dispatch.",
                        is_error=True,
                        error_code="ABORTED_BEFORE_DISPATCH",
                    )
                )
            else:
                synthesized.append(
                    ToolCallOutcome(
                        call_id=state.call_id,
                        name=state.name,
                        content="The step ended before this tool call was dispatched; the tool did not run.",
                        is_error=True,
                        error_code="TOOL_NOT_STARTED",
                    )
                )
            state.completed = True

        return synthesized


class OrderedToolScheduler:
    """Coordinates tool execution with ordered preparation, bounded concurrency, and Head-of-Line commits."""

    def __init__(self, max_parallel_tool_calls: int = 10) -> None:
        self.max_parallel_tool_calls = max_parallel_tool_calls

    async def execute_batch(
        self,
        calls: Sequence[PlannedToolCall],
        prepare_fn: Callable[[PlannedToolCall], Awaitable[None] | None] | None = None,
        execute_fn: Callable[[PlannedToolCall], Awaitable[ToolCallOutcome]] | None = None,
        commit_fn: Callable[[ToolCallOutcome], Awaitable[None] | None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> list[ToolCallOutcome]:
        if execute_fn is None:
            raise ValueError("execute_fn must be provided to execute_batch.")

        if not calls:
            return []

        # Partition into contiguous parallel-safe groups vs serial barrier calls
        groups: list[list[PlannedToolCall]] = []
        current_group: list[PlannedToolCall] = []
        current_is_safe: bool | None = None

        for call in calls:
            if current_is_safe is None:
                current_is_safe = call.is_concurrency_safe
                current_group.append(call)
            elif call.is_concurrency_safe == current_is_safe and current_is_safe is True:
                current_group.append(call)
            else:
                groups.append(current_group)
                current_group = [call]
                current_is_safe = call.is_concurrency_safe

        if current_group:
            groups.append(current_group)

        all_outcomes: list[ToolCallOutcome] = []

        for group in groups:
            if cancel_event is not None and cancel_event.is_set():
                for call in group:
                    cancelled_outcome = ToolCallOutcome(
                        call_id=call.call_id,
                        name=call.name,
                        content="Tool execution cancelled before run.",
                        is_error=True,
                        error_code="CANCELLED",
                    )
                    all_outcomes.append(cancelled_outcome)
                continue

            # Stage 1: Serial preparation in model emission order
            if prepare_fn is not None:
                for call in group:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    res = prepare_fn(call)
                    if inspect.isawaitable(res):
                        await res

            is_parallel = group[0].is_concurrency_safe

            if is_parallel and len(group) > 1:
                # Stage 2: Concurrently bounded execution
                sem = asyncio.Semaphore(self.max_parallel_tool_calls)
                slots: list[ToolCallOutcome | None] = [None] * len(group)
                slot_ready_events = [asyncio.Event() for _ in group]

                async def worker(idx: int, call: PlannedToolCall) -> None:
                    async with sem:
                        if cancel_event is not None and cancel_event.is_set():
                            slots[idx] = ToolCallOutcome(
                                call_id=call.call_id,
                                name=call.name,
                                content="Tool execution cancelled.",
                                is_error=True,
                                error_code="CANCELLED",
                            )
                            slot_ready_events[idx].set()
                            return
                        try:
                            outcome = await execute_fn(call)
                        except Exception as exc:
                            outcome = ToolCallOutcome(
                                call_id=call.call_id,
                                name=call.name,
                                content=f"Tool execution raised unhandled exception: {exc}",
                                is_error=True,
                                error_code="EXECUTION_EXCEPTION",
                            )
                        slots[idx] = outcome
                        slot_ready_events[idx].set()

                tasks = [asyncio.create_task(worker(i, c)) for i, c in enumerate(group)]

                # Stage 3: Contiguous Head-of-Line commit order
                for idx in range(len(group)):
                    await slot_ready_events[idx].wait()
                    outcome = slots[idx]
                    if outcome is None:
                        outcome = ToolCallOutcome(
                            call_id=group[idx].call_id,
                            name=group[idx].name,
                            content="Slot outcome was missing.",
                            is_error=True,
                            error_code="INTERNAL_ERROR",
                        )
                    if commit_fn is not None:
                        res = commit_fn(outcome)
                        if inspect.isawaitable(res):
                            await res
                    all_outcomes.append(outcome)

                await asyncio.gather(*tasks)
            else:
                # Serial execution for barrier calls or singletons
                for call in group:
                    if cancel_event is not None and cancel_event.is_set():
                        outcome = ToolCallOutcome(
                            call_id=call.call_id,
                            name=call.name,
                            content="Tool execution cancelled.",
                            is_error=True,
                            error_code="CANCELLED",
                        )
                    else:
                        try:
                            outcome = await execute_fn(call)
                        except Exception as exc:
                            outcome = ToolCallOutcome(
                                call_id=call.call_id,
                                name=call.name,
                                content=f"Tool execution raised unhandled exception: {exc}",
                                is_error=True,
                                error_code="EXECUTION_EXCEPTION",
                            )

                    if commit_fn is not None:
                        res = commit_fn(outcome)
                        if inspect.isawaitable(res):
                            await res
                    all_outcomes.append(outcome)

        return all_outcomes
