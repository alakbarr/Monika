# ==============================================================================
# File: cli/chat/__init__.py
# Description: Public Interface for Monika CLI Chat Subsystem
# ==============================================================================

"""
Monika CLI Interactive Chat Subsystem.
Provides institutional-grade trading desk console benchmarked against
Google Antigravity CLI (agy), Hermes Agent, and Pi.
"""

from typing import Optional

from cli.chat.commands import ChatCommandRouter, CommandResult
from cli.chat.completer import ChatCommandCompleter
from cli.chat.prompt import ChatPromptManager
from cli.chat.renderer import ChatRenderer, ThinkingScrubber
from cli.chat.session import ChatReplSession, DEFAULT_API_URL
from cli.chat.theme import ChatPalette, get_chat_palette


async def run_cli_chat(
    api_url: str = DEFAULT_API_URL,
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    offline: bool = False,
    model: str = "auto",
    theme: str = "retro_vintage",
) -> None:
    """
    Launch interactive standalone CLI Chat trading desk session.

    Args:
        api_url: Base HTTP URL of Monika dashboard/gateway.
        api_key: Optional API key / bearer token.
        session_id: Unique chat session identifier.
        offline: If True, bypass WebSocket connection and run local ChatAgent.
        model: Initial LLM model routing tier or name.
        theme: UI theme palette ('retro_vintage', 'matrix_terminal', etc.).
    """
    session = ChatReplSession(
        api_url=api_url,
        api_key=api_key,
        session_id=session_id,
        offline=offline,
        model=model,
        theme=theme,
    )
    await session.run()


__all__ = [
    "run_cli_chat",
    "ChatReplSession",
    "ChatRenderer",
    "ThinkingScrubber",
    "ChatPromptManager",
    "ChatCommandCompleter",
    "ChatCommandRouter",
    "CommandResult",
    "ChatPalette",
    "get_chat_palette",
    "DEFAULT_API_URL",
]
