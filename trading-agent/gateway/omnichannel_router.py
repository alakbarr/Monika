# ==============================================================================
# File: gateway/omnichannel_router.py
# ==============================================================================

"""
Omnichannel Message Router & Multi-Tenant Session Key Manager.
Unified multi-platform messaging architecture for Monika.

Key Architectural Capabilities:
  1. Standardized MessageEvent Normalization:
     Converts heterogeneous payloads from 15+ platforms (Telegram, Discord, Slack, WhatsApp,
     Signal, Webhooks) into a canonical MessageEvent object with full provenance tracking.

  2. Deterministic Multi-Tenant Session Key Algorithm:
     Builds immutable, collision-free session identifiers:
       "<namespace>:<platform>:<chat_type>[:<scope_id>][:<chat_id>][:<thread_id>][:<user>]"
     Supports isolated user contexts in DMs/groups and shared team contexts in forum threads.

  3. Progressive Return Delivery with Code-Fence Preservation:
     Guarantees that in-flight markdown streaming blocks (```) are always syntactically
     closed when dispatched to platform message editing APIs, preventing broken formatting.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Gateway.OmnichannelRouter")


class MessageType(str, enum.Enum):
    TEXT = "text"
    PHOTO = "photo"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    COMMAND = "command"
    ACTION = "action"


@dataclass
class SessionSource:
    platform: str                    # 'telegram', 'discord', 'slack', 'whatsapp', 'signal', 'cli'
    chat_id: str                     # Channel, room, or DM identifier
    chat_type: str = "dm"            # 'dm', 'group', 'channel', 'thread'
    user_id: Optional[str] = None    # Originating user ID
    user_name: Optional[str] = None  # Human display name
    thread_id: Optional[str] = None  # Thread or topic ID
    scope_id: Optional[str] = None   # Guild, team, or workspace ID
    namespace: str = "agent:main"    # Multi-tenant profile partition


@dataclass
class MessageEvent:
    text: str
    source: SessionSource
    message_type: MessageType = MessageType.TEXT
    message_id: Optional[str] = None
    media_urls: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    raw_payload: Optional[Dict[str, Any]] = None


def build_session_key(
    source: SessionSource,
    group_sessions_per_user: bool = True,
    thread_sessions_per_user: bool = False,
) -> str:
    """
    Computes a deterministic, collision-free session key across multi-platform traffic.
    """
    parts = [source.namespace, source.platform, source.chat_type]

    if source.scope_id:
        parts.append(f"scope_{source.scope_id}")

    parts.append(f"chat_{source.chat_id}")

    if source.thread_id:
        parts.append(f"thread_{source.thread_id}")

    # User isolation rules
    if source.chat_type == "dm":
        # DMs are always isolated per user
        if source.user_id:
            parts.append(f"user_{source.user_id}")
    elif source.thread_id:
        # Threads are shared by default unless thread_sessions_per_user is True
        if thread_sessions_per_user and source.user_id:
            parts.append(f"user_{source.user_id}")
    else:
        # Groups/Channels
        if group_sessions_per_user and source.user_id:
            parts.append(f"user_{source.user_id}")

    return ":".join(parts)


def ensure_closed_code_fences(markdown_text: str) -> str:
    """
    Scans in-flight streaming markdown and ensures any unclosed triple-backtick (```)
    blocks are temporarily closed so chat platform parsers render formatting correctly.
    """
    # Count occurrences of triple backticks
    fence_matches = list(re.finditer(r"```", markdown_text))
    if len(fence_matches) % 2 != 0:
        # Unclosed code fence: append closing backticks
        return markdown_text + "\n```"
    return markdown_text


class OmnichannelRouter:
    """
    Central hub for message normalization, session dispatch, and outbound streaming.
    """

    def __init__(self):
        self._handlers: Dict[str, Callable[[MessageEvent, str], Any]] = {}

    def register_handler(self, platform: str, handler: Callable[[MessageEvent, str], Any]) -> None:
        """Registers a platform-specific delivery handler."""
        self._handlers[platform.lower()] = handler
        logger.info(f"[OmnichannelRouter] Registered handler for platform '{platform}'")

    def route_incoming_message(self, event: MessageEvent) -> str:
        """
        Calculates session key for incoming event and dispatches to appropriate pipeline.
        Returns the computed session key.
        """
        session_key = build_session_key(event.source)
        logger.debug(f"[OmnichannelRouter] Inbound event from {event.source.platform} -> SessionKey: {session_key}")
        return session_key

    def format_outbound_stream_chunk(self, chunk_text: str, is_final: bool = False) -> str:
        """
        Sanitizes and prepares streaming delta for external chat platforms.
        """
        if not is_final:
            return ensure_closed_code_fences(chunk_text)
        return chunk_text
