# ==============================================================================
# File: infrastructure/providers/openai_chat.py
# ==============================================================================

"""
OpenAI Chat and Tool Execution Mixin.
Handles message normalization, tool schema conversion, and multi-turn chat loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Optional

from monika.infrastructure.providers.base_provider import BaseLLMClient, _flatten_system_prompt

logger = logging.getLogger("TradingAgent.OpenAIProvider")


class OpenAIChatMixin(BaseLLMClient):
    """Mixin for multi-turn chat, tool orchestration, and message normalization."""

    if TYPE_CHECKING:
        client: Any
        model: str
        max_tokens: int
        default_temperature: float
        kwargs: dict[str, Any]
        settings: Any
        max_tool_turns: int

        def _get_provider_name(self) -> str: ...
        def _apply_reasoning_params(self, kwargs: dict[str, Any]) -> None: ...
        async def _create_chat_completion(self, kwargs: dict[str, Any]) -> Any: ...
        @staticmethod
        def _extract_usage(usage: Any) -> tuple[int, int, int, int, Optional[float], int]: ...

    def _convert_tools(self, tools: list) -> list:
        provider_name = self._get_provider_name()
        is_openrouter = (
            provider_name in ("openrouter", "9router")
            or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
        )
        is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))
        supports_cache_control = is_openrouter and is_claude_or_qwen

        from monika.infrastructure.providers.schema_normalizer import ToolSchemaNormalizer

        return ToolSchemaNormalizer.to_openai(tools, supports_cache_control=supports_cache_control)

    def _normalize_messages(self, messages: list) -> list:
        """Normalizes messages across heterogeneous provider formats (Anthropic/Gemini to OpenAI)."""
        call_id_to_name: dict[str, str] = {}
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict):
                    cid = tc.get("id")
                    fn_name = tc.get("function", {}).get("name")
                    if cid and fn_name:
                        call_id_to_name[str(cid)] = str(fn_name)
            c = msg.get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        bid = b.get("id")
                        bname = b.get("name")
                        if bid and bname:
                            call_id_to_name[str(bid)] = str(bname)

        norm_messages = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content")

            if isinstance(content, list):
                text_parts = []
                image_parts: list[dict[str, Any]] = []
                tool_calls = []
                tool_results = []
                thinking_parts = []

                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "text":
                        text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if text_val:
                            text_parts.append(text_val)
                    elif b_type == "image":
                        source = block.get("source", {}) if isinstance(block, dict) else getattr(block, "source", {})
                        if isinstance(source, dict):
                            media_type = str(source.get("media_type", "image/jpeg"))
                            data = str(source.get("data", ""))
                            if data:
                                image_parts.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                                    }
                                )
                    elif b_type == "image_url":
                        img_url_data = (
                            block.get("image_url", {}) if isinstance(block, dict) else getattr(block, "image_url", {})
                        )
                        if isinstance(img_url_data, dict) and img_url_data.get("url"):
                            image_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": str(img_url_data["url"])},
                                }
                            )
                        elif isinstance(img_url_data, str) and img_url_data:
                            image_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": img_url_data},
                                }
                            )
                    elif b_type in ("thinking", "thought"):
                        t_val = block.get("thinking") if isinstance(block, dict) else getattr(block, "thinking", None)
                        if not t_val:
                            t_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if t_val:
                            thinking_parts.append(str(t_val))
                    elif b_type == "tool_result":
                        c_val = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                        tid = (
                            block.get("tool_use_id")
                            if isinstance(block, dict)
                            else getattr(block, "tool_use_id", "call_0")
                        )
                        raw_tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
                        if not raw_tname or str(raw_tname).lower() == "none":
                            raw_tname = call_id_to_name.get(str(tid)) or "tool"
                        tname = str(raw_tname)
                        content_str = json.dumps(c_val, default=str) if not isinstance(c_val, str) else c_val
                        if (
                            "gemini" in self.model.lower()
                            or "google" in self.model.lower()
                            or getattr(self, "provider_name", "") == "google"
                        ):
                            try:
                                parsed = json.loads(content_str)
                                if not isinstance(parsed, (dict, list)):
                                    content_str = json.dumps({"output": content_str})
                            except Exception:
                                content_str = json.dumps({"output": content_str})

                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": str(tid),
                                "name": tname,
                                "content": content_str,
                            }
                        )
                    elif b_type == "tool_use":
                        tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", "tool")
                        tinput = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                        tid = block.get("id") if isinstance(block, dict) else getattr(block, "id", "call_0")
                        tool_calls.append(
                            {
                                "id": str(tid),
                                "type": "function",
                                "function": {
                                    "name": tname,
                                    "arguments": json.dumps(tinput) if not isinstance(tinput, str) else tinput,
                                },
                            }
                        )

                if role == "assistant" or tool_calls:
                    ast_msg: dict[str, Any] = {"role": "assistant"}
                    ast_msg["content"] = " ".join(text_parts) if text_parts else ""
                    if tool_calls:
                        ast_msg["tool_calls"] = tool_calls
                    if m.get("reasoning_content"):
                        ast_msg["reasoning_content"] = m["reasoning_content"]
                    elif thinking_parts:
                        ast_msg["reasoning_content"] = "\n".join(thinking_parts)
                    for k in ("thought_signature", "thought", "reasoning_details", "extra_content"):
                        if k in m and m[k] is not None:
                            ast_msg[k] = m[k]
                    norm_messages.append(ast_msg)
                    if tool_results:
                        norm_messages.extend(tool_results)
                        tool_results = []
                else:
                    if tool_results:
                        norm_messages.extend(tool_results)
                        tool_results = []
                    if image_parts and role == "user":
                        content_payload: list[dict[str, Any]] = []
                        if text_parts:
                            content_payload.append({"type": "text", "text": " ".join(text_parts)})
                        content_payload.extend(image_parts)
                        norm_messages.append({"role": role, "content": content_payload})
                    elif text_parts:
                        norm_messages.append({"role": role, "content": " ".join(text_parts)})
            elif role == "tool":
                tid = m.get("tool_call_id", "")
                raw_name = m.get("name")
                if not raw_name or str(raw_name).lower() == "none":
                    m_copy = dict(m)
                    m_copy["name"] = call_id_to_name.get(str(tid)) or "tool"
                    norm_messages.append(m_copy)
                else:
                    norm_messages.append(dict(m))
            else:
                norm_messages.append(dict(m))
        return norm_messages

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any, tool_choice: Optional[Any] = None):
        if not self.client:
            raise Exception("OpenAI API client not initialized")

        req_messages = []
        static_sys = system_prompt
        dynamic_sys = ""
        compile_fn = getattr(system_prompt, "compile_stable_system", None)
        if isinstance(system_prompt, tuple) and len(system_prompt) >= 2:
            static_sys = system_prompt[0]
            dynamic_sys = str(system_prompt[1]).strip() if system_prompt[1] else ""
        elif callable(compile_fn):
            static_sys = compile_fn()
            dynamic_sys = getattr(system_prompt, "tier3_volatile", "")

        flat_sys = _flatten_system_prompt(static_sys)
        provider_name = self._get_provider_name()
        is_openrouter = (
            provider_name in ("openrouter", "9router")
            or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
        )
        is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))

        if flat_sys:
            if is_openrouter and is_claude_or_qwen:
                req_messages.append(
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": flat_sys, "cache_control": {"type": "ephemeral"}}],
                    }
                )
            else:
                req_messages.append({"role": "system", "content": flat_sys})

        norm_msgs = self._normalize_messages(messages)
        if dynamic_sys and norm_msgs:
            last_user_idx = max((i for i, m in enumerate(norm_msgs) if m.get("role") == "user"), default=None)
            if last_user_idx is not None:
                last_user = dict(norm_msgs[last_user_idx])
                user_content = last_user.get("content", "")
                if "<context_snapshot>" not in str(user_content):
                    if isinstance(user_content, str):
                        last_user["content"] = (
                            f"{user_content}\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"
                        )
                    elif isinstance(user_content, list):
                        last_user["content"] = list(user_content) + [
                            {"type": "text", "text": f"\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"}
                        ]
                norm_msgs[last_user_idx] = last_user

        if is_openrouter and is_claude_or_qwen:
            from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

            cbm = CacheBreakpointManager()
            max_msg_bp = 2 if tools else 3
            norm_msgs = cbm.apply_to_messages(norm_msgs, max_message_breakpoints=max_msg_bp)

        req_messages.extend(norm_msgs)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": req_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.kwargs.get("temperature", self.default_temperature),
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            if tool_choice is not None:
                if isinstance(tool_choice, str):
                    if tool_choice in ("auto", "none", "required"):
                        kwargs["tool_choice"] = tool_choice
                    else:
                        kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}
                elif isinstance(tool_choice, dict):
                    kwargs["tool_choice"] = tool_choice

        self._apply_reasoning_params(kwargs)

        response = await self._create_chat_completion(kwargs)
        return response

    async def run_chat_loop(
        self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None
    ) -> dict:
        if not self.client:
            return {"success": False, "reply": "OpenAI API not initialized.", "error": "Not initialized"}

        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            if tool_executor is not None:
                executor = tool_executor
            else:
                import importlib

                tool_executor_cls = importlib.import_module(
                    "monika.application.analysis.tools.tool_executor"
                ).ToolExecutor
                executor = tool_executor_cls(session, settings=self.settings, model_name=self.model)

            messages = []
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": new_user_message})

            turns = 0
            tool_calls_made = 0
            final_text = ""
            proposed_action = None
            total_input = 0
            total_output = 0
            total_cached = 0
            total_thinking = 0
            consecutive_chat_tool_sig = None
            repeated_chat_tool_count = 0

            from monika.infrastructure.llm.context_compaction import ContextCompactionEngine

            compactor = ContextCompactionEngine(self.settings)

            while turns < self.max_tool_turns:
                turns += 1

                # NOTE: In-place observation masking REMOVED — it destroys server KV cache.
                # Tool results are immutable once appended to messages.
                # For token pressure, atomic compaction occurs at turn boundaries.

                try:
                    response = await self.run_tool_agent(messages, tools, system_prompt)
                except Exception as e:
                    logger.error(f"OpenAI chat error: {e}")
                    return {"success": False, "reply": f"API error: {e}", "error": str(e)}

                if not response:
                    logger.error("OpenAI chat error: empty response")
                    return {"success": False, "reply": "Maaf, respon model kosong.", "error": "Empty response"}

                if hasattr(response, "usage") and response.usage:
                    inp, outp, cached, thinking, _, cache_creation = self._extract_usage(response.usage)
                    total_input += inp
                    total_output += outp
                    total_cached += cached
                    total_thinking += thinking

                if not getattr(response, "choices", None) or len(response.choices) == 0:
                    logger.error("OpenAI chat error: empty choices in response")
                    return {
                        "success": False,
                        "reply": "Maaf, respon model kosong (empty choices).",
                        "error": "No choices in response",
                    }

                choice = response.choices[0]
                if not choice or not getattr(choice, "message", None):
                    logger.error("OpenAI chat error: choice missing message object")
                    return {
                        "success": False,
                        "reply": "Maaf, pesan model tidak ditemukan.",
                        "error": "No message in choice",
                    }

                message = choice.message
                ast_msg: dict[str, Any] = {"role": "assistant"}
                if message.content:
                    ast_msg["content"] = message.content

                if getattr(message, "reasoning_content", None):
                    ast_msg["reasoning_content"] = message.reasoning_content

                extra = getattr(message, "model_extra", {}) or {}
                for k in ("thought_signature", "thought", "reasoning_details", "extra_content"):
                    val = getattr(message, k, None) or (extra.get(k) if isinstance(extra, dict) else None)
                    if val is not None:
                        ast_msg[k] = val

                if message.tool_calls:
                    ast_msg["tool_calls"] = []
                    for t in message.tool_calls:
                        ast_msg["tool_calls"].append(
                            {
                                "id": t.id,
                                "type": "function",
                                "function": {"name": t.function.name, "arguments": t.function.arguments},
                            }
                        )
                messages.append(ast_msg)

                if message.content:
                    final_text = message.content

                # C1 Safety: Truncated tool call abort guard
                if getattr(choice, "finish_reason", None) == "length" and message.tool_calls:
                    logger.critical(
                        f"[SafetyGuard] Model output truncated (finish_reason=length) with {len(message.tool_calls)} "
                        f"tool call(s). Aborting execution to prevent malformed trade/analysis parameters."
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "[GUARDRAIL ERROR: Output was truncated mid-generation. Tool calls were aborted for safety. Please re-state concisely.]",
                        }
                    )
                    return {
                        "success": False,
                        "reply": "Respon model terpotong (max_tokens). Eksekusi tool dibatalkan demi keamanan parameter trading.",
                        "error": "TRUNCATED_TOOL_CALLS",
                        "aborted_tools": len(message.tool_calls),
                    }

                if not message.tool_calls:
                    break

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    from monika.application.agent.harness.tool_repair import repair_tool_arguments

                    tool_input = repair_tool_arguments(tool_call.function.arguments)

                    # Anti-Oscillation Tool Loop Guard (Hash-based)
                    try:
                        sig_args = json.dumps(tool_input, sort_keys=True, default=str)
                    except Exception:
                        sig_args = str(tool_input)
                    call_sig = f"{tool_name}:{hashlib.md5(sig_args.encode()).hexdigest()}"
                    if call_sig == consecutive_chat_tool_sig:
                        repeated_chat_tool_count += 1
                    else:
                        consecutive_chat_tool_sig = call_sig
                        repeated_chat_tool_count = 1

                    if repeated_chat_tool_count >= 2:
                        logger.warning(
                            f"[OpenAI][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}"
                        )
                        suppressed_result = {
                            "status": "already_executed",
                            "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained.",
                        }
                        tool_calls_made += 1
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(suppressed_result),
                            }
                        )
                        continue

                    tool_calls_made += 1

                    if tool_name == "propose_action":
                        proposed_action = tool_input
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps({"status": "proposed", "message": "Action proposed to user."}),
                            }
                        )
                        continue

                    try:
                        res = await executor.execute(tool_name, tool_input)
                    except Exception as exec_err:
                        logger.error(f"OpenAI chat tool execution error ({tool_name}): {exec_err}", exc_info=True)
                        from monika.application.agent.harness.turn_failure_diagnostics import (
                            TurnFailureDiagnosticBuilder,
                        )

                        diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
                            turn_number=turns,
                            tool_name=tool_name,
                            tool_input=tool_input if isinstance(tool_input, dict) else {},
                            error_msg=str(exec_err),
                        )
                        res = {"status": "error", "error": str(exec_err), "_turn_failure_diagnostic": diag.to_dict()}
                    raw_content = json.dumps(res, default=str, ensure_ascii=False)
                    pruned_content = compactor.micro_prune(raw_content, tool_name=tool_name)
                    tool_content = pruned_content
                    if (
                        "gemini" in self.model.lower()
                        or "google" in self.model.lower()
                        or getattr(self, "provider_name", "") == "google"
                    ):
                        try:
                            parsed_check = json.loads(tool_content)
                            if not isinstance(parsed_check, (dict, list)):
                                tool_content = json.dumps({"output": tool_content})
                        except Exception:
                            tool_content = json.dumps({"output": tool_content})
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": tool_content}
                    )

            await self._save_token_usage(
                self.model,
                "chat_telegram",
                total_input,
                total_output,
                cached_tokens=total_cached,
                thinking_tokens=total_thinking,
            )

            return {
                "success": True,
                "reply": final_text,
                "proposed_action": proposed_action,
                "tool_calls_made": tool_calls_made,
                "turns": turns,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "thinking_tokens": total_thinking,
            }
