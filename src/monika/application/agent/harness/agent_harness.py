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
from monika.application.agent.harness.tool_batch_planner import ToolBatchPlanner
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
            (self.settings or {}).get("llm", {}).get("per_turn_timeout_seconds", 90.0)
        )
        self.compactor = ContextCompactionEngine(self.settings)
        from monika.application.analysis.tools.tool_guardrails import ToolGuardrailController

        self.guardrail_controller = ToolGuardrailController(self.settings)
        from monika.application.agent.harness.context_compressor import ContextCompressor

        self.context_compressor = ContextCompressor(self.settings)
        from monika.application.agent.harness.stall_guard import StallGuard

        self.stall_guard = StallGuard(
            warning_threshold=self.settings.get("stall_warning_threshold", 4),
            force_terminate_threshold=self.settings.get("stall_terminate_threshold", 7),
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

        # Usage extraction helper
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

        # Case 1: OpenAI-compatible ChatCompletion (has choices)
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

        # Case 2: Anthropic Message or MockResponse (has content list)
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
        Used to detect oscillation loops and redundant tool calls.
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
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import ActivityLog

            actor_name = getattr(self.llm_client, "role", getattr(self.llm_client, "model", "agent_harness"))
            symbol = tool_input.get("symbol") if isinstance(tool_input, dict) else None

            # Sanitize result payload for storage
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
        user_message: str,
        tools: list,
        stage_name: str = "unknown",
        extra_context: Optional[str] = None,
        prefetch_satisfied_tools: Optional[set] = None,
        max_tool_turns: Optional[int] = None,
        tool_executor: Optional[Any] = None,
        **kwargs,
    ) -> dict:
        """
        Execute full ReAct agent lifecycle starting from single user message.
        """
        full_user_msg = user_message
        if extra_context:
            full_user_msg += f"\n\n--- Additional Context ---\n{extra_context}"

        initial_messages = [{"role": "user", "content": full_user_msg}]
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

        turn_timeout = float(kwargs.get("turn_timeout_seconds") or getattr(self, "per_turn_timeout_seconds", 90.0))

        # Minify tool definitions to eliminate verbose schema bloat across multi-turn ReAct loop
        if tools:
            try:
                from monika.application.analysis.tools.tools_definitions import minify_tool_definitions

                tools = minify_tool_definitions(tools)
            except Exception as e:
                logger.debug(f"Tool minification fallback (non-fatal): {e}")

        active_tools: list[dict] = [dict(t) for t in tools] if tools else []
        active_tools.sort(key=lambda t: str(t.get("name", "")))

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
        tool_calls_made = 0
        final_text = ""
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0
        total_thinking_tokens = 0
        total_cost_usd = 0.0
        is_paid = False
        length_truncated = False

        called_tools: Set[str] = set()
        consecutive_tool_sig: Optional[str] = None
        repeated_tool_count: int = 0
        total_sig_counts: Dict[str, int] = {}
        sliding_window_sigs: deque[str] = deque(maxlen=8)

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
            default_timeout = 600.0 if is_benchmark else 180.0
            stage_timeout_seconds = self.settings.get("stage_timeout_seconds", default_timeout)
            if is_benchmark and stage_timeout_seconds < 600.0:
                stage_timeout_seconds = 600.0
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
            # to maximize provider KV-cache reuse. Compaction/offloading triggers ONLY at high-water mark (>80%).
            current_tokens = self.compactor.calculate_history_tokens(current_messages)
            if current_tokens > int(context_win * 0.80):
                # Offload heavy multimodal chart data from historical turns (>2 turns old)
                current_messages = offload_historical_charts(current_messages, retain_recent_turns=2)

            if current_tokens > int(context_win * 0.85):
                try:
                    from monika.application.agent.harness.context_compressor import ContextCompressor

                    current_messages = ContextCompressor.distill_initial_bundle_after_turn_1(current_messages)
                except Exception as dist_err:
                    logger.debug(f"Prefetch bundle distillation skipped: {dist_err}")

            current_messages = self.compactor.check_and_compact(current_messages, context_window=context_win)

            # 2. Context Compression (HIGH-4)
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

            # 3. Layer 3 Truncation Guardrail with Fact Preservation
            current_messages = self._apply_truncation_guardrail(
                current_messages, system_prompt=system_prompt, stage_name=stage_name
            )

            # Dynamic Tool Definition Stubbing (Turn >= 6) for Heavy Exploration Tools
            if turns >= 6 and not self.settings.get("disable_tool_stubbing", False):
                effective_tools = self._stub_exploration_tools(active_tools, called_tools)
            else:
                effective_tools = active_tools

            # 3. Provider Call with Transient Retry, Distributed Tracing, and Plugin Hooks
            from monika.application.plugins.manager.manager import PluginHook, get_plugin_manager

            plugin_mgr = get_plugin_manager()
            await plugin_mgr.emit(
                PluginHook.PRE_LLM_CALL,
                stage_name=stage_name,
                turn=turns,
                messages=current_messages,
                tools=effective_tools,
            )

            provider_name = getattr(self.llm_client, "provider_name", "unknown")
            model_name = getattr(self.llm_client, "model", "unknown")
            task_role = getattr(self.llm_client, "role", stage_name)

            response = None
            last_exc = None
            max_attempts = 3
            pre_turn_checkpoint = [dict(m) for m in current_messages]

            with llm_span(provider=provider_name, model=model_name, task_role=task_role) as active_llm_span:
                for attempt in range(max_attempts):
                    try:
                        # ── C4: ROLE ALTERNATION ENFORCEMENT & INTEGRITY REPAIR ──
                        role_safe_messages = self._enforce_role_alternation(current_messages)
                        try:
                            from monika.application.agent.harness.message_repair import repair_message_history

                            role_safe_messages = repair_message_history(role_safe_messages)
                        except Exception as e:
                            logger.debug(f"Message repair skipped: {e}")

                        # ── C3: COPY-ON-WRITE MESSAGE PROTECTION ──
                        # Clone messages before sending to prevent provider-specific
                        # canonicalization from corrupting durable conversation history.
                        import copy

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
                        from monika.infrastructure.providers.base_provider import _flatten_system_prompt

                        compile_stable_fn = getattr(system_prompt, "compile_stable_system", None)
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
                        if self._cached_surface_prompt is None:
                            self._cached_surface_prompt = current_static_sys
                            self._cached_surface_prompt_hash = static_hash
                            effective_sys = current_static_sys
                        else:
                            effective_sys = self._cached_surface_prompt
                            # 1.6: In-history system prompt updates (Append, Don't Replace)
                            if static_hash != self._cached_surface_prompt_hash:
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
                        if dynamic_sys and dynamic_sys != self._last_injected_dynamic_overlay:
                            self._last_injected_dynamic_overlay = dynamic_sys
                            snapshot_text = f"<volatile_overlay>\n{dynamic_sys}\n</volatile_overlay>"
                            if (
                                turns == 1
                                and send_messages
                                and send_messages[0].get("role") == "user"
                                and "<volatile_overlay>" not in str(send_messages[0].get("content", ""))
                            ):
                                prev_c = send_messages[0].get("content")
                                if isinstance(prev_c, str):
                                    send_messages[0]["content"] = f"{prev_c}\n\n{snapshot_text}"
                                elif isinstance(prev_c, list):
                                    send_messages[0]["content"].append({"type": "text", "text": f"\n\n{snapshot_text}"})
                                # Surface Node 0 invariant: keep current_messages[0] in sync so subsequent turns inherit identical prefix
                                if current_messages and current_messages[0].get("role") == "user":
                                    current_messages[0]["content"] = send_messages[0]["content"]
                            else:
                                last_user_msg = next(
                                    (m for m in reversed(send_messages) if m.get("role") == "user"), None
                                )
                                if last_user_msg and (turns == 1 or last_user_msg is not send_messages[0]):
                                    prev_c = last_user_msg.get("content")
                                    if isinstance(prev_c, str) and "<volatile_overlay>" not in prev_c:
                                        last_user_msg["content"] = f"{prev_c}\n\n{snapshot_text}"
                                    elif isinstance(prev_c, list):
                                        has_snapshot = any(
                                            "<volatile_overlay>" in str(b.get("text", ""))
                                            for b in prev_c
                                            if isinstance(b, dict)
                                        )
                                        if not has_snapshot:
                                            last_user_msg["content"].append(
                                                {"type": "text", "text": f"\n\n{snapshot_text}"}
                                            )
                                else:
                                    send_messages.append({"role": "user", "content": snapshot_text})

                        # 1.4: Active TODO list scaffold injection into latest user message
                        if hasattr(self, "todo_state") and self.todo_state and self.todo_state.has_items():
                            todo_scaffold = self.todo_state.format_scaffold()
                            if todo_scaffold:
                                todo_block = f"<active_todos>\n{todo_scaffold}\n</active_todos>"
                                last_user_msg = next(
                                    (m for m in reversed(send_messages) if m.get("role") == "user"), None
                                )
                                if last_user_msg:
                                    prev_c = last_user_msg.get("content")
                                    if isinstance(prev_c, str) and "<active_todos>" not in prev_c:
                                        last_user_msg["content"] = f"{prev_c}\n\n{todo_block}"
                                    elif isinstance(prev_c, list):
                                        if not any(
                                            "<active_todos>" in str(b.get("text", ""))
                                            for b in prev_c
                                            if isinstance(b, dict)
                                        ):
                                            last_user_msg["content"].append(
                                                {"type": "text", "text": f"\n\n{todo_block}"}
                                            )

                        turn_state.current_phase = TurnPhase.API_CALL
                        t_api_start = asyncio.get_event_loop().time()
                        _watchdog_ref: Optional[TurnLivenessWatchdog] = None
                        try:
                            async with TurnLivenessWatchdog(
                                turn_id=f"{stage_name}_{turns}",
                                timeout_seconds=turn_timeout,
                                stall_timeout_seconds=min(30.0, max(5.0, turn_timeout / 2.0)),
                                abort_on_hang=True,
                            ) as watchdog:
                                _watchdog_ref = watchdog
                                api_coro = run_bounded_async(
                                    self.llm_client.run_tool_agent(send_messages, effective_tools, effective_sys),
                                    timeout_seconds=turn_timeout,
                                    timeout_message=f"Turn {turns} LLM call timed out after {turn_timeout:.0f}s",
                                )
                                self._active_turn_task = asyncio.create_task(api_coro)
                                watchdog.set_task_to_cancel(self._active_turn_task)
                                try:
                                    response = await self._active_turn_task
                                finally:
                                    self._active_turn_task = None
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
                        if _emergency_recovery_turns_used > 0 and "StopIteration" in str(exc):
                            last_exc = exc
                            break
                        last_exc = exc

                        # ── Structured Error Recovery Pipeline (Phase 3) ──
                        from monika.application.agent.harness.error_classifier import (
                            ErrorCategory,
                            ErrorClassifier,
                            RecoveryAction,
                        )

                        classified = ErrorClassifier.classify(exc)

                        await plugin_mgr.emit(
                            PluginHook.ON_LLM_ERROR,
                            stage_name=stage_name,
                            turn=turns,
                            error=exc,
                            classified=classified,
                        )

                        if (
                            classified.recovery == RecoveryAction.RETRY_WITH_COMPACTION
                            and not _overflow_recovery_attempted
                        ):
                            _overflow_recovery_attempted = True
                            logger.warning(
                                f"[{stage_name}][AgentHarness] {classified.message} "
                                f"Running emergency compaction and retrying turn {turns}..."
                            )
                            if current_messages and current_messages[-1].get("role") == "assistant":
                                current_messages.pop()

                            current_messages = self.compactor.emergency_compact(
                                current_messages,
                                context_window=context_win,
                                target_reduction=0.50,
                            )
                            continue

                        if classified.recovery == RecoveryAction.ROTATE_CREDENTIAL:
                            logger.warning(f"[{stage_name}][AgentHarness] Rate limit encountered: {classified.message}")
                            if hasattr(self.llm_client, "rotate_key"):
                                self.llm_client.rotate_key()
                            elif hasattr(self.llm_client, "_rotate_key"):
                                self.llm_client._rotate_key()
                            if attempt < max_attempts - 1:
                                raw_backoff = (
                                    min(classified.retry_delay, 5.0)
                                    if classified.retry_delay > 0
                                    else (2.0 * (2**attempt))
                                )
                                backoff = raw_backoff * (1.0 - random.random() * 0.1)
                                await asyncio.sleep(backoff)
                                continue

                        is_timeout_err = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                        max_retry_attempts = 2 if is_timeout_err else max_attempts
                        if (
                            classified.recovery == RecoveryAction.RETRY_SAME or self._is_transient_error(exc)
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
                    if _emergency_recovery_turns_used > 0 and (
                        isinstance(last_exc, StopIteration) or "StopIteration" in str(last_exc)
                    ):
                        current_messages = pre_turn_checkpoint
                        turns -= 1
                        break

                    if self._try_fallback_swap(stage_name, last_exc):
                        from monika.application.agent.harness.message_repair import transform_messages_for_target_model

                        tgt_prov = self._detect_client_provider()
                        tgt_model = getattr(self.llm_client, "model", "")
                        current_messages = transform_messages_for_target_model(
                            current_messages,
                            target_provider=tgt_prov,
                            target_model=tgt_model,
                        )
                        if turns >= effective_max_turns:
                            effective_max_turns += 1
                        continue

                    is_billing = self._is_billing_error(last_exc)
                    logger.error(
                        f"[{stage_name}][AgentHarness] Provider error on turn {turns}: {last_exc} (is_billing={is_billing})"
                    )
                    if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(
                        self.llm_client, "_save_token_usage"
                    ):
                        try:
                            await self.llm_client._save_token_usage(
                                model_name=getattr(self.llm_client, "model", "unknown"),
                                task_name=stage_name,
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                                session=session,
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
                    return {
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

                # 4. Normalize Response Across Providers (Anthropic, Gemini, OpenAI, Groq)
                try:
                    assistant_content, stop_reason, reasoning_content, in_tok, out_tok, c_tok, th_tok = (
                        self._normalize_response_content(response)
                    )
                    active_llm_span.set_attribute("input_tokens", in_tok)
                    active_llm_span.set_attribute("output_tokens", out_tok)
                    active_llm_span.set_attribute("cached_tokens", c_tok)
                    active_llm_span.set_attribute("thinking_tokens", th_tok)

                    # ── Silent Overflow Detection (Input Token Ingestion Guard) ──
                    if in_tok > 0 and not _overflow_recovery_attempted:
                        from monika.infrastructure.llm.model_capabilities import MODEL_CAPABILITIES

                        model_name_check = getattr(self.llm_client, "model", "")
                        cap = MODEL_CAPABILITIES.get(model_name_check, None)
                        context_window = (
                            getattr(cap, "context_window", 0)
                            if cap
                            else (cap.get("context_window", 0) if isinstance(cap, dict) else 0)
                        )
                        if context_window > 0 and in_tok > context_window:
                            logger.warning(
                                f"[{stage_name}][AgentHarness] SILENT OVERFLOW detected: input_tokens={in_tok} > "
                                f"context_window={context_window}. Triggering compaction."
                            )
                            _overflow_recovery_attempted = True
                            current_messages = self.compactor.emergency_compact(
                                current_messages,
                                context_window=context_window,
                                target_reduction=0.50,
                            )
                            continue
                except Exception as norm_err:
                    logger.error(
                        f"[{stage_name}][AgentHarness] Response normalization error on turn {turns}: {norm_err}"
                    )
                    if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(
                        self.llm_client, "_save_token_usage"
                    ):
                        try:
                            await self.llm_client._save_token_usage(
                                model_name=getattr(self.llm_client, "model", "unknown"),
                                task_name=stage_name,
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                                session=session,
                                cached_tokens=total_cached_tokens,
                                thinking_tokens=total_thinking_tokens,
                                is_direct_free_tier=False if is_paid else None,
                                from_agent_harness=True,
                            )
                        except Exception:
                            pass
                    return {
                        "success": False,
                        "error": str(norm_err),
                        "is_billing_error": False,
                        "tool_calls_made": tool_calls_made,
                        "turns": turns,
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "thinking_tokens": total_thinking_tokens,
                        "cached_tokens": total_cached_tokens,
                        "context_messages": current_messages,
                        "is_paid": is_paid,
                        "length_truncated": length_truncated,
                    }

            if getattr(response, "is_paid", False):
                is_paid = True

            total_input_tokens += in_tok
            total_output_tokens += out_tok
            total_cached_tokens += c_tok
            total_thinking_tokens += th_tok
            model_name_curr = getattr(self.llm_client, "model", "unknown_model")
            total_cost_usd += calculate_turn_cost_usd(model_name_curr, in_tok, out_tok, c_tok)

            # 5. Build and Record Assistant Message (Preserving Reasoning Content)
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant_content}
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            # I2: Thinking Signature Persistence
            if getattr(response, "thinking_signature", None):
                assistant_msg["thinking_signature"] = getattr(response, "thinking_signature")
            curr_provider = self._detect_client_provider()
            assistant_msg["_source_provider"] = str(curr_provider)
            assistant_msg["_source_model"] = str(model_name_curr)

            if hasattr(self, "_last_normalized_extra") and self._last_normalized_extra:
                for k, v in self._last_normalized_extra.items():
                    if k not in assistant_msg:
                        assistant_msg[k] = v
            current_messages.append(assistant_msg)

            # Check text blocks
            for block in assistant_content:
                b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if b_type == "text":
                    b_text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                    if b_text and not getattr(block, "thinking", False):
                        final_text = b_text

            # ── Repetition Guard (Degenerate Echo Loop Prevention & History Cleansing) ──
            if final_text:
                from monika.application.agent.harness.repetition_guard import detect_text_repetition

                is_degenerate, rep_snippet = detect_text_repetition(final_text)
                if is_degenerate and turns < effective_max_turns:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Repetition loop detected ({rep_snippet}). "
                        f"Cleansing history and injecting recovery nudge on turn {turns}/{effective_max_turns}..."
                    )
                    # Cleanse infected assistant message in history to avoid KV-cache poisoning
                    REPETITION_PRUNED_MSG = (
                        "[Analytical narrative truncated due to degenerate repetition loop. "
                        "Proceed directly to final structured decision without repeating narrative.]"
                    )
                    for block in assistant_msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            block["text"] = REPETITION_PRUNED_MSG
                        elif hasattr(block, "text"):
                            setattr(block, "text", REPETITION_PRUNED_MSG)

                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[GUARDRAIL ALERT: Degenerate repetition loop detected and pruned. "
                                "Do NOT repeat previous narrative. Immediately submit your structured analytical verdict using the required tool now.]"
                            ),
                        }
                    )
                    continue

            # ── C1: TRUNCATED TOOL CALL SAFETY ──
            # When LLM hits max output tokens, tool call JSON arguments may be
            # truncated mid-value. Auto-repair JSON can "fix" syntax but produce
            # WRONG values (e.g., stop_loss: 1.08 → 1.0). Refuse all tool calls.
            if self._check_truncation(response, stop_reason):
                length_truncated = True
                tool_use_blocks_check = [
                    b
                    for b in assistant_content
                    if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None))
                    in ("tool_use", "tool_call", "function")
                    or (isinstance(b, dict) and ("function" in b or "tool_call_id" in b))
                    or hasattr(b, "function")
                ]
                if tool_use_blocks_check:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] TRUNCATED RESPONSE (stop_reason={stop_reason}). "
                        f"Refusing {len(tool_use_blocks_check)} tool call(s) — arguments may be malformed."
                    )
                    truncation_error_results = self._fail_truncated_tool_calls(tool_use_blocks_check)
                    current_messages.append({"role": "user", "content": truncation_error_results})
                    tool_calls_made += len(tool_use_blocks_check)
                    logger.info(
                        f"[{stage_name}][AgentHarness] Injected {len(truncation_error_results)} "
                        f"truncation error(s) as tool results for self-correction."
                    )
                    continue  # Next turn — model will re-issue with complete args
                else:
                    if turns < effective_max_turns:
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Narrative truncated by output token limit on turn {turns}. "
                            f"Injecting continuation prompt."
                        )
                        current_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[SYSTEM NOTICE: Your previous narrative was truncated by max_tokens. "
                                    "Continue directly from where you stopped without repeating prior content.]"
                                ),
                            }
                        )
                        continue

            # ── Structured Response Validation (Phase 3) ──
            from monika.application.agent.harness.error_classifier import ErrorClassifier, RecoveryAction

            resp_dict = {
                "stop_reason": stop_reason,
                "content": final_text,
                "tool_calls": [
                    b
                    for b in assistant_content
                    if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
                ],
                "reasoning": reasoning_content or "",
            }
            resp_issue = ErrorClassifier.classify_response(resp_dict)
            if resp_issue and not self._check_truncation(response, stop_reason) and turns < effective_max_turns:
                if resp_issue.recovery in (RecoveryAction.INJECT_NUDGE, RecoveryAction.INJECT_CONTINUATION):
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Response issue detected ({resp_issue.category.value}): injecting recovery nudge."
                    )
                    current_messages.append(
                        {"role": "user", "content": resp_issue.nudge_text or "[System: Please proceed.]"}
                    )
                    continue
                elif resp_issue.recovery == RecoveryAction.RETRY_WITH_REDUCED_EFFORT:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Thinking budget exhausted without content: nudging direct conclusion."
                    )
                    current_messages.append(
                        {
                            "role": "user",
                            "content": "[System: Thinking budget exhausted without answer. Conclude directly.]",
                        }
                    )
                    continue

            # 6. Check Completion & Mandatory Tool Enforcement
            tool_use_blocks = [
                b
                for b in assistant_content
                if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
            ]

            if not (final_text or "").strip() and not tool_use_blocks:
                prov_name = str(getattr(self.llm_client, "provider", "unknown"))
                mdl_name = str(getattr(self.llm_client, "model", "unknown"))
                emp_count = self.empty_response_guard.record_empty_response(
                    prov_name, mdl_name, str(stop_reason or "stop")
                )
                ladder_act = self.empty_response_guard.get_recovery_ladder_action(
                    prov_name,
                    mdl_name,
                    attempt=emp_count,
                    raw_response=reasoning_content or "",
                    task_role=stage_name,
                )
                if turns < effective_max_turns:
                    if ladder_act.action_type == "failover":
                        self._try_fallback_swap(stage_name, RuntimeError(ladder_act.instruction))
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Empty response recovery ladder step {ladder_act.step} "
                        f"({ladder_act.action_type}): {ladder_act.instruction}"
                    )
                    current_messages.append(
                        {"role": "user", "content": f"[SYSTEM RECOVERY DIRECTIVE]: {ladder_act.instruction}"}
                    )
                    continue
                elif not called_tools:
                    unverified_stop_gate_error = (
                        f"Empty response after {emp_count} attempt(s) with zero tool calls ({ladder_act.instruction})"
                    )
            else:
                self.empty_response_guard.record_successful_response(
                    str(getattr(self.llm_client, "provider", "unknown")),
                    str(getattr(self.llm_client, "model", "unknown")),
                )

            if not tool_use_blocks:
                from monika.application.agent.harness.anti_slop_gate import AntiSlopQualityGate
                from monika.application.agent.harness.turn_failure_diagnostics import TurnFailureDiagnosticBuilder

                mandatory_tool = self.get_mandatory_tool_for_stage(stage_name)
                if mandatory_tool and mandatory_tool not in called_tools and turns < effective_max_turns:
                    target_sym = stage_symbol or "this asset"
                    nudge_text = (
                        f"CRITICAL MANDATORY INSTRUCTION: You concluded your turn without invoking '{mandatory_tool}'. "
                        f"You MUST call '{mandatory_tool}' now with your final structured analysis and decision for {target_sym}. "
                        f"Plain text conclusions without invoking '{mandatory_tool}' cannot be processed."
                    )
                    logger.info(
                        f"[{stage_name}][AgentHarness] Mandatory tool '{mandatory_tool}' missing "
                        f"on turn {turns}/{effective_max_turns}. Nudging agent..."
                    )
                    current_messages.append({"role": "user", "content": nudge_text})
                    continue
                elif mandatory_tool and mandatory_tool not in called_tools:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Reached max turns ({effective_max_turns}) "
                        f"without calling mandatory tool '{mandatory_tool}'."
                    )
                turn_state.current_phase = TurnPhase.FINALIZE
                turn_state.stop_gate_context.pending_response = final_text

                # ── Trade Proposal Verification Stop Gate ──
                from monika.application.agent.harness.trade_stop_gates import TradeStopGate

                trade_verdict = TradeStopGate.evaluate(
                    final_text,
                    self.verification_ledger,
                    stage_name=stage_name,
                    stage_symbol=stage_symbol,
                )
                if not trade_verdict.should_stop:
                    if turns < effective_max_turns:
                        logger.info(
                            f"[{stage_name}][AgentHarness] Trade Stop Gate triggered for {trade_verdict.detected_symbol}. "
                            f"Nudging agent for risk/sizing verification..."
                        )
                        current_messages.append({"role": "user", "content": trade_verdict.nudge_text})
                        continue
                    else:
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Reached max turns ({effective_max_turns}) without "
                            f"verified risk sizing. Candidate Preservation: safely downgrading decision to WAIT."
                        )
                        final_text = json.dumps(
                            {
                                "decision": "WAIT",
                                "confidence": 0.0,
                                "rationale": f"Downgraded to defensive WAIT: {trade_verdict.rejection_reason or 'Risk/sizing unverified before turn limit'}",
                                "downgraded_by_stop_gate": True,
                            }
                        )

                # ── Modular Financial & Verification Stop Gates (TradingRiskStopGate + CodeVerifyStopGate) ──
                can_stop_modular, modular_nudge = apply_stop_gates(final_text, turn_state.stop_gate_context)
                if not can_stop_modular and modular_nudge:
                    unverified_stop_gate_error = modular_nudge
                    if turns >= effective_max_turns and _emergency_recovery_turns_used < _max_emergency_recovery_turns:
                        effective_max_turns += 1
                        _emergency_recovery_turns_used += 1
                    if turns < effective_max_turns:
                        diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                            turn_number=turns,
                            gate_name="ModularStopGate",
                            reason=modular_nudge,
                            remaining_turns=max(1, effective_max_turns - turns),
                        )
                        logger.info(f"[{stage_name}][AgentHarness] Modular Stop Gate intercepted: {modular_nudge}")
                        current_messages.append(
                            {"role": "user", "content": f"{modular_nudge}\n\n{diag.format_directive()}"}
                        )
                        continue

                # ── Physical Deliverable Gate (Anti-Hallucination & File Integrity Audit) ──
                deliverable_verdict = self.physical_deliverable_gate.audit_claimed_completion(
                    final_text,
                    touched_files=turn_state.stop_gate_context.mutated_files,
                    ledger=self.verification_ledger,
                )
                if not deliverable_verdict.is_valid and deliverable_verdict.message:
                    unverified_stop_gate_error = deliverable_verdict.message
                    if turns >= effective_max_turns and _emergency_recovery_turns_used < _max_emergency_recovery_turns:
                        effective_max_turns += 1
                        _emergency_recovery_turns_used += 1
                    if turns < effective_max_turns:
                        diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                            turn_number=turns,
                            gate_name="PhysicalDeliverableGate",
                            reason=deliverable_verdict.message,
                            remaining_turns=max(1, effective_max_turns - turns),
                        )
                        logger.info(
                            f"[{stage_name}][AgentHarness] Physical deliverable stop gate intercepted: "
                            f"{deliverable_verdict.message}"
                        )
                        current_messages.append(
                            {"role": "user", "content": f"{deliverable_verdict.message}\n\n{diag.format_directive()}"}
                        )
                        continue

                # ── Interactive TODO List Audit (Ensure no unfinished tasks before exit) ──
                if hasattr(self, "todo_state") and self.todo_state and self.todo_state.has_items():
                    all_done, todo_audit_msg = self.todo_state.audit_completion()
                    if not all_done:
                        unverified_stop_gate_error = f"Unfinished TODO items: {todo_audit_msg}"
                        if (
                            turns >= effective_max_turns
                            and _emergency_recovery_turns_used < _max_emergency_recovery_turns
                        ):
                            effective_max_turns += 1
                            _emergency_recovery_turns_used += 1
                        if turns < effective_max_turns:
                            diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                                turn_number=turns,
                                gate_name="InteractiveTodoAudit",
                                reason=todo_audit_msg,
                                remaining_turns=max(1, effective_max_turns - turns),
                            )
                            logger.info(
                                f"[{stage_name}][AgentHarness] Active TODOs incomplete: {todo_audit_msg}. "
                                f"Nudging agent on turn {turns}/{effective_max_turns}..."
                            )
                            current_messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"[CRITICAL TODO AUDIT]: You have unfinished items in your TODO list:\n"
                                        f"{todo_audit_msg}\n"
                                        f"Please finish the in-progress tasks or mark them completed/cancelled using 'todo_write'.\n\n"
                                        f"{diag.format_directive()}"
                                    ),
                                }
                            )
                            continue

                # ── Anti-Slop Quality Gate (Enforce Professional Zero-Slop Output) ──
                if final_text and len(final_text.strip()) >= 80:
                    slop_verdict = AntiSlopQualityGate.evaluate(
                        final_text,
                        stage_name=stage_name,
                        require_quantitative_grounding=False,
                    )
                    if not slop_verdict.passed:
                        if turns < effective_max_turns:
                            diag = TurnFailureDiagnosticBuilder.from_slop_rejection(
                                turn_number=turns,
                                violations=slop_verdict.violations,
                                stage_name=stage_name,
                            )
                            logger.info(
                                f"[{stage_name}][AgentHarness] AntiSlopQualityGate intercepted final response on turn {turns}: "
                                f"{slop_verdict.violations}"
                            )
                            current_messages.append({"role": "user", "content": diag.format_directive()})
                            continue
                        else:
                            final_text = AntiSlopQualityGate.sanitize_surface_slop(final_text)

                if (
                    can_stop_modular
                    and deliverable_verdict.is_valid
                    and (
                        not hasattr(self, "todo_state")
                        or not self.todo_state
                        or not self.todo_state.has_items()
                        or self.todo_state.audit_completion()[0]
                    )
                    and ((final_text or "").strip() or called_tools)
                ):
                    unverified_stop_gate_error = None

                logger.info(
                    f"[{stage_name}][AgentHarness] Agent completed in {turns} turns with "
                    f"{tool_calls_made} tool executions."
                )

                # ── Dual-Queue Follow-Up Processing ──
                if self._follow_up_queue:
                    if turns >= effective_max_turns:
                        effective_max_turns += 1
                    f_msg = self._follow_up_queue.popleft()
                    logger.info(f"[{stage_name}][AgentHarness] Draining follow-up directive from '{f_msg.sender}'.")
                    current_messages.append(
                        {"role": "user", "content": f"[{f_msg.sender.upper()} FOLLOW-UP TASK]: {f_msg.content}"}
                    )
                    continue

                break

            # ── C1: PERSIST-BEFORE-EXECUTE INVARIANT ──
            # Persist assistant turn and its tool calls to durable event store BEFORE executing tools
            cycle_id = kwargs.get("cycle_id", "")
            await self._persist_assistant_turn(
                session=session,
                messages=current_messages,
                turn_index=turns,
                stage_name=stage_name,
                cycle_id=cycle_id,
            )

            # 7. Segmented Tool Execution with Auto-Repair, Progressive Anti-Oscillation, and Mixed Batch Fault Tolerance
            planner = ToolBatchPlanner(registry=getattr(executor, "registry", None))

            prepared_calls = []
            for block in tool_use_blocks:
                raw_name = (
                    str(block.get("name") or "") if isinstance(block, dict) else str(getattr(block, "name", "") or "")
                )
                raw_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                t_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", "")

                t_name = repair_tool_name(raw_name)
                t_input = repair_tool_arguments(raw_input)
                call_item = {
                    "id": t_id,
                    "name": t_name,
                    "raw_name": raw_name,
                    "input": t_input,
                }

                # ── M5: Tool Schema Validation ──
                tool_schema_fn = getattr(executor, "get_tool_schema", None)
                tool_schema = None
                if callable(tool_schema_fn) and not inspect.iscoroutinefunction(tool_schema_fn):
                    res = tool_schema_fn(t_name)
                    if isinstance(res, dict):
                        tool_schema = res
                if tool_schema and isinstance(tool_schema, dict) and tool_schema.get("input_schema"):
                    input_schema = tool_schema["input_schema"]
                    coerce_tool_arguments(t_input, input_schema)
                    schema_err = None

                    try:
                        import jsonschema

                        jsonschema.validate(instance=t_input, schema=input_schema)
                    except ImportError:
                        req = input_schema.get("required", [])
                        missing = [r for r in req if r not in t_input]
                        if missing:
                            schema_err = f"missing required fields {missing}"
                    except Exception as ve:
                        schema_err = getattr(ve, "message", str(ve))

                    if schema_err:
                        healed = deep_repair_tool_arguments(
                            t_name,
                            t_input,
                            input_schema,
                            schema_err,
                            assistant_text=final_text or "",
                        )
                        if healed:
                            logger.info(
                                f"[{stage_name}][AgentHarness] Auto-healed schema validation error for {t_name} "
                                f"(previously: {schema_err})"
                            )
                            schema_err = None
                        else:
                            from monika.application.agent.harness.turn_failure_diagnostics import (
                                TurnFailureDiagnosticBuilder,
                            )

                            diag = TurnFailureDiagnosticBuilder.from_schema_validation_error(
                                turn_number=turns,
                                tool_name=t_name,
                                tool_input=t_input if isinstance(t_input, dict) else {},
                                error_msg=str(schema_err),
                                schema=input_schema,
                            )
                            logger.warning(f"[{stage_name}] Schema validation failed for {t_name}: {schema_err}")
                            call_item["_schema_error"] = {
                                "type": "tool_result",
                                "tool_use_id": t_id,
                                "name": t_name,
                                "content": json.dumps(
                                    {
                                        "status": "schema_validation_error",
                                        "error": f"Invalid arguments for {t_name}: {schema_err}. Fix and re-call.",
                                        "expected_schema": diag.expected_schema_summary,
                                        "diagnostic_directive": diag.format_directive(),
                                        "_turn_failure_diagnostic": diag.to_dict(),
                                    }
                                ),
                                "is_error": True,
                            }
                prepared_calls.append(call_item)

            # Prune empty duplicate submission calls if a substantive submission call exists in the same batch
            submission_tools = {"submit_fundamental_brief", "submit_asset_analysis"}
            for sub_tool in submission_tools:
                sub_calls = [c for c in prepared_calls if c["name"] == sub_tool]
                if len(sub_calls) > 1:
                    has_substantive = any(len(c.get("input", {})) > 1 for c in sub_calls)
                    if has_substantive:
                        for c in sub_calls:
                            if len(c.get("input", {})) <= 1:
                                c["_superseded"] = True

            async def _execute_single_prepared_tool(call_item: dict) -> dict:
                nonlocal tool_calls_made, consecutive_tool_sig, repeated_tool_count
                c_name = call_item["name"]
                c_input = call_item["input"]
                c_id = call_item["id"]
                needs_repeat_advisory = False

                # Check if call was superseded by another parallel call
                if call_item.get("_superseded"):
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps(
                            {
                                "status": "superseded",
                                "notice": "Duplicate/empty submission call superseded by substantive parallel submission in the same turn.",
                            }
                        ),
                        "is_error": False,
                    }

                # Final Turn Read Tools Lockdown: force agent to submit on final turn
                terminal_tool = (
                    "submit_fundamental_brief"
                    if ("fundamental" in stage_name.lower() or "stage1" in stage_name.lower())
                    else (
                        "submit_asset_analysis"
                        if ("asset" in stage_name.lower() or "stage2" in stage_name.lower())
                        else None
                    )
                )
                if turns >= effective_max_turns and terminal_tool and c_name != terminal_tool:
                    if c_name.startswith(("get_", "read_", "search_", "inspect_", "diff_")):
                        tool_calls_made += 1
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Final turn read tool lockdown: blocked '{c_name}'. Forcing '{terminal_tool}'."
                        )
                        return {
                            "type": "tool_result",
                            "tool_use_id": c_id,
                            "name": c_name,
                            "content": json.dumps(
                                {
                                    "status": "read_tools_disabled",
                                    "error": f"Read tools are strictly disabled on final turn {turns}/{effective_max_turns}. You MUST call '{terminal_tool}' immediately with your synthesized analysis.",
                                }
                            ),
                            "is_error": True,
                        }

                # Check if schema validation preflight failed
                if call_item.get("_schema_error"):
                    tool_calls_made += 1
                    if c_name not in ("submit_fundamental_brief", "submit_asset_analysis"):
                        self.guardrail_controller.record_denial()
                    return call_item["_schema_error"]

                # Unified Tool Guardrails (Monotonic Risk, Read-Before-Act, Sizing, Turn Cap, Anti-Oscillation)
                guard_ctx = dict(kwargs)
                if prefetch_satisfied_tools:
                    guard_ctx["prefetch_satisfied_tools"] = prefetch_satisfied_tools
                guard_verdict = self.guardrail_controller.validate_tool_call(c_name, c_input, context=guard_ctx)
                if not guard_verdict.allowed:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Guardrail blocked '{c_name}' ({guard_verdict.guard_name}): {guard_verdict.reason}"
                    )
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    if guard_verdict.action in ("reject", "nudge"):
                        if c_name not in ("submit_fundamental_brief", "submit_asset_analysis"):
                            self.guardrail_controller.record_denial()
                    status_val = (
                        "already_executed"
                        if guard_verdict.guard_name == "AntiOscillationGuard"
                        else f"guardrail_{guard_verdict.action}"
                    )
                    guard_payload: Dict[str, Any] = {
                        "status": status_val,
                        "guard": guard_verdict.guard_name,
                        "notice" if guard_verdict.action == "suppress" else "error": guard_verdict.reason,
                        "suggested_fix": guard_verdict.suggested_fix,
                    }
                    if guard_verdict.action in ("reject", "nudge"):
                        from monika.application.agent.harness.turn_failure_diagnostics import (
                            TurnFailureDiagnosticBuilder,
                        )

                        guard_diag = TurnFailureDiagnosticBuilder.from_guardrail_verdict(
                            turn_number=turns,
                            tool_name=c_name,
                            guard_name=guard_verdict.guard_name,
                            reason=guard_verdict.reason,
                            suggested_fix=guard_verdict.suggested_fix,
                        )
                        guard_payload["diagnostic_directive"] = guard_diag.format_directive()
                        guard_payload["_turn_failure_diagnostic"] = guard_diag.to_dict()
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps(guard_payload),
                        "is_error": guard_verdict.action in ("reject", "nudge"),
                    }

                # a. Progressive Anti-Oscillation Loop Guard (Hash-based + Sliding Window)
                suppress_threshold = int(self.settings.get("repeat_tool_suppress_threshold", 2))
                call_sig = self.compute_tool_signature(c_name, c_input)
                total_sig_counts[call_sig] = total_sig_counts.get(call_sig, 0) + 1

                if call_sig == consecutive_tool_sig:
                    repeated_tool_count += 1
                else:
                    consecutive_tool_sig = call_sig
                    repeated_tool_count = 1

                recent_repeats = sliding_window_sigs.count(call_sig)

                # Format canonical JSON-sorted arguments for deterministic tracking & reminders
                try:
                    canonical_args = json.dumps(c_input, sort_keys=True)
                except Exception:
                    canonical_args = str(c_input)

                is_hard_suppressed = (
                    repeated_tool_count >= suppress_threshold
                    or recent_repeats >= suppress_threshold
                    or total_sig_counts[call_sig] >= (suppress_threshold + 1)
                )

                if is_hard_suppressed:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Anti-Oscillation: Suppressing repeated call for '{c_name}' "
                        f"(consecutive={repeated_tool_count}, recent={recent_repeats}, total={total_sig_counts[call_sig]})"
                    )
                    suppressed_result = {
                        "status": "already_executed",
                        "notice": (
                            f"Tool '{c_name}' with identical parameters was already executed {repeated_tool_count} time(s). "
                            f"Arguments: {canonical_args}. "
                            f"Do not repeat identical calls. Synthesize data already collected and conclude analysis."
                        ),
                    }
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps(suppressed_result),
                    }

                needs_repeat_advisory = (
                    repeated_tool_count >= 2 or recent_repeats >= 1 or total_sig_counts[call_sig] >= 2
                )

                sliding_window_sigs.append(call_sig)

                # b. Tool Family Quota Enforcement
                allowed, quota_warn = self.compactor.check_tool_family_quota(c_name, list(called_tools))
                if not allowed:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Tool Family Quota Exceeded for '{c_name}': {quota_warn}"
                    )
                    suppressed_result = {"status": "quota_exceeded", "notice": quota_warn}
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps(suppressed_result),
                    }

                # ── Trade Proposal Verification Stop Gate & Anti-Laziness Interception ──
                if c_name == "submit_asset_analysis":
                    target_sym = c_input.get("symbol") or stage_symbol
                    decision = str(c_input.get("decision") or "").upper()

                    # 1. Anti-laziness on Turn 1: WAIT cannot be submitted without inspecting technical structure or price action
                    if turns == 1 and decision in ("WAIT", "HOLD", "NEUTRAL", "PASS", "NO_TRADE"):
                        inspection_tools = {
                            "get_smc_zones",
                            "get_structure_breaks",
                            "get_price_history",
                            "get_indicator_snapshot",
                            "get_mt5_bars",
                            "get_atr",
                            "get_swing_points",
                        }

                        def _normalize_inspection_name(t_name: str) -> str:
                            name = re.sub(r"_(?:M15|M30|H1|H4|D1|W1|MN|recent)$", "", str(t_name))
                            if name.startswith("price_history"):
                                return "get_price_history"
                            if name.startswith("smc_zones"):
                                return "get_smc_zones"
                            if name.startswith("structure_breaks"):
                                return "get_structure_breaks"
                            if name.startswith("indicator_snapshot") or name.startswith("technical_indicators"):
                                return "get_indicator_snapshot"
                            if name.startswith("swing_points"):
                                return "get_swing_points"
                            if name.startswith("atr"):
                                return "get_atr"
                            if name.startswith("mt5_bars") or name.startswith("multi_timeframe_candles"):
                                return "get_mt5_bars"
                            if not name.startswith("get_") and f"get_{name}" in inspection_tools:
                                return f"get_{name}"
                            return name

                        raw_inspected = set(called_tools) | set(prefetch_satisfied_tools or [])
                        all_inspected_tools = {_normalize_inspection_name(t) for t in raw_inspected} | raw_inspected
                        if not any(t in all_inspected_tools for t in inspection_tools):
                            logger.warning(
                                f"[{stage_name}][AgentHarness] Anti-laziness: blocked premature WAIT on turn 1 without technical inspection."
                            )
                            tool_calls_made += 1
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "content": json.dumps(
                                    {
                                        "status": "anti_laziness_nudge",
                                        "error": (
                                            "Cannot conclude WAIT on turn 1 without inspecting technical structure or price action. "
                                            "You must call get_smc_zones, get_structure_breaks, or get_price_history first."
                                        ),
                                    }
                                ),
                                "is_error": True,
                            }

                    # 2. Risk Verification Evidence Check for BUY/SELL
                    if decision in ("BUY", "SELL", "LONG", "SHORT"):
                        if not self.verification_ledger.has_passed_evidence(target_sym):
                            logger.warning(
                                f"[{stage_name}][AgentHarness] submit_asset_analysis ({decision} {target_sym}) "
                                f"BLOCKED: No passing verification evidence in ledger."
                            )
                            tool_calls_made += 1
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "content": json.dumps(
                                    {
                                        "status": "blocked_by_stop_gate",
                                        "error": (
                                            f"Trade proposal ({decision} {target_sym}) blocked by TradeStopGate: "
                                            f"No passing calculate_position_size or validate_risk_limits evidence recorded in ledger. "
                                            f"You MUST call calculate_position_size with exact stop_loss and take_profit parameters first."
                                        ),
                                    }
                                ),
                                "is_error": True,
                            }

                        # 2b. Verify parameter integrity (entry/SL/TP/lot must match verified sizing evidence)
                        prop_sl = None
                        prop_entry = None
                        prop_tp = None
                        prop_lot = None
                        try:
                            if "stop_loss" in c_input:
                                prop_sl = float(c_input["stop_loss"])
                            if "take_profit" in c_input:
                                prop_tp = float(c_input["take_profit"])
                            if "entry" in c_input or "entry_price" in c_input:
                                prop_entry = float(c_input.get("entry") or c_input.get("entry_price"))
                            entry_cond = c_input.get("entry_condition")
                            if (
                                prop_entry is None
                                and isinstance(entry_cond, dict)
                                and entry_cond.get("price") is not None
                            ):
                                prop_entry = float(entry_cond["price"])
                            raw_lot = c_input.get("lot_size") or c_input.get("lots") or c_input.get("volume")
                            if raw_lot is not None:
                                prop_lot = float(raw_lot)
                        except ValueError, TypeError:
                            pass

                        is_intact, integrity_err = self.verification_ledger.verify_proposal_integrity(
                            target_sym,
                            entry_price=prop_entry,
                            stop_loss=prop_sl,
                            take_profit=prop_tp,
                            lot_size=prop_lot,
                        )
                        if not is_intact:
                            logger.warning(
                                f"[{stage_name}][AgentHarness] submit_asset_analysis ({decision} {target_sym}) "
                                f"BLOCKED: Parameter integrity check failed: {integrity_err}"
                            )
                            tool_calls_made += 1
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "name": c_name,
                                "content": json.dumps(
                                    {
                                        "status": "blocked_by_parameter_integrity",
                                        "error": f"Trade proposal blocked: {integrity_err}",
                                    }
                                ),
                                "is_error": True,
                            }

                # c. Dynamic Execution via ToolExecutor with OpenTelemetry Tool Span and Plugin Hooks
                from monika.application.agent.estop import is_estop_active

                if is_estop_active():
                    logger.critical(
                        f"[{stage_name}][AgentHarness] ESTOP detected before executing tool '{c_name}'. Aborting tool execution."
                    )
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps({"error": "ESTOP is active. All tool executions are halted."}),
                        "is_error": True,
                    }

                # Persist-before-execute: record tool intent before touching broker/external state
                await self._log_tool_call(session, stage_name, c_name, c_input, {"status": "PENDING_EXECUTION"})

                tool_calls_made += 1
                called_tools.add(c_name)

                # Read-only tool check via ReadOnlyReplayCache
                # Financial Invariant: Real-time price quotes, order books, and account positions MUST NOT be cached.
                REALTIME_FINANCIAL_TOOLS = {
                    "get_market_quote",
                    "get_open_positions",
                    "get_account_info",
                    "get_ticks",
                    "get_rate",
                    "get_tick",
                }
                is_read_tool = (
                    c_name.startswith(("get_", "fetch_", "calc_", "calculate_"))
                    and c_name not in REALTIME_FINANCIAL_TOOLS
                )
                res_obj = None
                if is_read_tool:
                    cached_val = self.replay_cache.get(c_name, c_input)
                    if cached_val is not None:
                        logger.info(f"[{stage_name}][AgentHarness] ReadOnlyReplayCache HIT for '{c_name}'")
                        res_obj = cached_val

                if res_obj is None:
                    try:
                        from monika.application.plugins.manager.manager import PluginHook, get_plugin_manager

                        plugin_mgr = get_plugin_manager()
                        await plugin_mgr.emit(
                            PluginHook.PRE_TOOL_CALL, tool_name=c_name, args=c_input, stage_name=stage_name
                        )

                        from monika.core.telemetry.tracing.spans import tool_span

                        with tool_span(c_name, symbol=stage_symbol):
                            res_obj = await executor.execute(c_name, c_input)

                        await plugin_mgr.emit(
                            PluginHook.POST_TOOL_CALL,
                            tool_name=c_name,
                            args=c_input,
                            result=res_obj,
                            stage_name=stage_name,
                        )
                        if is_read_tool and isinstance(res_obj, dict) and "error" not in res_obj:
                            self.replay_cache.put(c_name, c_input, res_obj)
                    except Exception as ex:
                        logger.error(f"[{stage_name}][AgentHarness] Tool execution exception in '{c_name}': {ex}")
                        res_obj = {"error": f"Tool execution failed: {str(ex)}", "tool": c_name}

                await self._log_tool_call(session, stage_name, c_name, c_input, res_obj)
                self.guardrail_controller.record_tool_call(c_name, c_input, res_obj)
                is_tool_err = bool(
                    isinstance(res_obj, dict)
                    and (
                        bool(res_obj.get("error"))
                        or res_obj.get("status") in ("error", "failed", "rejected", "blocked", "validation_error")
                        or res_obj.get("valid") is False
                    )
                )
                if not is_tool_err:
                    self.guardrail_controller.record_success()
                self.stall_guard.record_call(c_name, res_obj, turn_idx=turns)
                self.verification_ledger.record_tool_execution(c_name, c_input, res_obj)

                if is_tool_err and isinstance(res_obj, dict) and "_turn_failure_diagnostic" not in res_obj:
                    from monika.application.agent.harness.turn_failure_diagnostics import (
                        TurnFailureDiagnosticBuilder,
                    )

                    err_msg_val = str(
                        res_obj.get("error")
                        or res_obj.get("errors")
                        or res_obj.get("message")
                        or res_obj.get("reason")
                        or res_obj.get("status")
                        or "Tool execution failed"
                    )
                    err_diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
                        turn_number=turns,
                        tool_name=c_name,
                        tool_input=c_input if isinstance(c_input, dict) else {},
                        error_msg=err_msg_val,
                    )
                    res_obj = dict(res_obj)
                    res_obj["_turn_failure_diagnostic"] = err_diag.to_dict()
                    res_obj.setdefault("diagnostic_directive", err_diag.format_directive())

                if c_name == "load_tool_category" and isinstance(res_obj, dict):
                    new_schemas = res_obj.get("schemas", [])
                    if isinstance(new_schemas, list):
                        existing_names = {str(t.get("name", "")) for t in active_tools}
                        for sch in new_schemas:
                            if isinstance(sch, dict) and str(sch.get("name", "")) not in existing_names:
                                active_tools.append(dict(sch))
                                existing_names.add(str(sch.get("name", "")))
                        active_tools.sort(key=lambda t: str(t.get("name", "")))

                if c_name in (
                    "patch_source_file",
                    "write_source_file",
                    "edit_file",
                    "apply_file_patch",
                    "create_file",
                ):
                    target_file = (
                        c_input.get("filepath") or c_input.get("path") or c_input.get("filename") or c_input.get("file")
                    )
                    if target_file:
                        turn_state.stop_gate_context.mutated_files.append(str(target_file))
                    turn_state.stop_gate_context.has_unverified_file_edits = True

                if c_name in (
                    "run_verification_gate",
                    "verify_syntax",
                    "run_terminal_command",
                    "execute_code",
                    "run_command",
                ):
                    cmd_str = str(c_input.get("command") or c_input.get("cmd") or "").strip().lower()
                    is_trivial_echo = c_name in ("run_terminal_command", "run_command") and (
                        cmd_str in ("true", "echo", "echo ok", "rem") or cmd_str.startswith("echo ")
                    )
                    rc_ok = not is_tool_err and (
                        not isinstance(res_obj, dict)
                        or (res_obj.get("returncode", 0) == 0 and res_obj.get("exit_code", 0) == 0)
                    )
                    if rc_ok and not is_trivial_echo:
                        turn_state.stop_gate_context.verification_commands_run.append(c_name)
                        turn_state.stop_gate_context.has_unverified_file_edits = False

                if c_name in ("propose_action", "propose_trade"):
                    turn_state.stop_gate_context.proposed_actions.append(c_input)
                    turn_state.stop_gate_context.has_unregistered_trade_proposals = False

                # Disk spillover check for payload > 16KB to prevent context window bloat and JSON truncation
                try:
                    from monika.application.analysis.tools.tool_result_storage import get_tool_result_storage

                    res_obj, was_spilled = get_tool_result_storage().maybe_persist(c_name, c_input, res_obj)
                except Exception as e:
                    logger.debug(f"[AgentHarness] Tool result spillover check error: {e}")

                # Format tool result block with validation and micro-pruning
                try:
                    from monika.core.validation.tool_response_validator import ToolResponseValidator

                    sanitized_result, is_valid, warning = ToolResponseValidator.validate_and_sanitize(c_name, res_obj)
                    if not is_valid:
                        error_context = ToolResponseValidator.build_error_context(c_name, warning)
                        tool_res_content = (
                            json.dumps(sanitized_result, default=str)
                            if not isinstance(sanitized_result, str)
                            else sanitized_result
                        ) + error_context
                    else:
                        tool_res_content = (
                            json.dumps(sanitized_result, ensure_ascii=False, default=str)
                            if not isinstance(sanitized_result, str)
                            else sanitized_result
                        )
                except Exception:
                    tool_res_content = json.dumps(res_obj, default=str) if not isinstance(res_obj, str) else res_obj

                tool_res_content = self.compactor.micro_prune(tool_res_content, tool_name=c_name)

                # ── Zero-Cost Lossless Structural Tool Output Pruning ──
                general_prune_tools = frozenset(
                    {
                        "run_command",
                        "run_terminal_command",
                        "execute_code",
                        "bash",
                        "terminal",
                        "read_file",
                        "search_files",
                        "grep",
                        "git_status",
                        "git_diff",
                        "git_log",
                        "web_search",
                        "scrape_url",
                        "read_url",
                    }
                )
                general_max_chars = int(self.settings.get("general_tool_max_chars", 2500))
                if c_name in general_prune_tools and len(tool_res_content) > general_max_chars:
                    if isinstance(res_obj, (dict, list)):
                        tool_res_content = self.general_tool_pruner.prune_json(
                            res_obj, max_chars=general_max_chars, tool_name=c_name
                        )
                    else:
                        tool_res_content = self.general_tool_pruner.prune_text(
                            tool_res_content, max_chars=general_max_chars, tool_name=c_name
                        )
                elif len(tool_res_content) > 16000:
                    if isinstance(res_obj, (dict, list)):
                        tool_res_content = self.general_tool_pruner.prune_json(
                            res_obj, max_chars=16000, tool_name=c_name
                        )
                    else:
                        tool_res_content = self.general_tool_pruner.prune_text(
                            tool_res_content, max_chars=16000, tool_name=c_name
                        )

                # ── Generation-Tracked Data Fetch Deduplication ──
                dedup_notice = self.data_dedup.check_and_record(c_name, c_input, tool_res_content)
                if dedup_notice:
                    tool_res_content = dedup_notice

                # ── Untrusted Content Isolation & Threat Scanning ──
                untrusted_tools = frozenset(
                    {
                        "get_news_items",
                        "get_news_digest",
                        "get_retail_sentiment",
                        "get_social_sentiment",
                        "web_search",
                        "get_cot_report",
                        "scrape_url",
                        "get_forex_sentiment",
                        "get_fxssi_sentiment",
                        "get_structured_sentiment",
                    }
                )
                if c_name in untrusted_tools:
                    try:
                        from monika.core.security.prompt_injection_scanner import PromptInjectionScanner

                        tool_res_content = PromptInjectionScanner.sanitize_or_block(tool_res_content, source=c_name)
                    except Exception as ex:
                        logger.warning(f"Prompt injection scanner failed for '{c_name}': {ex}. Quarantining content.")
                        tool_res_content = f"[SECURITY WARNING: External content from '{c_name}' quarantined due to safety scanner exception]"
                    tool_res_content = (
                        f'<untrusted_external_content source="{c_name}">\n'
                        f"{tool_res_content}\n"
                        f"</untrusted_external_content>"
                    )

                if needs_repeat_advisory:
                    if repeated_tool_count >= 5 or total_sig_counts.get(call_sig, 0) >= 5:
                        advisory_note = (
                            f"\n\n[STRONG WARNING: Tool '{c_name}' has been executed {repeated_tool_count} times "
                            f"with identical arguments: {canonical_args}. This indicates an unproductive loop. "
                            f"You MUST shift strategies or synthesize your findings now.]"
                        )
                    elif repeated_tool_count >= 3 or total_sig_counts.get(call_sig, 0) >= 3:
                        advisory_note = (
                            f"\n\n[REFLECTION ADVISORY: Tool '{c_name}' has been invoked {repeated_tool_count} times "
                            f"with these exact arguments. Reflect on whether new information is being gained.]"
                        )
                    else:
                        advisory_note = (
                            f"\n\n[ADVISORY REMINDER: Tool '{c_name}' with identical parameters was already called previously. "
                            f"Avoid redundant calls. Synthesize collected data and conclude.]"
                        )
                    tool_res_content = f"{tool_res_content}{advisory_note}"

                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": tool_res_content,
                    "is_error": is_tool_err,
                }

            # Plan segments into [Parallel Safe] -> [Barrier] -> [Parallel Safe]
            tool_results = []
            segments = planner.plan_segments(prepared_calls)
            for seg_type, batch in segments:
                if seg_type == "parallel" and len(batch) > 1:
                    raw_results = await asyncio.gather(
                        *[_execute_single_prepared_tool(tc) for tc in batch], return_exceptions=True
                    )
                    for idx, res in enumerate(raw_results):
                        if isinstance(res, Exception):
                            tc = batch[idx]
                            logger.error(f"[{stage_name}][AgentHarness] Parallel tool {tc.get('name')} failed: {res}")
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tc.get("id", ""),
                                    "content": json.dumps({"status": "execution_error", "error": str(res)}),
                                    "is_error": True,
                                }
                            )
                        else:
                            tool_results.append(res)
                else:
                    for tc in batch:
                        try:
                            res = await _execute_single_prepared_tool(tc)
                            tool_results.append(res)
                        except Exception as ex:
                            logger.error(f"[{stage_name}][AgentHarness] Sequential tool {tc.get('name')} failed: {ex}")
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tc.get("id", ""),
                                    "content": json.dumps({"status": "execution_error", "error": str(ex)}),
                                    "is_error": True,
                                }
                            )

            # Append tool observations as next turn user message
            current_messages.append({"role": "user", "content": tool_results})

            # 7b. Penultimate Turn Forcing Directive: lock read tools and mandate terminal submission
            terminal_sub_tool = (
                "submit_fundamental_brief"
                if ("fundamental" in stage_name.lower() or "stage1" in stage_name.lower())
                else (
                    "submit_asset_analysis"
                    if ("asset" in stage_name.lower() or "stage2" in stage_name.lower())
                    else None
                )
            )
            if terminal_sub_tool and terminal_sub_tool not in called_tools and turns == effective_max_turns - 1:
                forcing_directive = (
                    f"\n\n[CRITICAL MANDATORY INSTRUCTION — TURN BUDGET LIMIT REACHED]:\n"
                    f"You are on turn {turns}/{effective_max_turns}. You have gathered more than sufficient market data.\n"
                    f"All additional read tools are now LOCKED.\n"
                    f"On your NEXT step, you MUST invoke '{terminal_sub_tool}' with your complete synthesis.\n"
                    f"Do NOT call any more get_* or read_* tools."
                )
                if isinstance(current_messages[-1].get("content"), list):
                    current_messages[-1]["content"].append({"type": "text", "text": forcing_directive})
                elif current_messages:
                    current_messages[-1]["content"] = f"{current_messages[-1].get('content', '')}{forcing_directive}"
                logger.info(
                    f"[{stage_name}][AgentHarness] Injected Penultimate Turn Forcing Directive for '{terminal_sub_tool}' on turn {turns}/{effective_max_turns}."
                )

            # 8. State-Aware Stall Guard Check (H-8)
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
                        current_messages[-1]["content"] = f"{last_content or ''}\n\n[STALL GUARD WARNING]: {stall_msg}"

            # I7: PTC Iteration Budget Refund
            # If sole tool call was execute_analysis_code, refund the iteration
            # because the LLM delegated work to local Python execution
            # P0-10: Cap PTC refunds at 3 to prevent infinite loops
            if len(prepared_calls) == 1 and prepared_calls[0].get("name") == "execute_analysis_code":
                if ptc_refund_count < 3:
                    turns -= 1
                    ptc_refund_count += 1
                    logger.debug(
                        f"[{stage_name}][AgentHarness] PTC budget refund ({ptc_refund_count}/3): turn not counted"
                    )
                else:
                    logger.warning(f"[{stage_name}][AgentHarness] PTC budget refund cap reached ({ptc_refund_count}/3)")

        if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(self.llm_client, "_save_token_usage"):
            try:
                await self.llm_client._save_token_usage(
                    model_name=getattr(self.llm_client, "model", "unknown"),
                    task_name=stage_name,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    session=session,
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
