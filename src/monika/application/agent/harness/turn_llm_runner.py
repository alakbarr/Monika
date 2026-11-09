"""
File: src/monika/application/agent/harness/turn_llm_runner.py

Orchestrates a single turn's LLM invocation within the AgentHarness ReAct loop.
Handles:
1. Pre/post LLM plugin hooks and OpenTelemetry tracing spans.
2. Role alternation enforcement and message history integrity repair.
3. Copy-on-write message protection against provider mutations.
4. Surface Node 0 invariant prompt cache assembly, volatile overlay injection, and active TODO scaffold.
5. Watchdog-bounded async inference execution with deadlock and hang protection.
6. Structured error classification, credential rotation, retry backoff, and fallback model swapping.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from monika.application.agent.deadline import run_bounded_async
from monika.application.agent.harness.error_classifier import (
    ErrorClassifier,
    RecoveryAction,
)
from monika.application.agent.harness.message_repair import (
    repair_message_history,
    transform_messages_for_target_model,
)
from monika.application.agent.turn_liveness import TurnLivenessWatchdog
from monika.application.agent.turn_phase_machine import TurnPhase, TurnState
from monika.application.plugins.manager.manager import PluginHook, get_plugin_manager
from monika.core.telemetry.tracing.spans import llm_span
from monika.infrastructure.providers.base_provider import _flatten_system_prompt

logger = logging.getLogger("TradingAgent.AgentHarness.TurnLLMRunner")


@dataclass
class LLMTurnExecutionResult:
    """Outcome of one turn LLM invocation."""

    response: Optional[Any]
    current_messages: List[dict]
    last_exc: Optional[Exception]
    fallback_swapped: bool = False
    stop_iteration: bool = False
    terminated_early: bool = False
    early_return_payload: Optional[dict] = None
    pre_turn_checkpoint: Optional[List[dict]] = None
    active_llm_span: Optional[Any] = None


class TurnLLMRunner:
    """Encapsulates LLM invocation, retry ladders, prompt assembly, and fallback swapping."""

    @staticmethod
    async def execute_turn_llm(
        harness: Any,
        session: Any,
        current_messages: List[dict],
        effective_tools: List[dict],
        system_prompt: Any,
        stage_name: str,
        turns: int,
        effective_max_turns: int,
        turn_timeout: float,
        turn_state: TurnState,
        context_win: int,
        tool_calls_made: int,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cached_tokens: int,
        total_thinking_tokens: int,
        is_paid: bool,
        length_truncated: bool,
        emergency_recovery_turns_used: int,
        overflow_recovery_attempted: bool,
    ) -> LLMTurnExecutionResult:
        plugin_mgr = get_plugin_manager()
        await plugin_mgr.emit(
            PluginHook.PRE_LLM_CALL,
            stage_name=stage_name,
            turn=turns,
            messages=current_messages,
            tools=effective_tools,
        )

        provider_name = getattr(harness.llm_client, "provider_name", "unknown")
        model_name = getattr(harness.llm_client, "model", "unknown")
        task_role = getattr(harness.llm_client, "role", stage_name)

        response = None
        last_exc: Optional[Exception] = None
        max_attempts = 3
        pre_turn_checkpoint = [dict(m) for m in current_messages]
        current_overflow_attempted = overflow_recovery_attempted

        with llm_span(provider=provider_name, model=model_name, task_role=task_role) as active_span:
            for attempt in range(max_attempts):
                try:
                    # ── C4: ROLE ALTERNATION ENFORCEMENT & INTEGRITY REPAIR ──
                    role_safe_messages = harness._enforce_role_alternation(current_messages)
                    try:
                        role_safe_messages = repair_message_history(role_safe_messages)
                    except Exception as e:
                        logger.debug(f"Message repair skipped: {e}")

                    # ── C3: COPY-ON-WRITE MESSAGE PROTECTION ──
                    send_messages = []
                    for msg in role_safe_messages:
                        cloned = {}
                        for k, v in msg.items():
                            if k == "content" and isinstance(v, (list, dict)):
                                cloned[k] = copy.deepcopy(v)
                            else:
                                cloned[k] = v
                        send_messages.append(cloned)

                    # ── Prompt Cache Invariance Hardening (Surface Node 0) ──
                    assemble_fn = getattr(system_prompt, "assemble", None)

                    if callable(assemble_fn):
                        try:
                            current_static_sys = assemble_fn(provider=provider_name, quarantine_volatile=True)
                        except TypeError:
                            current_static_sys = assemble_fn(provider=provider_name)
                        dynamic_sys = str(getattr(system_prompt, "tier3_volatile", "") or "").strip()
                    elif isinstance(system_prompt, tuple) and len(system_prompt) >= 2:
                        current_static_sys = system_prompt[0]
                        dynamic_sys = str(system_prompt[1] or "").strip()
                    else:
                        current_static_sys = system_prompt
                        dynamic_sys = ""

                    if isinstance(current_static_sys, list):
                        flat_static = json.dumps(current_static_sys, sort_keys=True)
                    else:
                        flat_static = _flatten_system_prompt(current_static_sys).strip()
                    static_hash = hashlib.sha256(flat_static.encode("utf-8")).hexdigest()

                    # 1.1: Surface Node 0 is immutable for the lifetime of this harness session
                    if harness._cached_surface_prompt is None:
                        harness._cached_surface_prompt = current_static_sys
                        harness._cached_surface_prompt_hash = static_hash
                        effective_sys = current_static_sys
                    else:
                        effective_sys = harness._cached_surface_prompt
                        # 1.6: In-history system prompt updates (Append, Don't Replace)
                        if static_hash != harness._cached_surface_prompt_hash:
                            update_notice = f"[SYSTEM INSTRUCTION UPDATE]:\n{flat_static}"
                            if send_messages and send_messages[-1].get("role") == "user":
                                prev_c = send_messages[-1].get("content")
                                if isinstance(prev_c, str):
                                    send_messages[-1]["content"] = f"{prev_c}\n\n{update_notice}"
                                elif isinstance(prev_c, list):
                                    send_messages[-1]["content"].append(
                                        {"type": "text", "text": f"\n\n{update_notice}"}
                                    )
                            else:
                                send_messages.append({"role": "user", "content": update_notice})
                            logger.info(
                                f"[{stage_name}][AgentHarness] System prompt update appended in-history (token 0 prefix preserved)."
                            )

                    # 1.3: Dynamic context isolation: inject into user message tail, never system prompt
                    if hasattr(harness, "runtime_context_projection") and harness.runtime_context_projection:
                        proj = harness.runtime_context_projection.project({"volatile": dynamic_sys or ""})
                        volatile_changed = proj is not None or dynamic_sys != harness._last_injected_dynamic_overlay
                    else:
                        volatile_changed = dynamic_sys != harness._last_injected_dynamic_overlay

                    if dynamic_sys and volatile_changed:
                        harness._last_injected_dynamic_overlay = dynamic_sys
                        snapshot_text = f"<volatile_overlay>\n{dynamic_sys}\n</volatile_overlay>"
                        if (
                            turns == 1
                            and send_messages
                            and send_messages[0].get("role") == "user"
                            and "<volatile_overlay>" not in str(send_messages[0].get("content", ""))
                        ):
                            prev_c = send_messages[0].get("content")
                            send_messages[0] = dict(send_messages[0])
                            if isinstance(prev_c, str):
                                send_messages[0]["content"] = f"{prev_c}\n\n{snapshot_text}"
                            elif isinstance(prev_c, list):
                                send_messages[0]["content"] = list(prev_c) + [
                                    {"type": "text", "text": f"\n\n{snapshot_text}"}
                                ]
                            # Surface Node 0 invariant: keep current_messages[0] in sync without in-place mutation of caller's dict
                            if current_messages and current_messages[0].get("role") == "user":
                                current_messages[0] = dict(current_messages[0])
                                current_messages[0]["content"] = send_messages[0]["content"]
                        else:
                            last_user_idx = None
                            for i in range(len(send_messages) - 1, -1, -1):
                                if send_messages[i].get("role") == "user":
                                    last_user_idx = i
                                    break
                            if last_user_idx is not None and (turns == 1 or last_user_idx != 0):
                                send_messages[last_user_idx] = dict(send_messages[last_user_idx])
                                prev_c = send_messages[last_user_idx].get("content")
                                if isinstance(prev_c, str) and "<volatile_overlay>" not in prev_c:
                                    send_messages[last_user_idx]["content"] = f"{prev_c}\n\n{snapshot_text}"
                                elif isinstance(prev_c, list):
                                    has_snapshot = any(
                                        "<volatile_overlay>" in str(b.get("text", ""))
                                        for b in prev_c
                                        if isinstance(b, dict)
                                    )
                                    if not has_snapshot:
                                        send_messages[last_user_idx]["content"] = list(prev_c) + [
                                            {"type": "text", "text": f"\n\n{snapshot_text}"}
                                        ]
                            else:
                                send_messages.append({"role": "user", "content": snapshot_text})

                    # 1.4: Active TODO list scaffold injection into latest user message
                    if hasattr(harness, "todo_state") and harness.todo_state and harness.todo_state.has_items():
                        todo_scaffold = harness.todo_state.format_scaffold()
                        if todo_scaffold:
                            todo_block = f"<active_todos>\n{todo_scaffold}\n</active_todos>"
                            last_user_idx = None
                            for i in range(len(send_messages) - 1, -1, -1):
                                if send_messages[i].get("role") == "user":
                                    last_user_idx = i
                                    break
                            if last_user_idx is not None:
                                send_messages[last_user_idx] = dict(send_messages[last_user_idx])
                                prev_c = send_messages[last_user_idx].get("content")
                                if isinstance(prev_c, str) and "<active_todos>" not in prev_c:
                                    send_messages[last_user_idx]["content"] = f"{prev_c}\n\n{todo_block}"
                                elif isinstance(prev_c, list):
                                    if not any(
                                        "<active_todos>" in str(b.get("text", ""))
                                        for b in prev_c
                                        if isinstance(b, dict)
                                    ):
                                        send_messages[last_user_idx]["content"] = list(prev_c) + [
                                            {"type": "text", "text": f"\n\n{todo_block}"}
                                        ]

                    turn_state.current_phase = TurnPhase.API_CALL
                    t_api_start = asyncio.get_event_loop().time()
                    _watchdog_ref: Optional[TurnLivenessWatchdog] = None

                    effective_tool_choice = getattr(harness, "_next_turn_tool_choice", None)
                    if effective_tool_choice is not None:
                        harness._next_turn_tool_choice = None
                    elif turns >= effective_max_turns:
                        m_tool = (
                            harness.get_mandatory_tool_for_stage(stage_name)
                            if hasattr(harness, "get_mandatory_tool_for_stage")
                            else None
                        )
                        called_t = set()
                        if hasattr(harness, "tracking") and hasattr(harness.tracking, "called_tools"):
                            called_t = harness.tracking.called_tools
                        elif hasattr(harness, "called_tools"):
                            called_t = harness.called_tools
                        if m_tool and m_tool not in called_t:
                            has_m_tool = any(
                                (t.get("name") if isinstance(t, dict) else getattr(t, "name", None)) == m_tool
                                for t in effective_tools
                            )
                            if has_m_tool:
                                effective_tool_choice = {"type": "function", "function": {"name": m_tool}}

                    try:
                        async with TurnLivenessWatchdog(
                            turn_id=f"{stage_name}_{turns}",
                            timeout_seconds=turn_timeout,
                            stall_timeout_seconds=min(180.0, max(30.0, turn_timeout * 0.65)),
                            abort_on_hang=True,
                        ) as watchdog:
                            _watchdog_ref = watchdog
                            # Dual-Layer Adaptive Thinking: resolve cognitive budget for this turn phase
                            try:
                                from monika.infrastructure.llm.adaptive_thinking import resolve_turn_thinking_budget

                                called_set = set()
                                if hasattr(harness, "tracking") and hasattr(harness.tracking, "called_tools"):
                                    called_set = set(harness.tracking.called_tools)
                                elif hasattr(harness, "called_tools"):
                                    called_set = set(harness.called_tools)

                                turn_thinking_budget = resolve_turn_thinking_budget(
                                    turn=turns,
                                    called_tools=called_set,
                                    base_thinking=getattr(harness.llm_client, "thinking_level", None),
                                    is_agentic=True,
                                )
                                if hasattr(harness.llm_client, "thinking_budget"):
                                    harness.llm_client.thinking_budget = turn_thinking_budget
                                if hasattr(harness.llm_client, "kwargs") and isinstance(
                                    harness.llm_client.kwargs, dict
                                ):
                                    harness.llm_client.kwargs["thinking_budget"] = turn_thinking_budget
                                    harness.llm_client.kwargs["reasoning_effort"] = (
                                        "low"
                                        if turn_thinking_budget <= 1536
                                        else ("medium" if turn_thinking_budget <= 6144 else "high")
                                    )
                            except Exception as th_err:
                                logger.debug(f"[{stage_name}] Turn thinking budget calculation non-fatal: {th_err}")

                            try:
                                api_call = harness.llm_client.run_tool_agent(
                                    send_messages, effective_tools, effective_sys, tool_choice=effective_tool_choice
                                )
                            except TypeError:
                                api_call = harness.llm_client.run_tool_agent(
                                    send_messages, effective_tools, effective_sys
                                )
                            api_coro = run_bounded_async(
                                api_call,
                                timeout_seconds=turn_timeout,
                                timeout_message=f"Turn {turns} LLM call timed out after {turn_timeout:.0f}s",
                            )
                            harness._active_turn_task = asyncio.create_task(api_coro)
                            watchdog.set_task_to_cancel(harness._active_turn_task)
                            try:
                                response = await harness._active_turn_task
                            finally:
                                harness._active_turn_task = None
                            watchdog.record_activity("api_response_received")
                    except (asyncio.TimeoutError, TimeoutError) as to_err:
                        raise TimeoutError(f"Turn {turns} LLM call timed out after {turn_timeout:.0f}s") from to_err
                    except asyncio.CancelledError as cancel_err:
                        if _watchdog_ref is not None and _watchdog_ref.hang_detected:
                            raise TimeoutError(
                                f"Turn {turns} deadlocked and was aborted by TurnLivenessWatchdog after {turn_timeout:.0f}s"
                            ) from cancel_err
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Active LLM call cancelled on turn {turns} (in-flight steering or abort)."
                        )
                        raise
                    finally:
                        turn_state.phase_latencies[f"api_call_turn_{turns}"] = (
                            asyncio.get_event_loop().time() - t_api_start
                        )
                    break
                except StopIteration as stop_iter_exc:
                    last_exc = stop_iter_exc
                    break
                except Exception as exc:
                    if emergency_recovery_turns_used > 0 and "StopIteration" in str(exc):
                        last_exc = exc
                        break
                    last_exc = exc

                    # ── Structured Error Recovery Pipeline (Phase 3) ──
                    classified = ErrorClassifier.classify(exc)

                    await plugin_mgr.emit(
                        PluginHook.ON_LLM_ERROR,
                        stage_name=stage_name,
                        turn=turns,
                        error=exc,
                        classified=classified,
                    )

                    if classified.recovery == RecoveryAction.RETRY_WITH_COMPACTION and not current_overflow_attempted:
                        current_overflow_attempted = True
                        logger.warning(
                            f"[{stage_name}][AgentHarness] {classified.message} "
                            f"Running emergency compaction and retrying turn {turns}..."
                        )
                        if current_messages and current_messages[-1].get("role") == "assistant":
                            current_messages.pop()

                        current_messages = harness.compactor.emergency_compact(
                            current_messages,
                            context_window=context_win,
                            target_reduction=0.50,
                        )
                        continue

                    if classified.recovery == RecoveryAction.ROTATE_CREDENTIAL:
                        logger.warning(f"[{stage_name}][AgentHarness] Rate limit encountered: {classified.message}")
                        if hasattr(harness.llm_client, "rotate_key"):
                            harness.llm_client.rotate_key()
                        elif hasattr(harness.llm_client, "_rotate_key"):
                            harness.llm_client._rotate_key()
                        if attempt < max_attempts - 1:
                            raw_backoff = (
                                min(classified.retry_delay, 5.0) if classified.retry_delay > 0 else (2.0 * (2**attempt))
                            )
                            backoff = raw_backoff * (1.0 - random.random() * 0.1)
                            await asyncio.sleep(backoff)
                            continue

                    is_timeout_err = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                    max_retry_attempts = 2 if is_timeout_err else max_attempts
                    if (
                        classified.recovery == RecoveryAction.RETRY_SAME or harness._is_transient_error(exc)
                    ) and attempt < max_retry_attempts - 1:
                        raw_backoff = classified.retry_delay if classified.retry_delay > 0 else (2.0 * (2**attempt))
                        backoff = raw_backoff * (1.0 - random.random() * 0.1)
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Retryable error on turn {turns} "
                            f"(attempt {attempt + 1}/{max_retry_attempts}): {exc}. Retrying in {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        break

            await plugin_mgr.emit(
                PluginHook.POST_LLM_CALL,
                stage_name=stage_name,
                turn=turns,
                response=response,
                error=last_exc if response is None else None,
            )

            if response is None:
                if emergency_recovery_turns_used > 0 and (
                    isinstance(last_exc, StopIteration) or "StopIteration" in str(last_exc)
                ):
                    return LLMTurnExecutionResult(
                        response=None,
                        current_messages=pre_turn_checkpoint,
                        last_exc=last_exc,
                        stop_iteration=True,
                        pre_turn_checkpoint=pre_turn_checkpoint,
                        active_llm_span=active_span,
                    )

                if harness._try_fallback_swap(stage_name, last_exc):
                    tgt_prov = harness._detect_client_provider()
                    tgt_model = getattr(harness.llm_client, "model", "")
                    current_messages = transform_messages_for_target_model(
                        current_messages,
                        target_provider=tgt_prov,
                        target_model=tgt_model,
                    )
                    return LLMTurnExecutionResult(
                        response=None,
                        current_messages=current_messages,
                        last_exc=last_exc,
                        fallback_swapped=True,
                        pre_turn_checkpoint=pre_turn_checkpoint,
                        active_llm_span=active_span,
                    )

                is_billing = harness._is_billing_error(last_exc)
                logger.error(
                    f"[{stage_name}][AgentHarness] Provider error on turn {turns}: {last_exc} (is_billing={is_billing})"
                )
                if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(
                    harness.llm_client, "_save_token_usage"
                ):
                    try:
                        await harness.llm_client._save_token_usage(
                            model_name=getattr(harness.llm_client, "model", "unknown"),
                            task_name=stage_name,
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens,
                            session=session,
                            task_role=task_role,
                            cached_tokens=total_cached_tokens,
                            thinking_tokens=total_thinking_tokens,
                            is_direct_free_tier=False if is_paid else None,
                            from_agent_harness=True,
                        )
                    except Exception:
                        pass
                # Prevent negative prompt caching blackhole: rollback message state to pre-turn checkpoint
                current_messages = pre_turn_checkpoint
                reporting_messages = [dict(m) for m in current_messages]
                if reporting_messages and reporting_messages[-1].get("role") == "user":
                    reporting_messages.append(
                        {
                            "role": "assistant",
                            "content": "[Analysis turn terminated prematurely due to provider error. State preserved.]",
                        }
                    )
                early_payload = {
                    "success": False,
                    "error": str(last_exc),
                    "is_billing_error": is_billing,
                    "tool_calls_made": tool_calls_made,
                    "turns": turns,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "thinking_tokens": total_thinking_tokens,
                    "cached_tokens": total_cached_tokens,
                    "context_messages": reporting_messages,
                    "is_paid": is_paid,
                    "length_truncated": length_truncated,
                }
                return LLMTurnExecutionResult(
                    response=None,
                    current_messages=current_messages,
                    last_exc=last_exc,
                    terminated_early=True,
                    early_return_payload=early_payload,
                    pre_turn_checkpoint=pre_turn_checkpoint,
                    active_llm_span=active_span,
                )

            return LLMTurnExecutionResult(
                response=response,
                current_messages=current_messages,
                last_exc=last_exc,
                pre_turn_checkpoint=pre_turn_checkpoint,
                active_llm_span=active_span,
            )
