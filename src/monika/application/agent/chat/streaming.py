# ==============================================================================
# File: application/agent/chat/streaming.py
# ==============================================================================

"""
Token streaming, executor event instrumentation, and MCP synchronization.
"""

from __future__ import annotations

import asyncio
import re
from monika.infrastructure.database.db import get_session
from monika.application.agent.chat.pending_actions import PendingAction
from typing import Any, Optional

from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.planning.session_plan import SessionPlan
from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad

_MCP_MUTATING_TOKENS = frozenset(
    {
        "add",
        "append",
        "apply",
        "chmod",
        "chown",
        "clear",
        "commit",
        "copy",
        "create",
        "delete",
        "drop",
        "edit",
        "execute",
        "grant",
        "insert",
        "install",
        "kill",
        "merge",
        "mkdir",
        "modify",
        "move",
        "patch",
        "post",
        "publish",
        "purge",
        "push",
        "put",
        "remove",
        "rename",
        "replace",
        "reset",
        "restart",
        "revoke",
        "run",
        "save",
        "send",
        "set",
        "start",
        "stop",
        "sync",
        "terminate",
        "touch",
        "uninstall",
        "update",
        "upload",
        "write",
    }
)

_MCP_READ_ONLY_TOKENS = frozenset(
    {
        "browse",
        "check",
        "count",
        "describe",
        "exists",
        "fetch",
        "find",
        "get",
        "head",
        "health",
        "info",
        "inspect",
        "list",
        "lookup",
        "ping",
        "query",
        "read",
        "scan",
        "search",
        "show",
        "stat",
        "status",
        "tail",
        "validate",
        "view",
    }
)

_FILE_WRITE_TOOLS = frozenset({"write_file", "patch"})


def is_mutating_mcp_tool(tool_name: str) -> bool:
    """Classify MCP tools for approval; unknown tools fail closed (require approval)."""
    if not isinstance(tool_name, str) or not tool_name.startswith("mcp_"):
        return False
    tokens = {part for part in tool_name.lower().split("_") if part}
    if tokens & _MCP_MUTATING_TOKENS:
        return True
    if tokens & _MCP_READ_ONLY_TOKENS:
        return False
    return True


