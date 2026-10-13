# ==============================================================================
# File: application/agent/chat/__init__.py
# ==============================================================================

"""
Modular package for conversational chat agent and interaction management.
"""

from __future__ import annotations

from monika.application.agent.chat.constants import (
    HISTORY_WINDOW,
    MAX_HISTORY_CHARS,
    SESSION_TIMEOUT_HOURS,
    TELEGRAM_MAX_CHARS,
    _sanitize_chat_format,
    _sanitize_telegram_format,
    _sanitize_telegram_format_impl,
)
from monika.application.agent.chat.pending_actions import PendingAction
from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.agent.chat.action_state import ActionStateMixin
from monika.application.agent.chat.action_execution import ActionExecutionMixin
from monika.application.agent.chat.prompt_builder import PromptBuilderMixin
from monika.application.agent.chat.streaming import StreamingMixin
from monika.application.agent.chat.tiers import ExecutionTiersMixin
from monika.application.agent.chat.history import HistoryMixin
from monika.application.agent.chat.coordinator import ChatAgent

from monika.infrastructure.database.db import get_session
from monika.infrastructure.providers.llm_factory import get_client_for_task

__all__ = [
    "ActionExecutionMixin",
    "ActionStateMixin",
    "ChatAgent",
    "ExecutionTiersMixin",
    "HISTORY_WINDOW",
    "HistoryMixin",
    "MAX_HISTORY_CHARS",
    "PendingAction",
    "PromptBuilderMixin",
    "SESSION_TIMEOUT_HOURS",
    "StreamingMixin",
    "TELEGRAM_MAX_CHARS",
    "_ChatAgentMixinBase",
    "_sanitize_chat_format",
    "_sanitize_telegram_format",
    "_sanitize_telegram_format_impl",
    "get_client_for_task",
    "get_session",
    "logger",
]
