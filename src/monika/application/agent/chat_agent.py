# ==============================================================================
# File: application/agent/chat_agent.py
# Monika Core Conversational AI Agent & Session Domain Engine
# ==============================================================================

"""
Backward-compatible facade for Core Conversational Chat Agent.

All agent classes, execution mixins, and pending actions are now modularized
under monika.application.agent.chat.
"""

from __future__ import annotations

from monika.application.agent.chat import *
from monika.application.agent.chat import action_execution as action_execution
from monika.application.agent.chat import base as base
from monika.application.agent.chat import constants as constants
from monika.application.agent.chat import coordinator as coordinator
from monika.application.agent.chat import history as history
from monika.application.agent.chat import pending_actions as pending_actions
from monika.application.agent.chat import prompt_builder as prompt_builder
from monika.application.agent.chat import streaming as streaming
from monika.application.agent.chat import tiers as tiers

ChatAgent.__module__ = "monika.application.agent.chat_agent"
PendingAction.__module__ = "monika.application.agent.chat_agent"

import sys
import types
from typing import Any


class _ChatAgentFacadeModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in ("get_client_for_task", "get_session"):
            if "monika.application.agent.chat" in sys.modules:
                setattr(sys.modules["monika.application.agent.chat"], name, value)
            for sub in (
                "coordinator",
                "action_state",
                "action_execution",
                "history",
                "tiers",
                "streaming",
                "prompt_builder",
            ):
                m_name = f"monika.application.agent.chat.{sub}"
                if m_name in sys.modules:
                    setattr(sys.modules[m_name], name, value)


sys.modules[__name__].__class__ = _ChatAgentFacadeModule
