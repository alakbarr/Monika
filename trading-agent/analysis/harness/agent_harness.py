"""
File: trading-agent/analysis/harness/agent_harness.py

Unified Pi-Pattern Multi-Turn ReAct Agent Harness.
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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, cast

from collections import deque
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.tool_executor import ToolExecutor
from utils.llm.context_compaction import ContextCompactionEngine
from analysis.harness.tool_batch_planner import ToolBatchPlanner
from analysis.harness.tool_repair import repair_tool_name, repair_tool_arguments
from logging_observability.tracing.spans import llm_span

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
        from analysis.providers.pricing_catalog import cost_usd
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
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"] + cached_tokens * rates["cache_read"]) / 1_000_000.0
        return round(cost, 6)


class AgentHarness:
    """
    Unified ReAct Agent Execution Harness (Pi Pattern).
    Provides provider-agnostic multi-turn execution with comprehensive guardrails.
    """

    def __init__(
        self,
        llm_client: Any,
        settings: Optional[dict] = None,
        max_tool_turns: int = 15,
        max_context_chars: int = 500000,
        db_session: Optional[AsyncSession] = None,
    ):
        """
        Initialize the Agent Harness.
        
        Args:
            llm_client: Underlying LLM client implementing run_tool_agent(messages, tools, system_prompt).
            settings: Global system configuration dictionary.
            max_tool_turns: Maximum allowed ReAct turns before forcing termination.
            max_context_chars: Maximum character budget before context trimming kicks in.
            db_session: Optional SQLAlchemy AsyncSession for pre-execute turn persistence.
        """
        self.llm_client = llm_client
        self.settings = settings or {}
        self.max_tool_turns = max_tool_turns
        self.max_context_chars = max_context_chars
        self.db_session = db_session
        self.compactor = ContextCompactionEngine(self.settings)
        from analysis.tools.tool_guardrails import ToolGuardrailController
        self.guardrail_controller = ToolGuardrailController(self.settings)
        from analysis.harness.context_compressor import ContextCompressor
        self.context_compressor = ContextCompressor(self.settings)
        from analysis.harness.stall_guard import StallGuard
        self.stall_guard = StallGuard(
            warning_threshold=self.settings.get("stall_warning_threshold", 4),
            force_terminate_threshold=self.settings.get("stall_terminate_threshold", 7),
        )
        from utils.llm.data_dedup import DataFetchDeduplicator
        self.data_dedup = DataFetchDeduplicator()
        from analysis.harness.verification_evidence_ledger import VerificationEvidenceLedger
        self.verification_ledger = VerificationEvidenceLedger()

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
        if any(marker in err_str for marker in ("rate limit", "too many requests", "429", "timeout", "timed out", "overloaded", "529", "connection error", "temporarily unavailable")):
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
        if any(marker in err_str for marker in ("credit balance is too low", "insufficient credits", "insufficient_quota", "exceeded your current quota", "billing")):
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
            results.append({
                "type": "tool_result",
                "tool_use_id": str(t_id),
                "content": json.dumps({
                    "status": "refused_truncated_response",
                    "error": (
                        "[SYSTEM ERROR] Your previous response was truncated by the output token limit. "
                        "Tool call arguments are likely incomplete/corrupted and were NOT executed. "
                        "Reduce your reasoning length and re-issue the tool call with fewer tools or shorter arguments. "
                        "Do NOT repeat the same call verbatim."
                    ),
                }),
                "is_error": True,
            })
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
            from database.event_store import TradingEventStore

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
            logger.debug(f"[{stage_name}][AgentHarness] Persisted pre-execute turn {turn_index} with {len(tool_calls)} tool calls.")
        except Exception as e:
            logger.warning(f"[{stage_name}][AgentHarness] Failed to persist pre-execute turn: {e}")

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
            repaired.append({
                "role": "user",
                "content": "[System: Begin analysis.]",
            })
        repaired.append(dict(messages[0]))

        for i in range(1, len(messages)):
            curr = dict(messages[i])
            prev = repaired[-1]

            curr_role = curr.get("role")
            prev_role = prev.get("role")

            if curr_role == "assistant" and prev_role == "assistant":
                repaired.append({
                    "role": "user",
                    "content": "[System: Continue with your analysis.]",
                })
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
                raise ValueError("Invalid OpenAI response: 'choices' is empty or None")
            choice = response.choices[0]
            stop_reason = getattr(choice, "finish_reason", "") or "end_turn"
            msg = getattr(choice, "message", None)
            if not msg:
                raise ValueError("Invalid OpenAI response: choice 'message' is None")

            content_text = getattr(msg, "content", None)
            if content_text:
                assistant_blocks.append({"type": "text", "text": str(content_text)})

            reasoning_content = getattr(msg, "reasoning_content", getattr(msg, "reasoning", None))

            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                fn_name = getattr(fn, "name", "") if fn else ""
                raw_args = getattr(fn, "arguments", {}) if fn else {}
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except Exception:
                        parsed_args = {}
                else:
                    parsed_args = raw_args or {}

                tc_id = getattr(tc, "id", f"call_{fn_name}")
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": str(tc_id),
                    "name": str(fn_name),
                    "input": parsed_args
                })

        # Case 2: Anthropic Message or MockResponse (has content list)
        elif has_content:
            stop_reason = getattr(response, "stop_reason", "") or "end_turn"
            raw_content = response.content
            if isinstance(raw_content, list):
                for b in raw_content:
                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                    if b_type == "text":
                        t_text = b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
                        assistant_blocks.append({"type": "text", "text": str(t_text)})
                    elif b_type == "tool_use":
                        t_name = b.get("name") if isinstance(b, dict) else getattr(b, "name", "")
                        t_input = b.get("input") if isinstance(b, dict) else getattr(b, "input", {})
                        t_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", "")
                        assistant_blocks.append({
                            "type": "tool_use",
                            "id": str(t_id),
                            "name": str(t_name),
                            "input": t_input
                        })
                    elif isinstance(b, dict):
                        assistant_blocks.append(b)
            elif isinstance(raw_content, str) and raw_content:
                assistant_blocks.append({"type": "text", "text": raw_content})

        return assistant_blocks, stop_reason, reasoning_content, in_tok, out_tok, cached_tok, thinking_tok

    # --------------------------------------------------------------------------
    # Deterministic Tool Hashing & Anti-Oscillation Guard
    # --------------------------------------------------------------------------

    @staticmethod
    def compute_tool_signature(tool_name: str, tool_input: Any) -> str:
        """
        Generate deterministic hash signature for tool name and argument payload.
        Used to detect oscillation loops and redundant tool calls.
        """
        try:
            if isinstance(tool_input, dict):
                sig_args = json.dumps(tool_input, sort_keys=True, default=str)
            else:
                sig_args = str(tool_input)
        except Exception:
            sig_args = str(tool_input)
        
        return f"{tool_name}:{hashlib.md5(sig_args.encode('utf-8')).hexdigest()}"

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
        if stage_name.startswith("per_asset_") or stage_name == "per_asset_primary":
            return "submit_asset_analysis"
        if stage_name == "fundamental":
            return "submit_fundamental_brief"
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
            from database.db import get_session
            from database.models import ActivityLog

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
            async with get_session() as log_session:
                log_session.add(log_entry)
                await log_session.commit()
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
        stage_symbol = (
            stage_name.replace("per_asset_", "") if stage_name.startswith("per_asset_") else None
        )

        curr_max = getattr(self.llm_client, "max_tokens", None)
        if isinstance(curr_max, int) and curr_max < 32000:
            if getattr(self.llm_client, "provider_name", "") in ("groq", "openrouter"):
                self.llm_client.max_tokens = 32000

        # Initialize or reuse tool executor
        executor = tool_executor
        if executor is None:
            import sys
            llm_mod = sys.modules.get(self.llm_client.__class__.__module__) if hasattr(self.llm_client, "__class__") else None
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

        called_tools: Set[str] = set()
        consecutive_tool_sig: Optional[str] = None
        repeated_tool_count: int = 0
        total_sig_counts: Dict[str, int] = {}
        sliding_window_sigs: deque[str] = deque(maxlen=8)

        # Reset all guardrails for fresh stage execution
        self.guardrail_controller.reset_all()
        self.stall_guard.reset()
        self.verification_ledger.reset_turn()

        current_messages = list(messages)

        logger.info(
            f"[{stage_name}][AgentHarness] Starting ReAct loop "
            f"(max_turns={effective_max_turns}, tools_available={len(tools)})"
        )

        _overflow_recovery_attempted = False

        while turns < effective_max_turns:
            turns += 1
            self.guardrail_controller.reset_turn()

            # 1. Layer 1/2 Context Compaction & Observation Masking
            context_win = self.settings.get("context_window", 128000)
            current_messages = self.compactor.check_and_compact(
                current_messages, context_window=context_win
            )

            # 2. Context Compression (HIGH-4)
            if hasattr(self, "context_compressor") and self.context_compressor:
                try:
                    current_messages = await self.context_compressor.compress(
                        current_messages, max_context_chars=self.max_context_chars, tail_turns=3
                    )
                except Exception as comp_err:
                    logger.debug(f"ContextCompressor skipped or failed: {comp_err}")

            # 3. Layer 3 Truncation Guardrail with Fact Preservation
            current_messages = self._apply_truncation_guardrail(
                current_messages, system_prompt=system_prompt, stage_name=stage_name
            )

            # 3. Provider Call with Transient Retry, Distributed Tracing, and Plugin Hooks
            from utils.plugins.manager import get_plugin_manager, PluginHook

            plugin_mgr = get_plugin_manager()
            await plugin_mgr.emit(
                PluginHook.PRE_LLM_CALL,
                stage_name=stage_name,
                turn=turns,
                messages=current_messages,
                tools=tools,
            )

            provider_name = getattr(self.llm_client, "provider_name", "unknown")
            model_name = getattr(self.llm_client, "model", "unknown")
            task_role = getattr(self.llm_client, "role", stage_name)

            response = None
            last_exc = None
            max_attempts = 3

            with llm_span(provider=provider_name, model=model_name, task_role=task_role) as active_llm_span:
                for attempt in range(max_attempts):
                    try:
                        # ── C4: ROLE ALTERNATION ENFORCEMENT & INTEGRITY REPAIR ──
                        role_safe_messages = self._enforce_role_alternation(current_messages)
                        try:
                            from analysis.harness.message_repair import repair_message_history
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

                        # ── Prompt Cache Invariance Hardening ──
                        effective_sys = system_prompt
                        assemble_fn = getattr(system_prompt, "assemble", None)
                        if callable(assemble_fn):
                            effective_sys = assemble_fn(provider=provider_name)
                        elif isinstance(system_prompt, tuple):
                            static_sys, dynamic_sys = system_prompt
                            effective_sys = static_sys
                            if dynamic_sys and send_messages and send_messages[0].get("role") == "user":
                                content = send_messages[0].get("content", "")
                                if isinstance(content, str) and "<volatile_overlay>" not in content:
                                    send_messages[0]["content"] = f"<volatile_overlay>\n{dynamic_sys}\n</volatile_overlay>\n\n{content}"

                        response = await self.llm_client.run_tool_agent(
                            send_messages, tools, effective_sys
                        )
                        break
                    except Exception as exc:
                        last_exc = exc

                        # ── Structured Error Recovery Pipeline (Phase 3) ──
                        from analysis.harness.error_classifier import ErrorClassifier, RecoveryAction, ErrorCategory
                        classified = ErrorClassifier.classify(exc)

                        await plugin_mgr.emit(
                            PluginHook.ON_LLM_ERROR,
                            stage_name=stage_name,
                            turn=turns,
                            error=exc,
                            classified=classified,
                        )

                        if classified.recovery == RecoveryAction.RETRY_WITH_COMPACTION and not _overflow_recovery_attempted:
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
                                raw_backoff = min(classified.retry_delay, 5.0) if classified.retry_delay > 0 else (2.0 * (2 ** attempt))
                                backoff = raw_backoff * (1.0 - random.random() * 0.1)
                                await asyncio.sleep(backoff)
                                continue

                        if (classified.recovery == RecoveryAction.RETRY_SAME or self._is_transient_error(exc)) and attempt < max_attempts - 1:
                            raw_backoff = classified.retry_delay if classified.retry_delay > 0 else (2.0 * (2 ** attempt))
                            backoff = raw_backoff * (1.0 - random.random() * 0.1)
                            logger.warning(
                                f"[{stage_name}][AgentHarness] Retryable error on turn {turns} "
                                f"(attempt {attempt+1}/{max_attempts}): {exc}. Retrying in {backoff:.2f}s..."
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
                    is_billing = self._is_billing_error(last_exc)
                    logger.error(f"[{stage_name}][AgentHarness] Provider error on turn {turns}: {last_exc} (is_billing={is_billing})")
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
                                is_direct_free_tier=not is_paid if is_paid is not None else None,
                            )
                        except Exception:
                            pass
                    # Durable Failed Turn Sealing: prevent consecutive user messages
                    if current_messages and current_messages[-1].get("role") == "user":
                        current_messages.append({
                            "role": "assistant",
                            "content": "[Analysis turn terminated prematurely due to provider error. State preserved.]"
                        })
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
                        "context_messages": current_messages,
                        "is_paid": is_paid,
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

                    # ── Silent Overflow Detection (Pi Pattern) ──
                    if in_tok > 0 and not _overflow_recovery_attempted:
                        from utils.llm.model_capabilities import MODEL_CAPABILITIES
                        model_name_check = getattr(self.llm_client, "model", "")
                        cap = MODEL_CAPABILITIES.get(model_name_check, None)
                        context_window = getattr(cap, "context_window", 0) if cap else (cap.get("context_window", 0) if isinstance(cap, dict) else 0)
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
                    logger.error(f"[{stage_name}][AgentHarness] Response normalization error on turn {turns}: {norm_err}")
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
                                is_direct_free_tier=not is_paid if is_paid is not None else None,
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
            current_messages.append(assistant_msg)

            # Check text blocks
            for block in assistant_content:
                b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if b_type == "text":
                    b_text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                    if b_text and not getattr(block, "thinking", False):
                        final_text = b_text

            # ── Repetition Guard (Degenerate Echo Loop Prevention) ──
            if final_text:
                from analysis.harness.repetition_guard import detect_text_repetition
                is_degenerate, rep_snippet = detect_text_repetition(final_text)
                if is_degenerate and turns < effective_max_turns:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Repetition loop detected ({rep_snippet}). "
                        f"Injecting recovery nudge on turn {turns}/{effective_max_turns}..."
                    )
                    current_messages.append({
                        "role": "user",
                        "content": "[System: Repetition loop detected in analysis text. Conclude directly with your structured analytical verdict now.]"
                    })
                    continue

            # ── C1: TRUNCATED TOOL CALL SAFETY ──
            # When LLM hits max output tokens, tool call JSON arguments may be
            # truncated mid-value. Auto-repair JSON can "fix" syntax but produce
            # WRONG values (e.g., stop_loss: 1.08 → 1.0). Refuse all tool calls.
            if self._check_truncation(response, stop_reason):
                tool_use_blocks_check = [
                    b for b in assistant_content
                    if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
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

            # ── Structured Response Validation (Phase 3) ──
            from analysis.harness.error_classifier import ErrorClassifier, RecoveryAction
            resp_dict = {
                "stop_reason": stop_reason,
                "content": final_text,
                "tool_calls": [
                    b for b in assistant_content
                    if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
                ],
                "reasoning": reasoning_content or "",
            }
            resp_issue = ErrorClassifier.classify_response(resp_dict)
            if resp_issue and not self._check_truncation(response, stop_reason) and turns < effective_max_turns:
                if resp_issue.recovery in (RecoveryAction.INJECT_NUDGE, RecoveryAction.INJECT_CONTINUATION):
                    logger.warning(f"[{stage_name}][AgentHarness] Response issue detected ({resp_issue.category.value}): injecting recovery nudge.")
                    current_messages.append({"role": "user", "content": resp_issue.nudge_text or "[System: Please proceed.]"})
                    continue
                elif resp_issue.recovery == RecoveryAction.RETRY_WITH_REDUCED_EFFORT:
                    logger.warning(f"[{stage_name}][AgentHarness] Thinking budget exhausted without content: nudging direct conclusion.")
                    current_messages.append({"role": "user", "content": "[System: Thinking budget exhausted without answer. Conclude directly.]"})
                    continue

            # 6. Check Completion & Mandatory Tool Enforcement
            tool_use_blocks = [
                b for b in assistant_content
                if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
            ]

            if not tool_use_blocks:
                mandatory_tool = self.get_mandatory_tool_for_stage(stage_name)
                if mandatory_tool and mandatory_tool not in called_tools:
                    if turns < effective_max_turns:
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
                    else:
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Reached max turns ({effective_max_turns}) "
                            f"without calling mandatory tool '{mandatory_tool}'."
                        )
                # ── Trade Proposal Verification Stop Gate ──
                from analysis.harness.trade_stop_gates import TradeStopGate
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
                        final_text = json.dumps({
                            "decision": "WAIT",
                            "confidence": 0.0,
                            "rationale": f"Downgraded to defensive WAIT: {trade_verdict.rejection_reason or 'Risk/sizing unverified before turn limit'}",
                            "downgraded_by_stop_gate": True,
                        })

                logger.info(
                    f"[{stage_name}][AgentHarness] Agent completed in {turns} turns with "
                    f"{tool_calls_made} tool executions."
                )
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
                raw_name = str(block.get("name") or "") if isinstance(block, dict) else str(getattr(block, "name", "") or "")
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

                # ── M5: Tool Schema Validation (Pi Pattern) ──
                tool_schema_fn = getattr(executor, "get_tool_schema", None)
                tool_schema = None
                if callable(tool_schema_fn) and not inspect.iscoroutinefunction(tool_schema_fn) and type(tool_schema_fn).__name__ != "AsyncMock":
                    res = tool_schema_fn(t_name)
                    if isinstance(res, dict):
                        tool_schema = res
                if tool_schema and isinstance(tool_schema, dict) and tool_schema.get("input_schema"):


                    schema_err = None

                    try:
                        import jsonschema  # type: ignore[import-untyped, import-not-found]
                        jsonschema.validate(instance=t_input, schema=tool_schema["input_schema"])
                    except ImportError:
                        req = tool_schema["input_schema"].get("required", [])
                        missing = [r for r in req if r not in t_input]
                        if missing:
                            schema_err = f"missing required fields {missing}"
                    except Exception as ve:
                        schema_err = getattr(ve, "message", str(ve))

                    if schema_err:
                        logger.warning(f"[{stage_name}] Schema validation failed for {t_name}: {schema_err}")
                        call_item["_schema_error"] = {
                            "type": "tool_result",
                            "tool_use_id": t_id,
                            "content": json.dumps({
                                "status": "schema_validation_error",
                                "error": f"Invalid arguments for {t_name}: {schema_err}. Fix and re-call.",
                            }),
                            "is_error": True,
                        }
                prepared_calls.append(call_item)

            async def _execute_single_prepared_tool(call_item: dict) -> dict:
                nonlocal tool_calls_made, consecutive_tool_sig, repeated_tool_count
                c_name = call_item["name"]
                c_input = call_item["input"]
                c_id = call_item["id"]

                # Check if schema validation preflight failed
                if call_item.get("_schema_error"):
                    tool_calls_made += 1
                    self.guardrail_controller.record_denial()
                    return call_item["_schema_error"]

                # Unified Tool Guardrails (Monotonic Risk, Read-Before-Act, Sizing, Turn Cap, Anti-Oscillation)
                guard_verdict = self.guardrail_controller.validate_tool_call(
                    c_name, c_input, context=kwargs
                )
                if not guard_verdict.allowed:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Guardrail blocked '{c_name}' ({guard_verdict.guard_name}): {guard_verdict.reason}"
                    )
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    if guard_verdict.action in ("reject", "nudge"):
                        self.guardrail_controller.record_denial()
                    status_val = "already_executed" if guard_verdict.guard_name == "AntiOscillationGuard" else f"guardrail_{guard_verdict.action}"
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "content": json.dumps({
                            "status": status_val,
                            "guard": guard_verdict.guard_name,
                            "notice" if guard_verdict.action == "suppress" else "error": guard_verdict.reason,
                            "suggested_fix": guard_verdict.suggested_fix,
                        }),
                        "is_error": guard_verdict.action in ("reject", "nudge"),
                    }

                # a. Progressive Anti-Oscillation Loop Guard (Hash-based + Sliding Window)
                call_sig = self.compute_tool_signature(c_name, c_input)
                total_sig_counts[call_sig] = total_sig_counts.get(call_sig, 0) + 1

                if call_sig == consecutive_tool_sig:
                    repeated_tool_count += 1
                else:
                    consecutive_tool_sig = call_sig
                    repeated_tool_count = 1

                recent_repeats = sliding_window_sigs.count(call_sig)

                if repeated_tool_count >= 2 or recent_repeats >= 2 or total_sig_counts[call_sig] >= 3:
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Anti-Oscillation: Suppressing repeated call for '{c_name}' "
                        f"(consecutive={repeated_tool_count}, recent={recent_repeats}, total={total_sig_counts[call_sig]})"
                    )
                    suppressed_result = {
                        "status": "already_executed",
                        "notice": (
                            f"Tool '{c_name}' with identical parameters was already executed. "
                            f"Do not repeat identical calls. Synthesize data already collected and conclude analysis."
                        ),
                    }
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "content": json.dumps(suppressed_result),
                    }

                sliding_window_sigs.append(call_sig)

                # b. Tool Family Quota Enforcement
                allowed, quota_warn = self.compactor.check_tool_family_quota(c_name, list(called_tools))
                if not allowed:
                    logger.warning(f"[{stage_name}][AgentHarness] Tool Family Quota Exceeded for '{c_name}': {quota_warn}")
                    suppressed_result = {"status": "quota_exceeded", "notice": quota_warn}
                    tool_calls_made += 1
                    called_tools.add(c_name)
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "content": json.dumps(suppressed_result),
                    }

                # ── Trade Proposal Verification Stop Gate & Anti-Laziness Interception ──
                if c_name == "submit_asset_analysis":
                    target_sym = c_input.get("symbol") or stage_symbol
                    decision = str(c_input.get("decision") or "").upper()

                    # 1. Anti-laziness on Turn 1: WAIT cannot be submitted without inspecting technical structure or price action
                    if turns == 1 and decision in ("WAIT", "HOLD", "NEUTRAL", "PASS", "NO_TRADE"):
                        inspection_tools = {
                            "get_smc_zones", "get_structure_breaks", "get_price_history",
                            "get_indicator_snapshot", "get_mt5_bars", "get_atr", "get_swing_points"
                        }
                        if not any(t in called_tools for t in inspection_tools):
                            logger.warning(
                                f"[{stage_name}][AgentHarness] Anti-laziness: blocked premature WAIT on turn 1 without technical inspection."
                            )
                            tool_calls_made += 1
                            called_tools.add(c_name)
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "content": json.dumps({
                                    "status": "anti_laziness_nudge",
                                    "error": (
                                        "Cannot conclude WAIT on turn 1 without inspecting technical structure or price action. "
                                        "You must call get_smc_zones, get_structure_breaks, or get_price_history first."
                                    ),
                                }),
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
                            called_tools.add(c_name)
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "content": json.dumps({
                                    "status": "blocked_by_stop_gate",
                                    "error": (
                                        f"Trade proposal ({decision} {target_sym}) blocked by TradeStopGate: "
                                        f"No passing calculate_position_size or validate_risk_limits evidence recorded in ledger. "
                                        f"You MUST call calculate_position_size with exact stop_loss and take_profit parameters first."
                                    ),
                                }),
                                "is_error": True,
                            }

                # c. Dynamic Execution via ToolExecutor with OpenTelemetry Tool Span and Plugin Hooks
                tool_calls_made += 1
                called_tools.add(c_name)
                res_obj = None
                try:
                    from utils.plugins.manager import get_plugin_manager, PluginHook
                    plugin_mgr = get_plugin_manager()
                    await plugin_mgr.emit(PluginHook.PRE_TOOL_CALL, tool_name=c_name, args=c_input, stage_name=stage_name)

                    from logging_observability.tracing.spans import tool_span
                    with tool_span(c_name, symbol=stage_symbol):
                        res_obj = await executor.execute(c_name, c_input)

                    await plugin_mgr.emit(PluginHook.POST_TOOL_CALL, tool_name=c_name, args=c_input, result=res_obj, stage_name=stage_name)
                except Exception as ex:
                    logger.error(f"[{stage_name}][AgentHarness] Tool execution exception in '{c_name}': {ex}")
                    res_obj = {"error": f"Tool execution failed: {str(ex)}", "tool": c_name}

                await self._log_tool_call(session, stage_name, c_name, c_input, res_obj)
                self.guardrail_controller.record_tool_call(c_name, c_input, res_obj)
                self.guardrail_controller.record_success()
                self.stall_guard.record_call(c_name, res_obj)
                self.verification_ledger.record_tool_execution(c_name, c_input, res_obj)

                # Format tool result block with validation and micro-pruning
                try:
                    from utils.validation.tool_response_validator import ToolResponseValidator
                    sanitized_result, is_valid, warning = ToolResponseValidator.validate_and_sanitize(c_name, res_obj)
                    if not is_valid:
                        error_context = ToolResponseValidator.build_error_context(c_name, warning)
                        tool_res_content = (json.dumps(sanitized_result, default=str) if not isinstance(sanitized_result, str) else sanitized_result) + error_context
                    else:
                        tool_res_content = json.dumps(sanitized_result, ensure_ascii=False, default=str) if not isinstance(sanitized_result, str) else sanitized_result
                except Exception:
                    tool_res_content = json.dumps(res_obj, default=str) if not isinstance(res_obj, str) else res_obj

                tool_res_content = self.compactor.micro_prune(tool_res_content, tool_name=c_name)

                # ── Generation-Tracked Data Fetch Deduplication ──
                dedup_notice = self.data_dedup.check_and_record(c_name, c_input, tool_res_content)
                if dedup_notice:
                    tool_res_content = dedup_notice

                # ── Untrusted Content Isolation & Threat Scanning ──
                untrusted_tools = frozenset({
                    "get_news_items", "get_news_digest", "get_retail_sentiment",
                    "get_social_sentiment", "web_search", "get_cot_report", "scrape_url",
                    "get_forex_sentiment", "get_fxssi_sentiment", "get_structured_sentiment",
                })
                if c_name in untrusted_tools:
                    try:
                        from utils.security.threat_scanner import sanitize_or_block
                        tool_res_content = sanitize_or_block(tool_res_content, source=c_name)
                    except Exception:
                        pass
                    tool_res_content = (
                        f'<untrusted_external_content source="{c_name}">\n'
                        f'{tool_res_content}\n'
                        f'</untrusted_external_content>'
                    )

                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "content": tool_res_content,
                }

            # Plan segments into [Parallel Safe] -> [Barrier] -> [Parallel Safe]
            tool_results = []
            segments = planner.plan_segments(prepared_calls)
            for seg_type, batch in segments:
                if seg_type == "parallel" and len(batch) > 1:
                    raw_results = await asyncio.gather(*[_execute_single_prepared_tool(tc) for tc in batch], return_exceptions=True)
                    for idx, res in enumerate(raw_results):
                        if isinstance(res, Exception):
                            tc = batch[idx]
                            logger.error(f"[{stage_name}][AgentHarness] Parallel tool {tc.get('name')} failed: {res}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tc.get("id", ""),
                                "content": json.dumps({"status": "execution_error", "error": str(res)}),
                                "is_error": True,
                            })
                        else:
                            tool_results.append(res)
                else:
                    for tc in batch:
                        try:
                            res = await _execute_single_prepared_tool(tc)
                            tool_results.append(res)
                        except Exception as ex:
                            logger.error(f"[{stage_name}][AgentHarness] Sequential tool {tc.get('name')} failed: {ex}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tc.get("id", ""),
                                "content": json.dumps({"status": "execution_error", "error": str(ex)}),
                                "is_error": True,
                            })

            # Append tool observations as next turn user message
            current_messages.append({"role": "user", "content": tool_results})

            # 8. State-Aware Stall Guard Check (H-8)
            is_stall_warn, is_stall_terminate, stall_msg = self.stall_guard.check_stall()
            if is_stall_terminate and stall_msg:
                logger.warning(f"[{stage_name}][AgentHarness] STALL GUARD FORCE TERMINATION: {stall_msg}")
                if current_messages and isinstance(current_messages[-1].get("content"), list):
                    current_messages[-1]["content"].append({"type": "text", "text": f"\n[STALL GUARD TERMINATION]: {stall_msg}"})
                elif current_messages:
                    current_messages[-1]["content"] = f"{current_messages[-1].get('content', '')}\n\n[STALL GUARD TERMINATION]: {stall_msg}"
                if effective_max_turns > turns + 1:
                    effective_max_turns = turns + 1
            elif is_stall_warn and stall_msg:
                logger.info(f"[{stage_name}][AgentHarness] STALL GUARD WARNING: {stall_msg}")
                if current_messages and isinstance(current_messages[-1].get("content"), list):
                    current_messages[-1]["content"].append({"type": "text", "text": f"\n[STALL GUARD WARNING]: {stall_msg}"})
                elif current_messages:
                    current_messages[-1]["content"] = f"{current_messages[-1].get('content', '')}\n\n[STALL GUARD WARNING]: {stall_msg}"

            # I7: PTC Iteration Budget Refund
            # If sole tool call was execute_analysis_code, refund the iteration
            # because the LLM delegated work to local Python execution
            # P0-10: Cap PTC refunds at 3 to prevent infinite loops
            if len(prepared_calls) == 1 and prepared_calls[0].get("name") == "execute_analysis_code":
                if ptc_refund_count < 3:
                    turns -= 1
                    ptc_refund_count += 1
                    logger.debug(f"[{stage_name}][AgentHarness] PTC budget refund ({ptc_refund_count}/3): turn not counted")
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
                    is_direct_free_tier=not is_paid if is_paid is not None else None,
                )
            except Exception as e:
                logger.debug(f"[{stage_name}][AgentHarness] Token save failed: {e}")

        return {
            "success": True,
            "final_text": final_text,
            "tool_calls_made": tool_calls_made,
            "turns": turns,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "thinking_tokens": total_thinking_tokens,
            "cached_tokens": total_cached_tokens,
            "total_cost_usd": round(total_cost_usd, 6),
            "context_messages": current_messages,
            "error": None,
            "is_paid": is_paid,
            "is_billing_error": False,
        }
