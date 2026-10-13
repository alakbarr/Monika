# ==============================================================================
# File: tests/test_phase4_toolsets_and_terminal_guard.py
# ==============================================================================

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.application.analysis.tools.unified_registry import (
    unified_tool_registry,
    TRADING_TOOLSET,
    DEVELOPER_TOOLSET,
    RESEARCH_TOOLSET,
    TOOLSETS,
)
from monika.interfaces.dashboard.pty_bridge import PtySession
from monika.infrastructure.llm.context_compressor import (
    get_context_compressor,
    compress_context,
    prune_oversized_tool_results,
)


def test_modular_toolset_definitions():
    """Verify standard toolsets are correctly configured and partitioned."""
    assert len(TRADING_TOOLSET) > 0
    assert len(DEVELOPER_TOOLSET) > 0
    assert len(RESEARCH_TOOLSET) > 0

    assert "TRADING" in TOOLSETS
    assert "DEVELOPER" in TOOLSETS
    assert "RESEARCH" in TOOLSETS

    # Test list_toolset_names method
    trading_names = unified_tool_registry.list_toolset_names("TRADING")
    dev_names = unified_tool_registry.list_toolset_names("DEVELOPER")
    research_names = unified_tool_registry.list_toolset_names("RESEARCH")

    assert isinstance(trading_names, list)
    assert isinstance(dev_names, list)
    assert isinstance(research_names, list)

    with pytest.raises(ValueError):
        unified_tool_registry.list_toolset_names("NONEXISTENT_TOOLSET")


def test_get_toolset_schemas():
    """Verify toolset serialization for OpenAI, Anthropic, and Gemini formats."""
    schemas_openai = unified_tool_registry.get_toolset("TRADING", format="openai")
    schemas_anthropic = unified_tool_registry.get_toolset("DEVELOPER", format="anthropic")
    schemas_gemini = unified_tool_registry.get_toolset("RESEARCH", format="gemini")

    assert isinstance(schemas_openai, list)
    assert isinstance(schemas_anthropic, list)
    assert isinstance(schemas_gemini, list)


@pytest.mark.asyncio
async def test_pty_session_terminal_guard_allows_safe_command():
    """Verify benign commands pass through to PTY stdin."""
    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_proc.stdin = mock_stdin

    session = PtySession(
        session_id="test_safe_session",
        created_at=1000.0,
        last_active=1000.0,
        process=mock_proc,
    )

    await session.write_input("ls -la\r\n")

    # Stdin should have received the safe input
    mock_stdin.write.assert_called_with(b"ls -la\r\n")
    assert len(session._output_buffer) == 0


@pytest.mark.asyncio
async def test_pty_session_terminal_guard_blocks_destructive_command():
    """Verify dangerous commands are blocked by TerminalGuard and emit security alert."""
    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_proc.stdin = mock_stdin

    session = PtySession(
        session_id="test_danger_session",
        created_at=1000.0,
        last_active=1000.0,
        process=mock_proc,
    )

    # Attempt to send destructive command
    await session.write_input("rm -rf /\r\n")

    # Stdin must receive SIGINT (\x03) instead of the dangerous command
    mock_stdin.write.assert_called_with(b"\x03")

    # Output buffer must contain security alert
    output_history = session.get_history()
    assert "[SECURITY ALERT]" in output_history
    assert "TerminalGuard" in output_history


@pytest.mark.asyncio
async def test_unified_context_compressor():
    """Verify unified context compressor facade and tool result pruning."""
    compressor = get_context_compressor()
    assert compressor is not None

    messages = [
        {"role": "user", "content": "Analyze market"},
        {
            "role": "tool",
            "content": [{"type": "tool_result", "content": "x" * 20000}],
        },
        {"role": "user", "content": "What is the verdict?"},
    ]

    pruned = prune_oversized_tool_results(messages, threshold_chars=5000, head_chars=1000, tail_chars=500)
    assert len(pruned) == 3
    tool_content = str(pruned[1]["content"])
    assert len(tool_content) < 20000

    compressed = await compress_context(messages, max_context_chars=5000)
    assert len(compressed) > 0