class StreamingMixin(_ChatAgentMixinBase):
    """Mixin managing token streaming, tool callbacks, and live event interception."""

    @property
    def was_last_turn_streamed(self) -> bool:
        """Returns True if the most recent turn was successfully rendered via live streaming."""
        return getattr(self, "_last_turn_streamed", False)

    @was_last_turn_streamed.setter
    def was_last_turn_streamed(self, value: bool) -> None:
        self._last_turn_streamed = bool(value)

    def set_tool_event_listener(self, listener: Optional[Any]):
        """Register a callback for tool events ('start' and 'result')."""
        self.tool_event_listener = listener

    def _instrument_executor(self, executor: Any):
        """Wrap ToolExecutor.execute to notify tool_event_listener if set and enforce Safety Fortress gating."""
        orig_exec = executor.execute
        listener = self.tool_event_listener

        MUTATING_ACTIONS_MAP = {
            "place_order": "place_order",
            "close_position": "close_position",
            "close_positions_batch": "close_all_positions",
            "set_trailing_stop": "set_trailing_stop",
            "cancel_stale_pending_orders": "cancel_stale_pending_orders",
            "modify_sl_tp": "modify_sl_tp",
            "bulk_breakeven": "bulk_breakeven",
            "secure_positions": "secure_positions",
            "cancel_order": "cancel_order",
            "close_paper_trade": "close_paper_trade",
            "modify_paper_sl_tp": "modify_paper_sl_tp",
        }

        async def _wrapped_exec(tool_name: str, tool_input: dict) -> Any:
            # Safety Fortress Gate: MCP tools that can mutate external state require approval.
            if is_mutating_mcp_tool(tool_name):
                pending = self._create_pending_action(
                    {
                        "action_type": "mcp_write",
                        "params": {"tool_name": tool_name, "args": tool_input or {}},
                        "description": f"MCP write tool: {tool_name}",
                    }
                )
                if pending is None:
                    logger.warning(f"[SafetyFortress] MCP tool '{tool_name}' blocked: approval channel unavailable.")
                    return {
                        "status": "blocked_by_safety_fortress",
                        "error": (
                            f"MCP tool '{tool_name}' requires operator approval, but no approval channel is available."
                        ),
                    }
                self._last_intercepted_pending = pending
                logger.info(
                    f"[SafetyFortress] Intercepted MCP write tool '{tool_name}' -> PendingAction #{pending.action_id}"
                )
                return {
                    "status": "pending_operator_approval",
                    "action_id": pending.action_id,
                    "action_type": "mcp_write",
                    "message": (
                        f"MCP tool '{tool_name}' can mutate external state and requires operator authorization. "
                        f"Proposal #{pending.action_id} generated for operator confirmation."
                    ),
                }

            # Safety Fortress Gate: Local file writes mutate the workspace and require approval.
            if tool_name in _FILE_WRITE_TOOLS:
                pending = self._create_pending_action(
                    {
                        "action_type": "file_write",
                        "params": {"tool_name": tool_name, "args": tool_input or {}},
                        "description": f"File write tool: {tool_name}",
                    }
                )
                if pending is None:
                    logger.warning(
                        f"[SafetyFortress] File write tool '{tool_name}' blocked: approval channel unavailable."
                    )
                    return {
                        "status": "blocked_by_safety_fortress",
                        "error": (
                            f"File write tool '{tool_name}' requires operator approval, "
                            "but no approval channel is available."
                        ),
                    }
                self._last_intercepted_pending = pending
                logger.info(
                    f"[SafetyFortress] Intercepted file write tool '{tool_name}' -> PendingAction #{pending.action_id}"
                )
                return {
                    "status": "pending_operator_approval",
                    "action_id": pending.action_id,
                    "action_type": "file_write",
                    "message": (
                        f"File write tool '{tool_name}' requires operator authorization. "
                        f"Proposal #{pending.action_id} generated for operator confirmation."
                    ),
                }

            # Safety Fortress Gate: Intercept direct mutating calls from chat LLM
            if tool_name in MUTATING_ACTIONS_MAP:
                action_type = MUTATING_ACTIONS_MAP[tool_name]
                pending = self._create_pending_action(
                    {
                        "action_type": action_type,
                        "params": tool_input or {},
                        "description": f"Mutasi {tool_name} ({action_type})",
                    }
                )
                if pending is None:
                    logger.warning(
                        f"[SafetyFortress] Mutating tool '{tool_name}' blocked: approval channel unavailable."
                    )
                    return {
                        "status": "blocked_by_safety_fortress",
                        "error": (
                            f"Action '{tool_name}' requires operator approval, but no approval channel is available."
                        ),
                    }
                self._last_intercepted_pending = pending
                logger.info(
                    f"[SafetyFortress] Intercepted mutating tool '{tool_name}' -> Created PendingAction #{pending.action_id}"
                )
                return {
                    "status": "pending_operator_approval",
                    "action_id": pending.action_id,
                    "action_type": action_type,
                    "message": (
                        f"Action '{tool_name}' involves capital mutation and cannot be executed directly. "
                        f"Proposal #{pending.action_id} has been generated and presented to the operator for confirmation."
                    ),
                }

            # Safety Fortress Gate: Intercept mutating terminal execution
            if tool_name == "terminal":
                cmd = str((tool_input or {}).get("command", "")).strip()
                read_only_starters = (
                    "git status",
                    "git log",
                    "git diff",
                    "git branch",
                    "uptime",
                    "tasklist",
                    "dir",
                    "ls",
                    "ps",
                    "cat",
                    "head",
                    "tail",
                    "whoami",
                    "date",
                    "hostname",
                    "echo",
                )
                is_read_only = any(cmd.lower().startswith(starter) for starter in read_only_starters)
                destructive_chars = [";", "&", "|", ">"]
                if not (is_read_only and not any(ch in cmd for ch in destructive_chars)):
                    action_type = "execute_terminal_command"
                    pending = self._create_pending_action(
                        {
                            "action_type": action_type,
                            "params": tool_input or {},
                            "description": f"Eksekusi Shell Command:\n• Command: `{cmd}`",
                        }
                    )
                    if pending is None:
                        logger.warning(
                            f"[SafetyFortress] Terminal command '{cmd}' blocked: approval channel unavailable."
                        )
                        return {
                            "status": "blocked_by_safety_fortress",
                            "error": (
                                f"Terminal command '{cmd}' requires operator approval, "
                                "but no approval channel is available."
                            ),
                        }
                    self._last_intercepted_pending = pending
                    logger.info(
                        f"[SafetyFortress] Intercepted terminal command '{cmd}' -> PendingAction #{pending.action_id}"
                    )
                    return {
                        "status": "pending_operator_approval",
                        "action_id": pending.action_id,
                        "action_type": action_type,
                        "message": (
                            f"Terminal command '{cmd}' requires operator authorization. "
                            f"Proposal #{pending.action_id} generated for operator confirmation."
                        ),
                    }

            # Safety Fortress Gate: Intercept interactive computer_use GUI actions
            if tool_name == "computer_use":
                gui_action = str((tool_input or {}).get("action", "")).lower().strip()
                if gui_action != "screenshot":
                    action_type = "desktop_gui_action"
                    coord = (tool_input or {}).get("coordinate")
                    txt = (tool_input or {}).get("text")
                    key = (tool_input or {}).get("key")
                    detail = f"• Aksi: {gui_action}"
                    if coord:
                        detail += f"\n• Koordinat: {coord}"
                    if txt:
                        detail += f"\n• Input Teks: {txt}"
                    if key:
                        detail += f"\n• Tombol Key: {key}"
                    pending = self._create_pending_action(
                        {
                            "action_type": action_type,
                            "params": tool_input or {},
                            "description": f"Desktop GUI Interaction:\n{detail}",
                        }
                    )
                    if pending is None:
                        logger.warning(
                            f"[SafetyFortress] GUI action '{gui_action}' blocked: approval channel unavailable."
                        )
                        return {
                            "status": "blocked_by_safety_fortress",
                            "error": (
                                f"Desktop GUI action '{gui_action}' requires operator approval, "
                                "but no approval channel is available."
                            ),
                        }
                    self._last_intercepted_pending = pending
                    logger.info(
                        f"[SafetyFortress] Intercepted GUI action '{gui_action}' -> PendingAction #{pending.action_id}"
                    )
                    return {
                        "status": "pending_operator_approval",
                        "action_id": pending.action_id,
                        "action_type": action_type,
                        "message": (
                            f"Desktop GUI action '{gui_action}' requires operator authorization. "
                            f"Proposal #{pending.action_id} generated for operator confirmation."
                        ),
                    }

            if listener:
                try:
                    cb = listener("start", {"tool": tool_name, "input": tool_input})
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception as e:
                    logger.debug(f"[ChatAgent] Error in tool listener start: {e}")

            res = await orig_exec(tool_name, tool_input)

            if listener:
                try:
                    summary = str(res)
                    if len(summary) > 120:
                        summary = summary[:120] + "..."
                    cb = listener("result", {"tool": tool_name, "summary": summary, "result": res})
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception as e:
                    logger.debug(f"[ChatAgent] Error in tool listener result: {e}")

            return res

        executor.execute = _wrapped_exec

    async def _ensure_mcp_tools_synced(self):
        """Ensure active MCP servers are initialized and bridged tools are added to _tool_router."""
        if getattr(self, "_mcp_synced", False):
            return
        try:
            from monika.infrastructure.mcp.client import McpClientManager
            from monika.application.analysis.tools.unified_registry import unified_tool_registry

            mgr = McpClientManager.get_instance(self.settings)
            await mgr.initialize_servers()
            mcp_tool_defs = []
            for name, entry in unified_tool_registry._tools.items():
                if name.startswith("mcp_"):
                    mcp_tool_defs.append(entry.get_anthropic_schema())
            if mcp_tool_defs:
                self._tool_router.update_tools(mcp_tool_defs)
            self._mcp_synced = True
            logger.info(f"[ChatAgent] Synchronized {len(mcp_tool_defs)} MCP tools into ChatToolRouter.")
        except Exception as e:
            logger.warning(f"[ChatAgent] MCP tools sync non-fatal error: {e}")

    async def _handle_streaming(
        self,
        update: Any,
        context: Any,
        user_message: str,
        session_id: Optional[str] = None,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Headless fallback for streaming requests with external update objects."""
        return await self._handle_internal(
            user_message=user_message,
            session_id=session_id,
            typing_callback=typing_callback,
            status_callback=status_callback,
        )

    async def _handle_token_callback_stream(
        self,
        user_message: str,
        token_callback: Any,
        session_id: Optional[str] = None,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Stream real LLM tokens to WebSocket/caller callback with thought tag handling."""
        async with get_session() as session:
            history = await self._load_history(session, session_id=session_id)
            system_prompt = await self._build_system_prompt(session)

            preference = self._detect_model_preference(user_message)
            clean_message = user_message
            if preference == "deep_research":
                clean_message = re.sub(r"^/research\s*", "", user_message, flags=re.IGNORECASE)
            elif preference in ("tier_lite", "gemini_lite"):
                preference = "tier_lite"
                clean_message = re.sub(r"^/(fast|quick)\s+", "", user_message, flags=re.IGNORECASE)
            elif preference in ("tier_medium", "groq_medium"):
                preference = "tier_medium"
                clean_message = re.sub(r"^/(medium|mid)\s+", "", user_message, flags=re.IGNORECASE)
            elif preference in ("tier_deep", "claude_sonnet"):
                preference = "tier_deep"
                clean_message = re.sub(r"^/(analyze|analisis)\s+", "", user_message, flags=re.IGNORECASE)

            if preference == "auto":
                complexity = await self._classify_query_complexity(clean_message)
                if complexity == "deep_research":
                    preference = "deep_research"
                elif complexity == "complex":
                    preference = "tier_deep"
                else:
                    preference = "tier_lite"

            # Integrate session-scoped planning (Wave 3) — fully wired
            session_plan = SessionPlan.get_or_create(session_id or "default")
            plan_summary = session_plan.summary_text()
            if plan_summary and len(plan_summary) > 20:
                clean_message = f"[SESSION PLAN]\n{plan_summary}\n---\n{clean_message}"
            # Link session plan to working scratchpad for cross-reference
            scratch_symbol = (session_id or "default").strip().upper().replace("/", "") if session_id else "SESSION"
            scratch_symbol = scratch_symbol[:20]
            scratch_state = WorkingScratchpad.get_or_create(scratch_symbol)
            scratch_state["session_plan_ref"] = session_plan.session_id
            scratch_state["session_plan_goal"] = session_plan.get_plan().get("goal", "")
            WorkingScratchpad.update_scratchpad(
                scratch_symbol,
                {"notes": f"SessionPlan goal={session_plan.get_plan().get('goal', 'N/A')}"},
            )

            selected_tools = self._tool_router.route_tools_for_query(clean_message)
            needs_tools = bool(selected_tools) or bool(
                re.search(
                    r"\b(posisi|order|orders|harga|price|chart|saldo|equity|balance|pnl|profit|loss|close|buy|sell|debat|analisis|analisa|setup|market|vix|dxy|cot|fedwatch|alpha|factor|factors)\b",
                    clean_message,
                    re.IGNORECASE,
                )
            )

            if preference == "deep_research" or needs_tools:
                reply, pending = await self._handle_internal(
                    user_message=clean_message,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )
                if token_callback and reply:
                    res = token_callback(reply)
                    if asyncio.iscoroutine(res):
                        await res
                self._last_turn_streamed = True
                self.was_last_turn_streamed = True
                return reply, pending

            # Save user message once for the direct streaming path (_handle_internal handles its own save)
            await self._save_message(session, "user", clean_message, session_id=session_id)
            system_prompt = self._inject_macro_playbooks(system_prompt, user_query=clean_message)

            if preference in ("tier_deep", "claude_sonnet"):
                generator = await self._run_with_claude(system_prompt, history, clean_message, stream=True)
            else:
                generator = await self._run_with_gemini(system_prompt, history, clean_message, stream=True)

            buffer = []
            if isinstance(generator, dict):
                reply = str(generator.get("reply", ""))
                buffer.append(reply)
                if token_callback and reply:
                    res = token_callback(reply)
                    if asyncio.iscoroutine(res):
                        await res
            else:
                async for delta in generator:
                    text_chunk = delta if isinstance(delta, str) else getattr(delta, "text", str(delta))
                    buffer.append(text_chunk)
                    if token_callback:
                        res = token_callback(text_chunk)
                        if asyncio.iscoroutine(res):
                            await res

            final_text = "".join(buffer)
            if not final_text.strip():
                final_text = "[PERINGATAN] Tidak ada respons yang dihasilkan."
            else:
                from monika.application.agent.scratchpad_guard import close_dangling_scratchpad

                final_text = close_dangling_scratchpad(final_text)

            await self._save_message(session, "assistant", final_text, session_id=session_id)
            self._last_turn_streamed = True
            self.was_last_turn_streamed = True
            return final_text, None

    async def _stream_response(
        self,
        update: Any,
        context: Any,
        response_generator: Any,
    ) -> str:
        """Headless response accumulator fallback."""
        chunks = []
        async for delta in response_generator:
            text_chunk = delta if isinstance(delta, str) else getattr(delta, "text", str(delta))
            chunks.append(text_chunk)
        raw_text = "".join(chunks)
        from monika.application.agent.scratchpad_guard import close_dangling_scratchpad

        return close_dangling_scratchpad(raw_text)
