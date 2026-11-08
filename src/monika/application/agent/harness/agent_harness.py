"""
File: src/monika/application/agent/harness/agent_harness.py

Unified Multi-Turn ReAct Agent Harness.
Standardizes and centralizes:
1. Turn & conversation state management across all LLM providers.
2. Context compaction, observation masking, and token truncation guardrails.
3. State preservation (anti-hallucination) on conversation context trimming.
4. Anti-oscillation tool hashing (detects and suppresses identical tool calls).
5. Tool family quota enforcement.
6. Dynamic tool routing and execution via ToolExecutor.
7. Mandatory tool nudging (e.g. submit_asset_analysis, submit_fundamental_brief).
8. Audit trail logging to ActivityLog.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import random
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, cast

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.agent.auxiliary_model_router import AuxiliaryModelRouter, AuxiliaryTaskType
from monika.application.agent.bounded_response import truncate_text_middle
from monika.application.agent.deadline import run_bounded_async
from monika.application.agent.empty_response_guard import EmptyResponseGuard
from monika.application.agent.harness.fs_observation_policy import ObservedStateGate
from monika.application.agent.harness.repeat_tool_guard import RepeatToolGuard
from monika.application.agent.harness.session_surface import (
    RuntimeContextProjection,
    SessionSurface,
    ThrottledTimeContext,
)
from monika.application.agent.harness.tool_batch_planner import ToolBatchPlanner
from monika.application.agent.harness.tool_scheduler import ToolCallRecovery
from monika.application.agent.harness.tool_repair import (
    coerce_tool_arguments,
    compute_canonical_tool_signature,
    deep_repair_tool_arguments,
    repair_tool_arguments,
    repair_tool_name,
)
from monika.application.agent.readonly_replay_cache import ReadOnlyReplayCache
from monika.application.agent.scratchpad_guard import (
    close_dangling_scratchpad,
    extract_reasoning_and_content,
    scratchpad_guard,
)
from monika.application.agent.socket_lifecycle_guard import clear_socket_graveyard, socket_guard
from monika.application.agent.turn_liveness import TurnLivenessWatchdog
from monika.application.agent.turn_phase_machine import TurnPhase, TurnPhaseMachine, TurnState, TurnVerdict
from monika.application.agent.turn_preflight_gate import (
    RUN_BUDGET_WRAPUP_NOTICE,
    TurnPreflightGate,
    WallClockBudgetManager,
)
from monika.application.agent.turn_stop_gates import StopGateContext, apply_stop_gates
from monika.application.agent.turn_tool_round import ToolCallSpec, ToolRoundVerdict, TurnToolRoundCoordinator
from monika.application.agent.harness.turn_llm_runner import TurnLLMRunner
from monika.application.agent.harness.turn_response_evaluator import TurnResponseEvaluator
from monika.application.agent.harness.turn_stop_auditor import TurnStopAuditor
from monika.application.agent.harness.turn_tool_pipeline import (
    ToolExecutionTracking,
    TurnToolPipeline,
)
from monika.application.analysis.tools.tool_executor import ToolExecutor
from monika.core.telemetry.tracing.spans import llm_span
from monika.infrastructure.llm.context_compaction import ContextCompactionEngine

logger = logging.getLogger("TradingAgent.AgentHarness")


MODEL_PRICING_PER_1M = {
    "claude": {"input": 3.0, "output": 15.0, "cache_read": 0.30},
    "gemini": {"input": 0.10, "output": 0.40, "cache_read": 0.025},
    "deepseek": {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "groq": {"input": 0.0, "output": 0.0, "cache_read": 0.0},
    "default": {"input": 1.0, "output": 3.0, "cache_read": 0.20},
}


def calculate_turn_cost_usd(model_name: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    try:
        from monika.infrastructure.providers.pricing_catalog import cost_usd

        return cost_usd(
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )
    except Exception:
        lower = (model_name or "").lower()
        rates = MODEL_PRICING_PER_1M["default"]
        for prefix, p_rates in MODEL_PRICING_PER_1M.items():
            if prefix in lower:
                rates = p_rates
                break
        cost = (
            input_tokens * rates["input"] + output_tokens * rates["output"] + cached_tokens * rates["cache_read"]
        ) / 1_000_000.0
        return round(cost, 6)


class AgentHarness:
    """
    Unified ReAct Agent Execution Harness.
    Provides provider-agnostic multi-turn execution with comprehensive guardrails.
    """

    def __init__(
        self,
        llm_client: Any,
        settings: Optional[dict] = None,
        max_tool_turns: int = 15,
        max_context_chars: int = 500000,
        db_session: Optional[AsyncSession] = None,
        fallback_client: Optional[Any] = None,
    ):
        """
        Initialize the Agent Harness.

        Args:
            llm_client: Underlying LLM client implementing run_tool_agent(messages, tools, system_prompt).
            settings: Global system configuration dictionary.
            max_tool_turns: Maximum allowed ReAct turns before forcing termination.
            max_context_chars: Maximum character budget before context trimming kicks in.
            db_session: Optional SQLAlchemy AsyncSession for pre-execute turn persistence.
            fallback_client: Optional secondary LLM client for cross-provider failover.
        """
        self.llm_client = llm_client
        self.fallback_client = fallback_client
        self._last_normalized_extra: dict[str, Any] = {}
        self.settings = settings or {}
        self.max_tool_turns = max_tool_turns
        self.max_context_chars = max_context_chars
        self.db_session = db_session
        self.per_turn_timeout_seconds = float(
            (self.settings or {}).get("llm", {}).get("per_turn_timeout_seconds", 360.0)
        )
        self.compactor = ContextCompactionEngine(self.settings)
        from monika.application.analysis.tools.tool_guardrails import ToolGuardrailController

        self.guardrail_controller = ToolGuardrailController(self.settings)
        from monika.application.agent.harness.context_compressor import ContextCompressor

        self.context_compressor = ContextCompressor(self.settings)
        from monika.application.agent.harness.stall_guard import StallGuard

        self.stall_guard = StallGuard(
            warning_threshold=self.settings.get("stall_warning_threshold", 10),
            force_terminate_threshold=self.settings.get("stall_terminate_threshold", 16),
        )
        from monika.infrastructure.llm.data_dedup import DataFetchDeduplicator

        self.data_dedup = DataFetchDeduplicator()
        from monika.application.agent.harness.verification_evidence_ledger import VerificationEvidenceLedger

        self.verification_ledger = VerificationEvidenceLedger()
        from monika.application.agent.harness.physical_deliverable_gate import PhysicalDeliverableGate

        self.physical_deliverable_gate = PhysicalDeliverableGate()
        from monika.application.agent.harness.general_tool_pruner import GeneralToolPruner

        self.general_tool_pruner = GeneralToolPruner()
        from monika.application.agent.harness.interactive_todo import TodoListState

        self.todo_state = TodoListState()
        self._active_turn_task: Optional[asyncio.Task] = None

        # Dual-Queue Steering Engine (Immediate Steering + Follow-Up Processing)
        self._steering_queue: deque = deque()
        self._follow_up_queue: deque = deque()
        self._next_turn_tool_choice: Optional[Any] = None

        # Surface Node 0: Immutable System Prompt Tracking & Invariance
        self._cached_surface_prompt: Optional[Any] = None
        self._cached_surface_prompt_hash: Optional[str] = None
        self._last_injected_dynamic_overlay: Optional[str] = None

        # 12 Modular Turn Protection Components
        self.budget_manager = WallClockBudgetManager(budget_seconds=self.per_turn_timeout_seconds)
        self.empty_response_guard = EmptyResponseGuard()
        self.scratchpad_guard = scratchpad_guard
        self.socket_guard = socket_guard
        self.replay_cache = ReadOnlyReplayCache.get_instance()
        self.auxiliary_router = AuxiliaryModelRouter(settings=self.settings)
        self.tool_round_coordinator = TurnToolRoundCoordinator()

        # Session Surface & Execution Guard Subsystems
        self.session_surface = SessionSurface()
        self.runtime_context_projection = RuntimeContextProjection()
        self.throttled_time_context = ThrottledTimeContext()
        self.repeat_tool_guard = RepeatToolGuard()
        self.fs_observation_gate = ObservedStateGate()
        self.tool_call_recovery = ToolCallRecovery()

    def enqueue_steering(
        self,
        content: str,
        sender: str = "operator",
        mode: str = "immediate",
    ) -> None:
        """
        Enqueue an external steering directive or follow-up task.
        - mode='immediate': drained at next inner turn before model call (live steering/invalidation).
        - mode='follow_up': drained after current loop finishes before going idle.
        """
        from monika.application.agent.harness.harness_state import SteeringMessage

        msg = SteeringMessage(content=content, sender=sender, mode=mode)
        if mode == "follow_up":
            self._follow_up_queue.append(msg)
        else:
            self._steering_queue.append(msg)
            # In-flight emergency steering cancellation
            if any(marker in content.upper() for marker in ("ESTOP", "HALT", "EMERGENCY", "ABORT", "CANCEL")):
                if self._active_turn_task and not self._active_turn_task.done():
                    logger.warning(
                        f"[AgentHarness] Immediate emergency directive '{content[:50]}' detected. "
                        f"Cancelling in-flight turn task."
                    )
                    self._active_turn_task.cancel()
        logger.info(f"[AgentHarness] Enqueued {mode} steering directive from '{sender}': {content[:80]}...")

    # --------------------------------------------------------------------------
    # Provider Response Normalization & Error Classification
    # --------------------------------------------------------------------------

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Check if exception is transient (rate limit 429, timeout, 529 overloaded, 502/503/504)."""
        err_str = str(exc).lower()
        status_code = getattr(exc, "status_code", getattr(exc, "code", None))
        if status_code in (429, 502, 503, 504, 529):
            return True
        if any(
            marker in err_str
            for marker in (
                "rate limit",
                "too many requests",
                "429",
                "timeout",
                "timed out",
                "overloaded",
                "529",
                "connection error",
                "temporarily unavailable",
            )
        ):
            return True
        return False

    @staticmethod
    def _is_billing_error(exc: Optional[Exception]) -> bool:
        """Check if exception is an API credit or billing exhaustion error."""
        if not exc:
            return False
        err_str = str(exc).lower()
        status_code = getattr(exc, "status_code", getattr(exc, "code", None))
        if status_code == 402:
            return True
        if any(
            marker in err_str
            for marker in (
                "credit balance is too low",
                "insufficient credits",
                "insufficient_quota",
                "exceeded your current quota",
                "billing",
            )
        ):
            return True
        return False

    def _detect_client_provider(self, client: Any = None) -> str:
        """Detect provider name for client instance cleanly."""
        target = client if client is not None else self.llm_client
        if target is None:
            return "unknown"
        p = getattr(target, "provider", None) or getattr(target, "provider_name", None)
        if isinstance(p, str) and p:
            return p
        cls_name = getattr(target, "__class__", type(target)).__name__.lower()
        for prov in ("anthropic", "gemini", "openai", "ollama", "groq"):
            if prov in cls_name:
                return prov
        return "openai"

    def _try_fallback_swap(self, stage_name: str, last_exc: Any) -> bool:
        """
        Attempt failover swap to fallback LLM client if configured.
        Returns True if fallback client was swapped in.
        """
        if self.fallback_client is not None:
            old_provider = self._detect_client_provider(self.llm_client)
            old_model = getattr(self.llm_client, "model", "unknown")
            self.llm_client = self.fallback_client
            self.fallback_client = None
            new_provider = self._detect_client_provider(self.llm_client)
            new_model = getattr(self.llm_client, "model", "unknown")
            logger.warning(
                f"[{stage_name}][AgentHarness] Swapping to fallback LLM client "
                f"({old_provider}:{old_model} -> {new_provider}:{new_model}) due to error: {last_exc}"
            )
            return True
        return False

    @staticmethod
    def _check_truncation(response: Any, stop_reason: str = "", content: Optional[str] = None) -> bool:
        """Detect if LLM response was truncated (stop_reason == 'length' or 'max_tokens' or premature cut)."""
        reasons = [stop_reason]
        if hasattr(response, "stop_reason"):
            reasons.append(getattr(response, "stop_reason", ""))
        if hasattr(response, "finish_reason"):
            reasons.append(getattr(response, "finish_reason", ""))
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if isinstance(choice, dict):
                reasons.append(choice.get("finish_reason", ""))
            elif hasattr(choice, "finish_reason"):
                reasons.append(getattr(choice, "finish_reason", ""))
        if isinstance(response, dict):
            reasons.append(response.get("stop_reason", ""))
            reasons.append(response.get("finish_reason", ""))
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    reasons.append(first_choice.get("finish_reason", ""))
                elif hasattr(first_choice, "finish_reason"):
                    reasons.append(getattr(first_choice, "finish_reason", ""))

        if any(str(r).lower() in ("length", "max_tokens") for r in reasons if r):
            return True

        # Stop-as-truncated heuristic: text cut off mid-sentence despite reporting stop
        if content and isinstance(content, str) and len(content.strip()) > 80:
            clean = content.strip()
            if not re.search(r'[.!?。！？}\]"\'`]\s*$', clean):
                raw_reasons = [str(r).lower() for r in reasons if r]
                if "stop" in raw_reasons or "end_turn" in raw_reasons:
                    logger.debug("Detected premature truncation despite stop finish_reason.")
                    return True

        return False

    @staticmethod
    def _fail_truncated_tool_calls(tool_use_blocks: list) -> list:
        """Return error results for all tool calls from a truncated response."""
        results = []
        for i, b in enumerate(tool_use_blocks):
            t_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            if not t_id and isinstance(b, dict):
                t_id = b.get("tool_call_id") or b.get("tool_use_id")
            if not t_id:
                t_id = f"truncated_{i}"

            t_name = b.get("name") if isinstance(b, dict) else getattr(b, "name", None)
            if not t_name and isinstance(b, dict) and "function" in b:
                fn = b["function"]
                t_name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "tool")
            elif not t_name and hasattr(b, "function"):
                fn = getattr(b, "function")
                t_name = getattr(fn, "name", "tool")
            t_name = str(t_name or "tool")

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(t_id),
                    "name": t_name,
                    "content": json.dumps(
                        {
                            "status": "refused_truncated_response",
                            "error": (
                                "[SYSTEM ERROR] Your previous response was truncated by the output token limit. "
                                "Tool call arguments are likely incomplete/corrupted and were NOT executed. "
                                "Reduce your reasoning length and re-issue the tool call with complete arguments. "
                                "Do NOT repeat the same call verbatim."
                            ),
                        }
                    ),
                    "is_error": True,
                }
            )
        return results

    async def _persist_assistant_turn(
        self,
        session: Optional[AsyncSession],
        messages: List[dict],
        turn_index: int,
        stage_name: str = "",
        cycle_id: str = "",
    ) -> None:
        """Persist assistant message with tool calls BEFORE executing tools (durable audit invariant)."""
        effective_session = session or getattr(self, "db_session", None)
        if not effective_session:
            return
        try:
            from monika.infrastructure.database.event_store import TradingEventStore

            assistant_msg = messages[-1] if messages else {}
            content = assistant_msg.get("content", "")
            content_preview = ""
            tool_calls = []

            if isinstance(content, str):
                content_preview = content[:500]
            elif isinstance(content, list):
                for b in content:
                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                    if b_type == "text":
                        t_text = b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
                        content_preview += str(t_text) + " "
                    elif b_type == "tool_use":
                        tool_calls.append(b)
                content_preview = content_preview.strip()[:500]

            payload = {
                "turn_index": turn_index,
                "stage_name": stage_name,
                "cycle_id": cycle_id,
                "tool_calls": tool_calls,
                "content_preview": content_preview,
            }

            await TradingEventStore.emit(
                session=effective_session,
                event_type="agent.turn.pre_execute",
                payload=payload,
                correlation_id=cycle_id or f"{stage_name}_{turn_index}",
                actor=stage_name or "agent_harness",
            )
            logger.debug(
                f"[{stage_name}][AgentHarness] Persisted pre-execute turn {turn_index} with {len(tool_calls)} tool calls."
            )
        except Exception as e:
            logger.error(f"[{stage_name}][AgentHarness] Failed to persist pre-execute turn: {e}", exc_info=True)
            raise RuntimeError(f"Audit invariant violation: Failed to persist pre-execute turn: {e}") from e

    @staticmethod
    def _enforce_role_alternation(messages: List[dict]) -> List[dict]:
        """Repair message sequences to maintain strict role alternation.

        Rules:
        - Never start with 'assistant' message (insert user placeholder for Anthropic)
        - Never two consecutive 'assistant' messages (insert hidden user placeholder)
        - Never two consecutive 'user' messages (merge content cleanly)
        """
        if not messages:
            return messages

        repaired: List[dict] = []
        if messages[0].get("role") == "assistant":
            repaired.append(
                {
                    "role": "user",
                    "content": "[System: Begin analysis.]",
                }
            )
        repaired.append(dict(messages[0]))

        for i in range(1, len(messages)):
            curr = dict(messages[i])
            prev = repaired[-1]

            curr_role = curr.get("role")
            prev_role = prev.get("role")

            if curr_role == "assistant" and prev_role == "assistant":
                repaired.append(
                    {
                        "role": "user",
                        "content": "[System: Continue with your analysis.]",
                    }
                )
                repaired.append(curr)
            elif curr_role == "user" and prev_role == "user":
                prev_content = prev.get("content", "")
                curr_content = curr.get("content", "")

                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    prev["content"] = f"{prev_content}\n\n{curr_content}"
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    prev["content"] = list(prev_content) + list(curr_content)
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    prev["content"] = list(prev_content) + [{"type": "text", "text": curr_content}]
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    prev["content"] = [{"type": "text", "text": prev_content}] + list(curr_content)
                else:
                    prev["content"] = f"{str(prev_content)}\n\n{str(curr_content)}"
            else:
                repaired.append(curr)

        return repaired

    def _normalize_response_content(self, response: Any) -> Tuple[List[dict], str, Optional[str], int, int, int, int]:
        """
        Normalize responses across Anthropic, Gemini (MockResponse), OpenAI, Groq, Ollama.
        Returns:
            (assistant_blocks, stop_reason, reasoning_content, in_tok, out_tok, cached_tok, thinking_tok)
        """
        assistant_blocks: List[dict] = []
        stop_reason = ""
        reasoning_content: Optional[str] = None
        in_tok = 0
        out_tok = 0
        cached_tok = 0
        thinking_tok = 0
        self._last_normalized_extra = {}

        def _safe_int(val: Any) -> int:
            if isinstance(val, bool):
                return 0
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str) and val.isdigit():
                return int(val)
            return 0

        if hasattr(response, "usage") and response.usage:
            u = response.usage
            in_tok = _safe_int(getattr(u, "input_tokens", getattr(u, "prompt_tokens", 0)))
            out_tok = _safe_int(getattr(u, "output_tokens", getattr(u, "completion_tokens", 0)))
            cached_tok = _safe_int(getattr(u, "cache_read_input_tokens", getattr(u, "cached_tokens", 0)))
            thinking_tok = _safe_int(getattr(u, "thinking_tokens", 0))
            prompt_details = getattr(u, "prompt_tokens_details", None)
            if prompt_details and not cached_tok:
                cached_tok = _safe_int(getattr(prompt_details, "cached_tokens", 0))
            comp_details = getattr(u, "completion_tokens_details", None)
            if comp_details and not thinking_tok:
                thinking_tok = _safe_int(getattr(comp_details, "reasoning_tokens", 0))
        else:
            in_tok = _safe_int(getattr(response, "input_tokens", 0))
            out_tok = _safe_int(getattr(response, "output_tokens", 0))
            cached_tok = _safe_int(getattr(response, "cached_tokens", 0))
            thinking_tok = _safe_int(getattr(response, "thinking_tokens", 0))

        client_provider = getattr(self.llm_client, "provider_name", "")
        client_cls = self.llm_client.__class__.__name__ if hasattr(self.llm_client, "__class__") else ""
        is_anthropic_or_gemini = (
            client_provider in ("anthropic", "gemini", "ollama")
            or "Anthropic" in client_cls
            or "Gemini" in client_cls
            or "Ollama" in client_cls
        )

        has_choices = hasattr(response, "choices")
        has_content = hasattr(response, "content")

        if (not is_anthropic_or_gemini and has_choices) or (not has_content and has_choices):
            if not response.choices:
                self.empty_response_guard.record_empty_response(
                    client_provider or "openai",
                    getattr(self.llm_client, "model", "unknown"),
                    "empty_choices",
                )
                raise ValueError("Invalid OpenAI response: 'choices' is empty or None")
            choice = response.choices[0]
            stop_reason = getattr(choice, "finish_reason", "") or "end_turn"
            msg = getattr(choice, "message", None)
            if not msg:
                raise ValueError("Invalid OpenAI response: choice 'message' is None")

            content_text = getattr(msg, "content", None)
            if content_text:
                closed_text = self.scratchpad_guard.close_dangling_scratchpad(str(content_text))
                ext_th, clean_text, _ = self.scratchpad_guard.extract_reasoning_and_content(closed_text)
                if ext_th and not reasoning_content:
                    reasoning_content = ext_th
                bounded_text = truncate_text_middle(clean_text, max_chars=100000)
                if bounded_text:
                    assistant_blocks.append({"type": "text", "text": str(bounded_text)})

            if not reasoning_content:
                reasoning_content = getattr(msg, "reasoning_content", getattr(msg, "reasoning", None))

            def _clean_val(v: Any) -> Any:
                if v is None or not isinstance(v, (str, int, float, bool, list, dict)):
                    return None
                return v

            if reasoning_content is not None and not isinstance(reasoning_content, (str, dict, list)):
                reasoning_content = None

            extra: dict[str, Any] = {}
            model_extra = _clean_val(getattr(msg, "model_extra", None))
            if isinstance(model_extra, dict):
                for k, v in model_extra.items():
                    cleaned_v = _clean_val(v)
                    if cleaned_v is not None:
                        extra[k] = cleaned_v

            for field_name in ("thought_signature", "reasoning_details", "extra_content"):
                val = _clean_val(getattr(msg, field_name, None))
                if val is not None:
                    extra[field_name] = val

            self._last_normalized_extra = extra

            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                fn_name = getattr(fn, "name", "") if fn else ""
                raw_args = getattr(fn, "arguments", {}) if fn else {}
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except Exception:
                        parsed_args = repair_tool_arguments(raw_args)
                else:
                    parsed_args = raw_args or {}

                tc_id = getattr(tc, "id", f"call_{fn_name}")
                assistant_blocks.append(
                    {"type": "tool_use", "id": str(tc_id), "name": str(fn_name), "input": parsed_args}
                )

        elif has_content:
            stop_reason = getattr(response, "stop_reason", "") or "end_turn"
            raw_content = response.content
            if isinstance(raw_content, list):
                for b in raw_content:
                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                    if b_type == "text":
                        t_text = b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
                        if t_text:
                            closed_t = self.scratchpad_guard.close_dangling_scratchpad(str(t_text))
                            ext_th, clean_t, _ = self.scratchpad_guard.extract_reasoning_and_content(closed_t)
                            if ext_th and not reasoning_content:
                                reasoning_content = ext_th
                            bounded_t = truncate_text_middle(clean_t, max_chars=100000)
                            if bounded_t:
                                assistant_blocks.append({"type": "text", "text": str(bounded_t)})
                    elif b_type == "tool_use":
                        t_name = b.get("name") if isinstance(b, dict) else getattr(b, "name", "")
                        t_input = b.get("input") if isinstance(b, dict) else getattr(b, "input", {})
                        t_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", "")
                        assistant_blocks.append(
                            {"type": "tool_use", "id": str(t_id), "name": str(t_name), "input": t_input}
                        )
                    elif b_type == "thinking":
                        th_text = b.get("thinking") if isinstance(b, dict) else getattr(b, "thinking", "")
                        sig = b.get("signature") if isinstance(b, dict) else getattr(b, "signature", None)
                        th_block: dict = {"type": "thinking", "thinking": str(th_text or "")}
                        if sig:
                            th_block["signature"] = str(sig)
                        assistant_blocks.append(th_block)
                    elif b_type == "redacted_thinking":
                        data = b.get("data") if isinstance(b, dict) else getattr(b, "data", "")
                        assistant_blocks.append({"type": "redacted_thinking", "data": str(data or "")})
                    elif isinstance(b, dict):
                        assistant_blocks.append(b)
            elif isinstance(raw_content, str) and raw_content:
                closed_r = self.scratchpad_guard.close_dangling_scratchpad(str(raw_content))
                ext_th, clean_r, _ = self.scratchpad_guard.extract_reasoning_and_content(closed_r)
                if ext_th and not reasoning_content:
                    reasoning_content = ext_th
                bounded_r = truncate_text_middle(clean_r, max_chars=100000)
                if bounded_r:
                    assistant_blocks.append({"type": "text", "text": str(bounded_r)})

        model_name_val = getattr(self.llm_client, "model", "unknown")
        if not assistant_blocks and not reasoning_content:
            self.empty_response_guard.record_empty_response(
                client_provider or "unknown",
                model_name_val,
                stop_reason,
            )
        else:
            self.empty_response_guard.record_successful_response(
                client_provider or "unknown",
                model_name_val,
            )

        return assistant_blocks, stop_reason, reasoning_content, in_tok, out_tok, cached_tok, thinking_tok

    # --------------------------------------------------------------------------
    # Deterministic Tool Hashing & Anti-Oscillation Guard
    # --------------------------------------------------------------------------

    @staticmethod
    def compute_tool_signature(tool_name: str, tool_input: Any) -> str:
        """
        Generate deterministic hash signature for tool name and argument payload.
        Uses recursive canonicalization to ensure identical signatures across varying key orders.
        """
        try:
            return compute_canonical_tool_signature(tool_name, tool_input)
        except Exception:
            return f"{tool_name}:{hashlib.md5(str(tool_input).encode('utf-8')).hexdigest()}"

    @staticmethod
    def _stub_exploration_tools(tools: list[dict], called_tools: Set[str]) -> list[dict]:
        """
        Dynamic tool stubbing for Turn >= 6:
        Replaces lengthy descriptions of previously called heavy exploration tools
        with a concise 1-line signature to conserve input tokens without breaking tool schema.
        """
        stubbed: list[dict] = []
        heavy_prefixes = (
            "get_historical",
            "get_candles",
            "get_calendar",
            "get_cot",
            "get_market_sentiment",
            "get_order_book",
        )
        for t in tools:
            name = str(t.get("name", ""))
            desc = str(t.get("description", ""))
            is_heavy = (
                name in called_tools
                and (any(name.startswith(p) for p in heavy_prefixes) or len(desc) > 150)
                and not name.startswith("submit_")
                and name not in ("todo_write", "request_human_guidance")
            )
            if is_heavy:
                t_copy = dict(t)
                t_copy["description"] = (
                    f"{name}: previously executed exploration tool. Retains schema; call only if new parameters required."
                )
                stubbed.append(t_copy)
            else:
                stubbed.append(t)
        return stubbed

    # --------------------------------------------------------------------------
    # State Preservation Context Truncation
    # --------------------------------------------------------------------------

    def _preserve_state_summary(self, trimmed_messages: List[dict]) -> List[str]:
        """
        Extract high-value deterministic facts from trimmed tool outputs to prevent
        the LLM from hallucinating or re-deriving established numbers.
        """
        preserved_facts: List[str] = []

        for msg in trimmed_messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "tool_result":
                        raw = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                        if isinstance(raw, str):
                            try:
                                td = json.loads(raw)
                                if isinstance(td, dict):
                                    if isinstance(td.get("atr_14"), (int, float)):
                                        preserved_facts.append(f"ATR_14={td['atr_14']}")
                                    if isinstance(td.get("latest"), dict):
                                        lat = td["latest"]
                                        if "close" in lat and "date" in lat:
                                            preserved_facts.append(f"Latest_Close={lat['close']} on {lat['date']}")
                                    if "trend_5d" in td:
                                        preserved_facts.append(f"Trend_5d={td['trend_5d']}")
                                    if "risk_sentiment" in td:
                                        preserved_facts.append(f"Risk_Sentiment={td['risk_sentiment']}")
                                    if isinstance(td.get("currency_bias"), dict):
                                        preserved_facts.append(f"Currency_Bias={json.dumps(td['currency_bias'])}")
                            except Exception:
                                pass
        return preserved_facts[:20]

    def _apply_truncation_guardrail(
        self,
        messages: List[dict],
        system_prompt: Any,
        stage_name: str,
    ) -> List[dict]:
        """
        Compress conversation history when message payload exceeds safety thresholds
        while maintaining the first prompt and an anti-hallucination state summary.
        """
        sys_len = (
            (len(system_prompt[0]) + len(system_prompt[1]))
            if isinstance(system_prompt, tuple)
            else len(str(system_prompt or ""))
        )
        full_msg_chars = sys_len + sum(len(str(m.get("content", ""))) for m in messages)

        if full_msg_chars <= self.max_context_chars or len(messages) <= 8:
            return messages

        logger.warning(
            f"[{stage_name}][AgentHarness] Context {full_msg_chars} chars exceeds limit "
            f"{self.max_context_chars}. Trimming with state preservation..."
        )

        first_msg = messages[:1]
        cutoff_idx = len(messages) - 6
        while cutoff_idx < len(messages) and messages[cutoff_idx].get("role") != "assistant":
            cutoff_idx += 1
        if cutoff_idx >= len(messages):
            cutoff_idx = len(messages) - 6

        trimmed_msgs = messages[1:cutoff_idx]
        preserved_facts = self._preserve_state_summary(trimmed_msgs)
        last_msgs = messages[cutoff_idx:]

        if preserved_facts:
            state_block = (
                "[CONTEXT WINDOW STATE SUMMARY — preserved from earlier turns]\n"
                "These facts were established in earlier turns and remain strictly valid:\n"
                + "\n".join(f"  • {f}" for f in preserved_facts)
                + "\n[END STATE SUMMARY — continue analysis with latest context below]"
            )
            summary_msg = {"role": "user", "content": state_block}
        else:
            summary_msg = {
                "role": "user",
                "content": (
                    "[SYSTEM: Earlier conversation turns trimmed for context budget. "
                    "Continue analysis with latest observations below.]"
                ),
            }

        return first_msg + [summary_msg] + last_msgs

    # --------------------------------------------------------------------------
    # Mandatory Tool Verification
    # --------------------------------------------------------------------------

    @staticmethod
    def get_mandatory_tool_for_stage(stage_name: str) -> Optional[str]:
        """Determine if a stage has an indispensable conclusion tool."""
        s_lower = stage_name.lower()
        if s_lower.startswith("per_asset_") or s_lower == "per_asset_primary" or "asset_analysis" in s_lower:
            return "submit_asset_analysis"
        if "fundamental" in s_lower or "stage1" in s_lower:
            return "submit_fundamental_brief"
        return None

    def _maybe_inject_wrapup_notice(
        self, elapsed_seconds: float, stage_timeout_seconds: Optional[float]
    ) -> Optional[str]:
        """Inject wrap-up directive if elapsed execution time reaches or exceeds 80% of budget."""
        if not stage_timeout_seconds or stage_timeout_seconds <= 0:
            return None
        if hasattr(self, "budget_manager") and self.budget_manager.should_inject_wrapup():
            self.budget_manager.mark_wrapup_injected()
            return self.budget_manager.get_wrapup_notice()
        if elapsed_seconds >= 0.8 * stage_timeout_seconds:
            return RUN_BUDGET_WRAPUP_NOTICE
        return None

    # --------------------------------------------------------------------------
    # Activity Log Integration
    # --------------------------------------------------------------------------

    async def _log_tool_call(
        self,
        session: Optional[AsyncSession],
        stage_name: str,
        tool_name: str,
        tool_input: dict,
        result: dict,
    ) -> None:
        """Audit trail logger saving tool execution details into ActivityLog."""
        if not session:
            return
        if hasattr(self.llm_client, "_log_tool_call"):
            try:
                await self.llm_client._log_tool_call(session, stage_name, tool_name, tool_input, result)
                return
            except Exception as e:
                logger.debug(f"[{stage_name}][AgentHarness] llm_client._log_tool_call non-fatal: {e}")
        try:
            from monika.infrastructure.database.models import ActivityLog

            actor_name = getattr(self.llm_client, "role", getattr(self.llm_client, "model", "agent_harness"))
            symbol = tool_input.get("symbol") if isinstance(tool_input, dict) else None

            raw_str = json.dumps(result, default=str)
            if len(raw_str) > 4000:
                raw_str = raw_str[:3980] + "... [truncated]"

            inp_str = json.dumps(tool_input, default=str)
            if len(inp_str) > 2000:
                inp_str = inp_str[:1980] + "... [truncated]"

            desc = f"tool_call:{tool_name} [{symbol or 'N/A'}]"
            details = json.dumps(
                {
                    "stage": stage_name,
                    "tool": tool_name,
                    "input": inp_str,
                    "result_summary": raw_str,
                }
            )
            log_entry = ActivityLog(
                actor=(actor_name or "ai_agent")[:50],
                category="analysis",
                description=f"{desc} - {details}",
                timestamp=datetime.now(timezone.utc),
            )
            session.add(log_entry)
            await session.commit()
        except Exception as e:
            logger.debug(f"[{stage_name}][AgentHarness] Failed to log tool call audit trail (non-fatal): {e}")

    # --------------------------------------------------------------------------
    # Unified Execution Entrypoints
    # --------------------------------------------------------------------------

    async def run_agent(
        self,
        session: Optional[AsyncSession],
        system_prompt: Any,
        user_message: Union[str, list[dict[str, Any]]],
        tools: list,
        stage_name: str = "unknown",
        extra_context: Optional[str] = None,
        prefetch_satisfied_tools: Optional[set] = None,
        max_tool_turns: Optional[int] = None,
        tool_executor: Optional[Any] = None,
        multimodal_images: Optional[list[dict[str, Any]]] = None,
        **kwargs,
    ) -> dict:
        """
        Execute full ReAct agent lifecycle starting from single user message.
        """
        initial_content: Union[str, list[dict[str, Any]]]
        if isinstance(user_message, list):
            blocks: list[dict[str, Any]] = [dict(b) for b in user_message]
            if extra_context:
                appended = False
                for block in blocks:
                    if block.get("type") == "text" and "text" in block:
                        block["text"] = f"{block['text']}\n\n--- Additional Context ---\n{extra_context}"
                        appended = True
                        break
                if not appended:
                    blocks.append({"type": "text", "text": f"--- Additional Context ---\n{extra_context}"})
            initial_content = blocks
        else:
            full_user_msg = str(user_message)
            if extra_context:
                full_user_msg += f"\n\n--- Additional Context ---\n{extra_context}"

            if multimodal_images:
                valid_images: list[dict[str, Any]] = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": str(img.get("media_type", "image/jpeg")),
                            "data": str(img.get("data", "")),
                        },
                    }
                    for img in multimodal_images
                    if isinstance(img, dict) and img.get("data")
                ]
                if valid_images:
                    initial_content = [{"type": "text", "text": full_user_msg}, *valid_images]
                else:
                    initial_content = full_user_msg
            else:
                initial_content = full_user_msg

        initial_messages = [{"role": "user", "content": initial_content}]
        return await self.run_agent_from_messages(
            session=session,
            system_prompt=system_prompt,
            messages=initial_messages,
            tools=tools,
            max_tool_turns=max_tool_turns,
            stage_name=stage_name,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            tool_executor=tool_executor,
            **kwargs,
        )

    async def run_agent_from_messages(
        self,
        session: Optional[AsyncSession],
        system_prompt: Any,
        messages: list,
        tools: list,
        max_tool_turns: Optional[int] = None,
        stage_name: str = "unknown",
        prefetch_satisfied_tools: Optional[set] = None,
        tool_executor: Optional[Any] = None,
        **kwargs,
    ) -> dict:
        """
        Execute multi-turn tool calling loop continuing from existing message history.
        """
        session = session or getattr(self, "db_session", None)
        effective_max_turns = max_tool_turns or self.max_tool_turns
        stage_symbol = stage_name.replace("per_asset_", "") if stage_name.startswith("per_asset_") else None
        if stage_symbol:
            try:
                from monika.application.agent.turn_lease_manager import SymbolTurnLeaseManager

                await SymbolTurnLeaseManager.get_instance().attach_harness_for_symbol(stage_symbol, self)
            except Exception as e:
                logger.debug(f"Failed to attach harness to lease for {stage_symbol}: {e}")

        turn_timeout = float(kwargs.get("turn_timeout_seconds") or getattr(self, "per_turn_timeout_seconds", 360.0))
        client_thinking = getattr(self.llm_client, "thinking_level", None)
        if client_thinking and str(client_thinking).lower() not in ("none", "off", ""):
            turn_timeout = max(turn_timeout, 420.0)

        # Minify tool definitions to eliminate verbose schema bloat across multi-turn ReAct loop
        if tools:
            try:
                from monika.application.analysis.tools.tools_definitions import minify_tool_definitions

                tools = minify_tool_definitions(tools)
            except Exception as e:
                logger.debug(f"Tool minification fallback (non-fatal): {e}")

        active_tools: list[dict] = [dict(t) for t in tools] if tools else []
        active_tools.sort(key=lambda t: str(t.get("name", "")))
        task_role = getattr(self.llm_client, "role", None) or stage_name

        if hasattr(self, "repeat_tool_guard") and self.repeat_tool_guard:
            self.repeat_tool_guard.reset_on_user_turn()

        curr_max = getattr(self.llm_client, "max_tokens", None)
        if isinstance(curr_max, int) and curr_max < 32000:
            if getattr(self.llm_client, "provider_name", "") in ("groq", "openrouter"):
                self.llm_client.max_tokens = 32000

        # Initialize or reuse tool executor
        executor = tool_executor
        if executor is None:
            import sys

            llm_mod = (
                sys.modules.get(self.llm_client.__class__.__module__) if hasattr(self.llm_client, "__class__") else None
            )
            executor_cls = getattr(llm_mod, "ToolExecutor", ToolExecutor) if llm_mod else ToolExecutor
            model_name = getattr(self.llm_client, "model", "unknown_model")
            executor = executor_cls(
                session=cast(AsyncSession, session),
                settings=self.settings,
                model_name=model_name,
                prefetch_satisfied_tools=prefetch_satisfied_tools,
                symbol=stage_symbol,
            )
        if executor is not None:
            executor.verification_ledger = self.verification_ledger
            executor.todo_state = self.todo_state
        else:
            raise RuntimeError("ToolExecutor failed to initialize in run_agent_loop")

        turns = 0
        ptc_refund_count = 0
        dedup_refund_count = 0
        tool_calls_made = 0
        final_text = ""
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0
        total_thinking_tokens = 0
        total_cost_usd = 0.0
        is_paid = False
        length_truncated = False

        tracking = ToolExecutionTracking(
            tool_calls_made=0,
            consecutive_tool_sig=None,
            repeated_tool_count=0,
            total_sig_counts={},
            sliding_window_sigs=deque(maxlen=8),
            called_tools=set(),
            persisted_mandatory_tools=set(),
            unpersisted_validation_failures=set(),
        )

        # Reset all guardrails for fresh stage execution
        self.guardrail_controller.reset_all()
        if prefetch_satisfied_tools:
            for p_tool in prefetch_satisfied_tools:
                self.guardrail_controller.read_before_act.record_call(p_tool)
        self.stall_guard.reset()
        self.verification_ledger.reset_turn()
        if hasattr(self, "todo_state") and self.todo_state is not None:
            self.todo_state.reset()
        _emergency_recovery_turns_used = 0
        _max_emergency_recovery_turns = int(self.settings.get("max_emergency_recovery_turns", 2))
        unverified_stop_gate_error: Optional[str] = None

        current_messages = list(messages)

        logger.info(
            f"[{stage_name}][AgentHarness] Starting ReAct loop "
            f"(max_turns={effective_max_turns}, tools_available={len(active_tools)})"
        )

        _overflow_recovery_attempted = False
        stage_timeout_seconds = kwargs.get("stage_timeout_seconds")
        if not stage_timeout_seconds:
            is_benchmark = self.settings.get("_benchmark_mode", False)
            client_thinking = getattr(self.llm_client, "thinking_level", None)
            is_thinking_client = client_thinking and str(client_thinking).lower() not in ("none", "off", "")
            is_macro_or_fundamental = (
                stage_name in ("fundamental", "macro", "benchmark_stage1_fundamental") or "macro" in stage_name
            )
            default_timeout = 900.0 if (is_benchmark or is_macro_or_fundamental or is_thinking_client) else 600.0
            stage_timeout_seconds = float(self.settings.get("stage_timeout_seconds") or default_timeout)
            if stage_timeout_seconds < default_timeout:
                stage_timeout_seconds = default_timeout
        _wrapup_injected = False
        _stage_start_time = asyncio.get_event_loop().time()

        # WallClockBudgetManager & TurnState initialization
        self.budget_manager.reset(budget_seconds=stage_timeout_seconds or turn_timeout)
        turn_state = TurnState(
            turn_id=f"{stage_name}_{int(_stage_start_time)}",
            session_id=str(getattr(session, "hash", id(session))),
            user_prompt=str(current_messages[-1].get("content") if current_messages else ""),
            current_phase=TurnPhase.PREFLIGHT,
        )

        while turns < effective_max_turns:
            turns += 1
            turn_state.iteration = turns
            turn_state.current_phase = TurnPhase.PREFLIGHT
            self.guardrail_controller.reset_turn()

            # Check wall-clock time budget and inject wrap-up directive at >= 80% (Phase 6.4)
            if not _wrapup_injected and stage_timeout_seconds:
                elapsed = asyncio.get_event_loop().time() - _stage_start_time
                wrapup_msg = self._maybe_inject_wrapup_notice(elapsed, stage_timeout_seconds)
                if wrapup_msg:
                    _wrapup_injected = True
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Time budget 80% reached ({elapsed:.1f}s / {stage_timeout_seconds:.1f}s). "
                        f"Injecting wrap-up directive."
                    )
                    if current_messages and current_messages[-1].get("role") == "user":
                        prev_c = current_messages[-1].get("content")
                        if isinstance(prev_c, str):
                            current_messages[-1]["content"] = f"{prev_c}\n\n{wrapup_msg}"
                        elif isinstance(prev_c, list):
                            current_messages[-1]["content"].append({"type": "text", "text": f"\n\n{wrapup_msg}"})
                    else:
                        current_messages.append({"role": "user", "content": wrapup_msg})

            # ── Dual-Queue Steering Drainage (Immediate Steering) ──
            if self._steering_queue:
                steering_directives = []
                while self._steering_queue:
                    s_msg = self._steering_queue.popleft()
                    steering_directives.append(f"[{s_msg.sender.upper()} STEERING DIRECTIVE]: {s_msg.content}")
                if steering_directives:
                    combined_steering = "\n".join(steering_directives)
                    logger.info(
                        f"[{stage_name}][AgentHarness] Injecting {len(steering_directives)} "
                        f"steering directive(s) into active turn {turns}."
                    )
                    if current_messages and current_messages[-1].get("role") == "user":
                        prev_c = current_messages[-1].get("content")
                        if isinstance(prev_c, str):
                            current_messages[-1]["content"] = f"{prev_c}\n\n{combined_steering}"
                        elif isinstance(prev_c, list):
                            current_messages[-1]["content"].append({"type": "text", "text": f"\n\n{combined_steering}"})
                    else:
                        current_messages.append({"role": "user", "content": combined_steering})

            # 1. Layer 1/2 Context Compaction & Observation Masking
            from monika.application.agent.harness.context_compressor import offload_historical_charts
            from monika.infrastructure.providers.capabilities import resolve_effective_context_window

            context_win = resolve_effective_context_window(
                model_name=getattr(self.llm_client, "model", None),
                provider_name=getattr(self.llm_client, "provider_name", None),
                settings=self.settings,
            )
            # TurnPreflightGate context floor validation
            is_floor_ok, floor_msg = TurnPreflightGate.validate_context_floor(
                context_win, estimated_required_tokens=2048
            )
            if not is_floor_ok:
                logger.warning(f"[{stage_name}][AgentHarness] Preflight context floor warning: {floor_msg}")

            # Surface Node 0 Invariant: Preserve messages[0] prefix and historical charts across turns
            current_tokens = self.compactor.calculate_history_tokens(current_messages)
            if current_tokens > int(context_win * 0.80):
                current_messages = offload_historical_charts(current_messages, retain_recent_turns=2)

            enable_prefetch_distillation = bool(
                (self.settings or {}).get("harness", {}).get("enable_prefetch_distillation", False)
            )
            if enable_prefetch_distillation and current_tokens > int(context_win * 0.85):
                try:
                    from monika.application.agent.harness.context_compressor import ContextCompressor

                    current_messages = ContextCompressor.distill_initial_bundle_after_turn_1(
                        current_messages, turn=turns, preserve_kv_cache=False
                    )
                except Exception as dist_err:
                    logger.debug(f"Prefetch bundle distillation skipped: {dist_err}")

            # Dynamic Tool Definition Selection (Turn >= 6)
            stub_tools_on_turn_6 = bool(
                (self.settings or {}).get("harness", {}).get("enable_legacy_turn6_tool_stubbing", False)
            )
            if turns >= 6 and stub_tools_on_turn_6 and not self.settings.get("disable_tool_stubbing", False):
                effective_tools = self._stub_exploration_tools(active_tools, tracking.called_tools)
            else:
                effective_tools = active_tools

            # Layer 1/2 Compaction with Warm-Prefix Forwarding
            if hasattr(self.compactor, "check_and_compact_async"):
                current_messages = await self.compactor.check_and_compact_async(
                    current_messages,
                    context_window=context_win,
                    system_prompt=system_prompt,
                    tools=effective_tools,
                    settings=self.settings,
                )
            else:
                current_messages = self.compactor.check_and_compact(current_messages, context_window=context_win)

            # High-Water-Mark Gate
            if current_tokens >= int(context_win * 0.80):
                if hasattr(self, "context_compressor") and self.context_compressor:
                    try:
                        current_messages = await self.context_compressor.compress(
                            current_messages,
                            max_context_chars=self.max_context_chars,
                            tail_turns=3,
                            primary_client=self.llm_client,
                        )
                    except Exception as comp_err:
                        logger.debug(f"ContextCompressor skipped or failed: {comp_err}")

                current_messages = self._apply_truncation_guardrail(
                    current_messages, system_prompt=system_prompt, stage_name=stage_name
                )

            # 2. Invoke LLM via TurnLLMRunner
            llm_res = await TurnLLMRunner.execute_turn_llm(
                harness=self,
                session=session,
                current_messages=current_messages,
                effective_tools=effective_tools,
                system_prompt=system_prompt,
                stage_name=stage_name,
                turns=turns,
                effective_max_turns=effective_max_turns,
                turn_timeout=turn_timeout,
                turn_state=turn_state,
                context_win=context_win,
                tool_calls_made=tool_calls_made,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_cached_tokens=total_cached_tokens,
                total_thinking_tokens=total_thinking_tokens,
                is_paid=is_paid,
                length_truncated=length_truncated,
                emergency_recovery_turns_used=_emergency_recovery_turns_used,
                overflow_recovery_attempted=_overflow_recovery_attempted,
            )
            current_messages = llm_res.current_messages
            if llm_res.terminated_early:
                return llm_res.early_return_payload or {"success": False}
            if llm_res.stop_iteration:
                turns -= 1
                break
            if llm_res.fallback_swapped:
                if turns >= effective_max_turns:
                    effective_max_turns += 1
                continue

            # 3. Evaluate and Normalize Response via TurnResponseEvaluator
            eval_res = TurnResponseEvaluator.evaluate_response(
                harness=self,
                session=session,
                response=llm_res.response,
                current_messages=current_messages,
                stage_name=stage_name,
                turns=turns,
                effective_max_turns=effective_max_turns,
                context_win=context_win,
                tool_calls_made=tool_calls_made,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_cached_tokens=total_cached_tokens,
                total_thinking_tokens=total_thinking_tokens,
                total_cost_usd=total_cost_usd,
                is_paid=is_paid,
                length_truncated=length_truncated,
                overflow_recovery_attempted=_overflow_recovery_attempted,
                calculate_turn_cost_fn=calculate_turn_cost_usd,
                called_tools=tracking.called_tools,
                active_llm_span=llm_res.active_llm_span,
            )

            if eval_res.action == "emergency_compact":
                _overflow_recovery_attempted = True
                continue
            if eval_res.action == "early_return":
                return eval_res.early_return_payload or {"success": False}

            total_input_tokens += eval_res.in_tok
            total_output_tokens += eval_res.out_tok
            total_cached_tokens += eval_res.c_tok
            total_thinking_tokens += eval_res.th_tok
            total_cost_usd += eval_res.turn_cost_usd
            if eval_res.is_paid:
                is_paid = True
            if eval_res.length_truncated:
                length_truncated = True
            if eval_res.unverified_stop_gate_error:
                unverified_stop_gate_error = eval_res.unverified_stop_gate_error

            if eval_res.action == "continue_turn":
                if eval_res.tool_calls_increment > 0:
                    tool_calls_made += eval_res.tool_calls_increment
                    tracking.tool_calls_made = tool_calls_made
                continue
            final_text = eval_res.final_text
            tool_use_blocks = eval_res.tool_use_blocks

            # 4. Check Completion & Mandatory Tool Enforcement / Stop Gates
            if not tool_use_blocks:
                stop_verdict = TurnStopAuditor.audit_completion(
                    harness=self,
                    current_messages=current_messages,
                    final_text=final_text,
                    stage_name=stage_name,
                    stage_symbol=stage_symbol,
                    turns=turns,
                    effective_max_turns=effective_max_turns,
                    called_tools=tracking.called_tools,
                    unpersisted_validation_failures=tracking.unpersisted_validation_failures,
                    turn_state=turn_state,
                    tool_calls_made=tool_calls_made,
                    emergency_recovery_turns_used=_emergency_recovery_turns_used,
                    max_emergency_recovery_turns=_max_emergency_recovery_turns,
                    current_unverified_error=unverified_stop_gate_error,
                )
                final_text = stop_verdict.final_text
                if stop_verdict.unverified_stop_gate_error is not None:
                    unverified_stop_gate_error = stop_verdict.unverified_stop_gate_error
                if stop_verdict.emergency_recovery_turns_added > 0:
                    effective_max_turns += stop_verdict.emergency_recovery_turns_added
                    _emergency_recovery_turns_used += stop_verdict.emergency_recovery_turns_added

                if stop_verdict.can_break:
                    break
                else:
                    continue

            # 5. Persist Assistant Turn BEFORE Executing Tools
            cycle_id = kwargs.get("cycle_id", "")
            await self._persist_assistant_turn(
                session=session,
                messages=current_messages,
                turn_index=turns,
                stage_name=stage_name,
                cycle_id=cycle_id,
            )

            # 6. Execute Segmented Tool Pipeline
            tracking.tool_calls_made = tool_calls_made
            pipe_res = await TurnToolPipeline.execute_tools(
                harness=self,
                session=session,
                executor=executor,
                tool_use_blocks=tool_use_blocks,
                final_text=final_text,
                stage_name=stage_name,
                stage_symbol=stage_symbol,
                turns=turns,
                effective_max_turns=effective_max_turns,
                tracking=tracking,
                turn_state=turn_state,
                active_tools=active_tools,
                prefetch_satisfied_tools=prefetch_satisfied_tools,
                kwargs=kwargs,
            )
            tool_calls_made = pipe_res.tool_calls_made
            tool_results = pipe_res.tool_results
            current_messages.append({"role": "user", "content": tool_results})

            # Emergency turn extension if mandatory submission tool failed on final turn
            mandatory_tool = self.get_mandatory_tool_for_stage(stage_name)
            has_failed_mandatory = mandatory_tool in tracking.unpersisted_validation_failures or any(
                isinstance(tr, dict) and tr.get("is_error") and tr.get("name") == mandatory_tool for tr in tool_results
            )
            if (
                has_failed_mandatory
                and turns >= effective_max_turns
                and _emergency_recovery_turns_used < _max_emergency_recovery_turns
            ):
                effective_max_turns += 1
                _emergency_recovery_turns_used += 1
                logger.warning(
                    f"[{stage_name}][AgentHarness] Mandatory tool '{mandatory_tool}' failed on turn {turns}/{effective_max_turns - 1}. "
                    f"Granted emergency recovery turn ({_emergency_recovery_turns_used}/{_max_emergency_recovery_turns})."
                )

            # 7. Budget Refunds (PTC and Dedup)
            prepared_submission = any(
                b.get("name") == "execute_analysis_code"
                for b in tool_use_blocks
                if isinstance(b, dict) or hasattr(b, "name")
            )
            if len(tool_use_blocks) == 1 and prepared_submission:
                if ptc_refund_count < 3:
                    turns -= 1
                    ptc_refund_count += 1
                    logger.debug(
                        f"[{stage_name}][AgentHarness] PTC budget refund ({ptc_refund_count}/3): turn not counted"
                    )
                else:
                    logger.warning(f"[{stage_name}][AgentHarness] PTC budget refund cap reached ({ptc_refund_count}/3)")

            actual_tool_results = [
                tr for tr in tool_results if isinstance(tr, dict) and tr.get("type") == "tool_result"
            ]
            is_all_dedup = False
            if tool_use_blocks and actual_tool_results:
                parsed_res = []
                for tr in actual_tool_results:
                    c_text = str(tr.get("content", ""))
                    if "already satisfied in prefetch bundle" in c_text or "already_executed" in c_text:
                        parsed_res.append(True)
                    else:
                        parsed_res.append(False)
                if parsed_res and all(parsed_res):
                    is_all_dedup = True

            if is_all_dedup and dedup_refund_count < 2:
                turns -= 1
                dedup_refund_count += 1
                logger.info(
                    f"[{stage_name}][AgentHarness] Dedup tool budget refund ({dedup_refund_count}/2): turn not counted"
                )

            # 8. Penultimate Turn Forcing Directive: lock read tools and mandate terminal submission
            terminal_sub_tool = (
                "submit_fundamental_brief"
                if ("fundamental" in stage_name.lower() or "stage1" in stage_name.lower())
                else (
                    "submit_asset_analysis"
                    if ("asset" in stage_name.lower() or "stage2" in stage_name.lower())
                    else None
                )
            )
            if (
                terminal_sub_tool
                and (
                    terminal_sub_tool not in tracking.called_tools
                    or terminal_sub_tool in tracking.unpersisted_validation_failures
                )
                and turns == effective_max_turns - 1
            ):
                forcing_directive = (
                    f"\n\n[CRITICAL MANDATORY INSTRUCTION — TURN BUDGET LIMIT REACHED]:\n"
                    f"You are on turn {turns}/{effective_max_turns}. You have gathered more than sufficient market data.\n"
                    f"All additional read tools are now LOCKED.\n"
                    f"On your NEXT step, you MUST invoke '{terminal_sub_tool}' with your complete synthesis.\n"
                    f"NOTE: If recommending BUY or SELL, supply valid entry_price, stop_loss, and take_profit in '{terminal_sub_tool}' (verified sizing will be auto-calculated) or run 'calculate_position_size'.\n"
                    f"Do NOT call any more get_* or read_* tools."
                )
                if isinstance(current_messages[-1].get("content"), list):
                    current_messages[-1]["content"].append({"type": "text", "text": forcing_directive})
                elif current_messages:
                    current_messages[-1]["content"] = f"{current_messages[-1].get('content', '')}{forcing_directive}"
                logger.info(
                    f"[{stage_name}][AgentHarness] Injected Penultimate Turn Forcing Directive for '{terminal_sub_tool}' on turn {turns}/{effective_max_turns}."
                )

            # 9. State-Aware Stall Guard Check (H-8)
            if not is_all_dedup:
                is_stall_warn, is_stall_terminate, stall_msg = self.stall_guard.check_stall()
                if is_stall_terminate and stall_msg:
                    logger.warning(f"[{stage_name}][AgentHarness] STALL GUARD FORCE TERMINATION: {stall_msg}")
                    if current_messages:
                        last_content = current_messages[-1].get("content")
                        if isinstance(last_content, list):
                            last_content.append({"type": "text", "text": f"\n[STALL GUARD TERMINATION]: {stall_msg}"})
                        else:
                            current_messages[-1]["content"] = (
                                f"{last_content or ''}\n\n[STALL GUARD TERMINATION]: {stall_msg}"
                            )
                    if effective_max_turns > turns + 1:
                        effective_max_turns = turns + 1
                elif is_stall_warn and stall_msg:
                    logger.info(f"[{stage_name}][AgentHarness] STALL GUARD WARNING: {stall_msg}")
                    if current_messages:
                        last_content = current_messages[-1].get("content")
                        if isinstance(last_content, list):
                            last_content.append({"type": "text", "text": f"\n[STALL GUARD WARNING]: {stall_msg}"})
                        else:
                            current_messages[-1]["content"] = (
                                f"{last_content or ''}\n\n[STALL GUARD WARNING]: {stall_msg}"
                            )

        # Ensure mandatory tool failure is accurately reflected in result success
        mandatory_tool = self.get_mandatory_tool_for_stage(stage_name)
        if mandatory_tool:
            if mandatory_tool in tracking.unpersisted_validation_failures:
                if unverified_stop_gate_error is None:
                    unverified_stop_gate_error = (
                        f"Mandatory submission tool '{mandatory_tool}' failed validation and was not persisted."
                    )
            elif mandatory_tool not in tracking.called_tools:
                if unverified_stop_gate_error is None:
                    unverified_stop_gate_error = (
                        f"Mandatory submission tool '{mandatory_tool}' was never called by agent."
                    )

        if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(self.llm_client, "_save_token_usage"):
            try:
                await self.llm_client._save_token_usage(
                    model_name=getattr(self.llm_client, "model", "unknown"),
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
            except Exception as e:
                logger.debug(f"[{stage_name}][AgentHarness] Token save failed: {e}")

        clear_socket_graveyard()
        return {
            "success": unverified_stop_gate_error is None,
            "final_text": final_text,
            "tool_calls_made": tool_calls_made,
            "turns": turns,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "thinking_tokens": total_thinking_tokens,
            "cached_tokens": total_cached_tokens,
            "total_cost_usd": round(total_cost_usd, 6),
            "context_messages": current_messages,
            "error": unverified_stop_gate_error,
            "is_paid": is_paid,
            "is_billing_error": False,
            "length_truncated": length_truncated,
            "phase_latencies": turn_state.phase_latencies,
        }


# Register AgentHarness factory with BaseLLMClient to decouple infrastructure from application
from monika.infrastructure.providers.base_provider import BaseLLMClient

BaseLLMClient.register_agent_harness_factory(AgentHarness)
