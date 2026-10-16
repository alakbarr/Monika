# ==============================================================================
# File: application/agent/chat/base.py
# ==============================================================================

"""
Shared logging, constants, and typing infrastructure for ChatAgent mixins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from monika.application.agent.chat_tool_router import ChatToolRouter
    from monika.application.agent.chat.pending_actions import PendingAction

logger = logging.getLogger("TradingAgent.ChatAgent")


class _ChatAgentMixinBase:
    """Type-checking base contract for ChatAgent modular mixins."""

    if TYPE_CHECKING:
        settings: dict
        user_id: int | str
        is_admin: bool
        _client_lite: Any
        _client_medium: Any
        _client_deep: Any
        _client_research: Any
        _client_intent: Any
        _gemini_lite: Any
        _groq_medium: Any
        _claude_sonnet: Any
        _pending_actions: dict[str, PendingAction]
        _pending_charts: list[Any]
        _pending_files: list[tuple[str, Any]]
        last_active: Optional[datetime]
        _tool_router: ChatToolRouter
        guardrail_controller: Any
        _session_approvals: dict[str, datetime]
        SESSION_APPROVAL_TTL_HOURS: int
        _consecutive_denials: int
        DENIAL_BREAKER_THRESHOLD: int
        _proposals_paused: bool
        _active_task: Optional[asyncio.Task]
        _interrupt_message: Optional[str]
        _steer_queue: list[str]
        _hard_cancelled: bool
        tool_event_listener: Optional[Any]
        _last_turn_streamed: bool
        _last_intercepted_pending: Optional[PendingAction]

        @property
        def was_last_turn_streamed(self) -> bool: ...
        @was_last_turn_streamed.setter
        def was_last_turn_streamed(self, value: bool) -> None: ...
        def set_tool_event_listener(self, listener: Optional[Any]) -> None: ...
        def _instrument_executor(self, executor: Any) -> None: ...
        async def _ensure_mcp_tools_synced(self) -> None: ...
        def is_symbol_session_approved(self, symbol: str) -> bool: ...
        def add_session_approval(self, symbol: str) -> datetime: ...
        async def _persist_pending_action(self, action: PendingAction) -> None: ...
        async def _delete_persisted_pending_action(self, action_id: str) -> None: ...
        async def get_pending_action(self, action_id: str) -> Optional[PendingAction]: ...
        async def approve_for_session(self, action_id: str) -> tuple[bool, str]: ...
        def is_proposals_paused(self) -> bool: ...
        def is_busy(self) -> bool: ...
        def record_denial(self) -> tuple[bool, str]: ...
        def steer(self, guidance: str) -> str: ...
        def redirect(self, new_task: str) -> bool: ...
        def hard_cancel(self) -> bool: ...
        def interrupt(self) -> bool: ...
        def resume_proposals(self) -> str: ...
        def pop_pending_charts(self) -> list[Any]: ...
        def pop_pending_files(self) -> list[tuple[str, Any]]: ...
        def _detect_model_preference(self, msg: str) -> Optional[str]: ...
        def _is_macro_event_query(self, text: str) -> bool: ...
        def _inject_macro_playbooks(
            self, system_prompt: Union[str, tuple[str, str]], user_query: str = ""
        ) -> Union[str, tuple[str, str]]: ...
        async def _classify_query_complexity(self, msg: str) -> str: ...
        def _prepare_cache_invariant_prompt(self, system_prompt: Any, message: str) -> tuple[str, str]: ...
        def _format_user_message_payload(self, user_msg: str, image_bytes: Optional[bytes] = None) -> Any: ...
        async def _build_system_prompt(self, session: AsyncSession) -> tuple[str, str] | str: ...
        def _build_lean_system_prompt(self) -> str: ...
        async def _handle_streaming(
            self,
            update: Any,
            context: Any,
            user_message: str,
            session_id: Optional[str] = None,
            typing_callback: Optional[Any] = None,
            status_callback: Optional[Any] = None,
        ) -> tuple[str, Optional[PendingAction]]: ...
        async def _handle_token_callback_stream(
            self,
            user_message: str,
            token_callback: Any,
            session_id: Optional[str] = None,
            typing_callback: Optional[Any] = None,
            status_callback: Optional[Any] = None,
        ) -> tuple[str, Optional[PendingAction]]: ...
        async def _stream_response(
            self,
            update: Any,
            context: Any,
            response_generator: Any,
        ) -> str: ...
        async def _handle_internal(
            self,
            user_message: str,
            typing_callback: Optional[Any] = None,
            status_callback: Optional[Any] = None,
            session_id: Optional[str] = None,
        ) -> tuple[str, Optional[PendingAction]]: ...
        async def handle(
            self,
            user_message: Union[str, Any],
            context: Optional[Any] = None,
            typing_callback: Optional[Any] = None,
            status_callback: Optional[Any] = None,
            session_id: Optional[str] = None,
            override_text: Optional[str] = None,
            stream: bool = False,
            update: Optional[Any] = None,
            token_callback: Optional[Any] = None,
        ) -> tuple[str, Optional[PendingAction]]: ...
        async def _run_tier_deep_research(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            status_callback: Any = None,
        ) -> dict: ...
        async def _run_tier_lite(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            image_bytes: Optional[bytes] = None,
        ) -> dict: ...
        async def _run_tier_medium(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            image_bytes: Optional[bytes] = None,
        ) -> dict: ...
        async def _run_tier_deep(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            image_bytes: Optional[bytes] = None,
        ) -> dict: ...
        async def _run_with_gemini(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            stream: bool = False,
        ) -> Any: ...
        async def _run_with_claude(
            self,
            system_prompt: Any,
            history: Any,
            message: Any,
            tool_executor: Any = None,
            stream: bool = False,
        ) -> Any: ...
        async def confirm_action(self, action_id: str) -> tuple[bool, str]: ...
        async def reject_action(self, action_id: str) -> str: ...
        async def _execute_action(self, action: PendingAction) -> str: ...
        async def _execute_db_mutation(self, params: dict) -> str: ...
        def _create_pending_action(self, proposed: dict) -> Optional[PendingAction]: ...
        async def _close_durable_failed_turn(
            self, session_id: Optional[str] = None, reason: str = "Turn aborted before completion"
        ) -> None: ...
        async def _save_message(
            self, session: AsyncSession, role: str, message: str, session_id: Optional[str] = None
        ) -> None: ...
        async def _load_history(self, session: AsyncSession, session_id: Optional[str] = None) -> list[dict]: ...
