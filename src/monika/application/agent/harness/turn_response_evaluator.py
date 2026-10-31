"""
File: src/monika/application/agent/harness/turn_response_evaluator.py

Evaluates, normalizes, and validates LLM provider responses within AgentHarness.
Handles:
1. Multi-provider response content normalization and token accounting.
2. Silent input token overflow detection with emergency compaction triggers.
3. Assistant message construction preserving reasoning blocks and thinking signatures.
4. Repetition loop detection and history cleansing (Anti-Slop / Degenerate loop prevention).
5. Output token truncation safety (refusing malformed partial tool calls).
6. Structured response issue classification and recovery nudging.
7. Empty response recovery ladder and fallback swapping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from monika.application.agent.harness.error_classifier import (
    ErrorClassifier,
    RecoveryAction,
)
from monika.application.agent.harness.repetition_guard import detect_text_repetition
from monika.infrastructure.llm.model_capabilities import MODEL_CAPABILITIES

logger = logging.getLogger("TradingAgent.AgentHarness.TurnResponseEvaluator")


@dataclass
class ResponseEvaluationResult:
    """Outcome of evaluating a raw provider response."""

    action: str  # "proceed", "continue_turn", "emergency_compact", "early_return"
    assistant_content: List[dict]
    assistant_msg: dict
    final_text: str
    tool_use_blocks: List[dict]
    in_tok: int
    out_tok: int
    c_tok: int
    th_tok: int
    turn_cost_usd: float
    is_paid: bool
    length_truncated: bool
    early_return_payload: Optional[dict] = None
    unverified_stop_gate_error: Optional[str] = None
    tool_calls_increment: int = 0


class TurnResponseEvaluator:
    """Validates raw LLM responses and produces safe, normalized turn artifacts."""

    @staticmethod
    def evaluate_response(
        harness: Any,
        session: Any,
        response: Any,
        current_messages: List[dict],
        stage_name: str,
        turns: int,
        effective_max_turns: int,
        context_win: int,
        tool_calls_made: int,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cached_tokens: int,
        total_thinking_tokens: int,
        total_cost_usd: float,
        is_paid: bool,
        length_truncated: bool,
        overflow_recovery_attempted: bool,
        calculate_turn_cost_fn: Any,
        called_tools: set[str],
        active_llm_span: Optional[Any] = None,
    ) -> ResponseEvaluationResult:
        model_name_curr = getattr(harness.llm_client, "model", "unknown_model")
        task_role = getattr(harness.llm_client, "role", stage_name)

        # 1. Normalize Response Across Providers (Anthropic, Gemini, OpenAI, Groq)
        try:
            assistant_content, stop_reason, reasoning_content, in_tok, out_tok, c_tok, th_tok = (
                harness._normalize_response_content(response)
            )
            if active_llm_span is not None:
                active_llm_span.set_attribute("input_tokens", in_tok)
                active_llm_span.set_attribute("output_tokens", out_tok)
                active_llm_span.set_attribute("cached_tokens", c_tok)
                active_llm_span.set_attribute("thinking_tokens", th_tok)

            # ── Silent Overflow Detection (Input Token Ingestion Guard) ──
            if in_tok > 0 and not overflow_recovery_attempted:
                cap = MODEL_CAPABILITIES.get(model_name_curr, None)
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
                    compacted_messages = harness.compactor.emergency_compact(
                        current_messages,
                        context_window=context_window,
                        target_reduction=0.50,
                    )
                    current_messages.clear()
                    current_messages.extend(compacted_messages)
                    return ResponseEvaluationResult(
                        action="emergency_compact",
                        assistant_content=[],
                        assistant_msg={},
                        final_text="",
                        tool_use_blocks=[],
                        in_tok=in_tok,
                        out_tok=out_tok,
                        c_tok=c_tok,
                        th_tok=th_tok,
                        turn_cost_usd=0.0,
                        is_paid=is_paid,
                        length_truncated=length_truncated,
                    )
        except Exception as norm_err:
            logger.error(f"[{stage_name}][AgentHarness] Response normalization error on turn {turns}: {norm_err}")
            if (total_input_tokens > 0 or total_output_tokens > 0) and hasattr(harness.llm_client, "_save_token_usage"):
                try:
                    import asyncio

                    asyncio.create_task(
                        harness.llm_client._save_token_usage(
                            model_name=model_name_curr,
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
                    )
                except Exception:
                    pass
            early_payload = {
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
            return ResponseEvaluationResult(
                action="early_return",
                assistant_content=[],
                assistant_msg={},
                final_text="",
                tool_use_blocks=[],
                in_tok=0,
                out_tok=0,
                c_tok=0,
                th_tok=0,
                turn_cost_usd=0.0,
                is_paid=is_paid,
                length_truncated=length_truncated,
                early_return_payload=early_payload,
            )

        paid_flag = is_paid or bool(getattr(response, "is_paid", False))
        turn_cost = calculate_turn_cost_fn(model_name_curr, in_tok, out_tok, c_tok)

        # 2. Build and Record Assistant Message (Preserving Reasoning Content)
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant_content}
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        # I2: Thinking Signature Persistence
        if getattr(response, "thinking_signature", None):
            assistant_msg["thinking_signature"] = getattr(response, "thinking_signature")
        curr_provider = harness._detect_client_provider()
        assistant_msg["_source_provider"] = str(curr_provider)
        assistant_msg["_source_model"] = str(model_name_curr)

        if hasattr(harness, "_last_normalized_extra") and harness._last_normalized_extra:
            for k, v in harness._last_normalized_extra.items():
                if k not in assistant_msg:
                    assistant_msg[k] = v
        current_messages.append(assistant_msg)

        final_text = ""
        for block in assistant_content:
            b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if b_type == "text":
                b_text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                if b_text and not getattr(block, "thinking", False):
                    final_text = b_text

        # ── Repetition Guard (Degenerate Echo Loop Prevention & History Cleansing) ──
        if final_text:
            is_degenerate, rep_snippet = detect_text_repetition(final_text)
            if is_degenerate and turns < effective_max_turns:
                logger.warning(
                    f"[{stage_name}][AgentHarness] Repetition loop detected ({rep_snippet}). "
                    f"Cleansing history and injecting recovery nudge on turn {turns}/{effective_max_turns}..."
                )
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
                return ResponseEvaluationResult(
                    action="continue_turn",
                    assistant_content=assistant_content,
                    assistant_msg=assistant_msg,
                    final_text=final_text,
                    tool_use_blocks=[],
                    in_tok=in_tok,
                    out_tok=out_tok,
                    c_tok=c_tok,
                    th_tok=th_tok,
                    turn_cost_usd=turn_cost,
                    is_paid=paid_flag,
                    length_truncated=length_truncated,
                )

        # ── C1: TRUNCATED TOOL CALL SAFETY ──
        new_length_truncated = length_truncated
        if harness._check_truncation(response, stop_reason):
            new_length_truncated = True
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
                truncation_error_results = harness._fail_truncated_tool_calls(tool_use_blocks_check)
                current_messages.append({"role": "user", "content": truncation_error_results})
                logger.info(
                    f"[{stage_name}][AgentHarness] Injected {len(truncation_error_results)} "
                    f"truncation error(s) as tool results for self-correction."
                )
                return ResponseEvaluationResult(
                    action="continue_turn",
                    assistant_content=assistant_content,
                    assistant_msg=assistant_msg,
                    final_text=final_text,
                    tool_use_blocks=[],
                    in_tok=in_tok,
                    out_tok=out_tok,
                    c_tok=c_tok,
                    th_tok=th_tok,
                    turn_cost_usd=turn_cost,
                    is_paid=paid_flag,
                    length_truncated=new_length_truncated,
                    tool_calls_increment=len(tool_use_blocks_check),
                )
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
                    return ResponseEvaluationResult(
                        action="continue_turn",
                        assistant_content=assistant_content,
                        assistant_msg=assistant_msg,
                        final_text=final_text,
                        tool_use_blocks=[],
                        in_tok=in_tok,
                        out_tok=out_tok,
                        c_tok=c_tok,
                        th_tok=th_tok,
                        turn_cost_usd=turn_cost,
                        is_paid=paid_flag,
                        length_truncated=new_length_truncated,
                    )

        # ── Structured Response Validation (Phase 3) ──
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
        if resp_issue and not harness._check_truncation(response, stop_reason) and turns < effective_max_turns:
            if resp_issue.recovery in (RecoveryAction.INJECT_NUDGE, RecoveryAction.INJECT_CONTINUATION):
                logger.warning(
                    f"[{stage_name}][AgentHarness] Response issue detected ({resp_issue.category.value}): injecting recovery nudge."
                )
                current_messages.append(
                    {"role": "user", "content": resp_issue.nudge_text or "[System: Please proceed.]"}
                )
                return ResponseEvaluationResult(
                    action="continue_turn",
                    assistant_content=assistant_content,
                    assistant_msg=assistant_msg,
                    final_text=final_text,
                    tool_use_blocks=[],
                    in_tok=in_tok,
                    out_tok=out_tok,
                    c_tok=c_tok,
                    th_tok=th_tok,
                    turn_cost_usd=turn_cost,
                    is_paid=paid_flag,
                    length_truncated=new_length_truncated,
                )
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
                return ResponseEvaluationResult(
                    action="continue_turn",
                    assistant_content=assistant_content,
                    assistant_msg=assistant_msg,
                    final_text=final_text,
                    tool_use_blocks=[],
                    in_tok=in_tok,
                    out_tok=out_tok,
                    c_tok=c_tok,
                    th_tok=th_tok,
                    turn_cost_usd=turn_cost,
                    is_paid=paid_flag,
                    length_truncated=new_length_truncated,
                )

        tool_use_blocks = [
            b
            for b in assistant_content
            if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
        ]
        if tool_use_blocks and hasattr(harness, "tool_call_recovery") and harness.tool_call_recovery:
            harness.tool_call_recovery.register_assistant_tool_calls(tool_use_blocks)

        unverified_stop_gate_err: Optional[str] = None
        if not (final_text or "").strip() and not tool_use_blocks:
            prov_name = str(getattr(harness.llm_client, "provider", "unknown"))
            mdl_name = str(getattr(harness.llm_client, "model", "unknown"))
            emp_count = harness.empty_response_guard.record_empty_response(
                prov_name, mdl_name, str(stop_reason or "stop")
            )
            ladder_act = harness.empty_response_guard.get_recovery_ladder_action(
                prov_name,
                mdl_name,
                attempt=emp_count,
                raw_response=reasoning_content or "",
                task_role=stage_name,
            )
            if turns < effective_max_turns:
                if ladder_act.action_type == "failover":
                    harness._try_fallback_swap(stage_name, RuntimeError(ladder_act.instruction))
                logger.warning(
                    f"[{stage_name}][AgentHarness] Empty response recovery ladder step {ladder_act.step} "
                    f"({ladder_act.action_type}): {ladder_act.instruction}"
                )
                current_messages.append(
                    {"role": "user", "content": f"[SYSTEM RECOVERY DIRECTIVE]: {ladder_act.instruction}"}
                )
                return ResponseEvaluationResult(
                    action="continue_turn",
                    assistant_content=assistant_content,
                    assistant_msg=assistant_msg,
                    final_text=final_text,
                    tool_use_blocks=[],
                    in_tok=in_tok,
                    out_tok=out_tok,
                    c_tok=c_tok,
                    th_tok=th_tok,
                    turn_cost_usd=turn_cost,
                    is_paid=paid_flag,
                    length_truncated=new_length_truncated,
                )
            elif not called_tools:
                unverified_stop_gate_err = (
                    f"Empty response after {emp_count} attempt(s) with zero tool calls ({ladder_act.instruction})"
                )
        else:
            harness.empty_response_guard.record_successful_response(
                str(getattr(harness.llm_client, "provider", "unknown")),
                str(getattr(harness.llm_client, "model", "unknown")),
            )

        return ResponseEvaluationResult(
            action="proceed",
            assistant_content=assistant_content,
            assistant_msg=assistant_msg,
            final_text=final_text,
            tool_use_blocks=tool_use_blocks,
            in_tok=in_tok,
            out_tok=out_tok,
            c_tok=c_tok,
            th_tok=th_tok,
            turn_cost_usd=turn_cost,
            is_paid=paid_flag,
            length_truncated=new_length_truncated,
            unverified_stop_gate_error=unverified_stop_gate_err,
        )
