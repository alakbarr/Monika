# ==============================================================================
# File: tests/cli/test_chat_suite.py
# Description: Unit and Integration Test Suite for Monika CLI Chat Subsystem
# ==============================================================================

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from cli.chat.commands import ChatCommandRouter, CommandResult, MODEL_ALIASES
from cli.chat.completer import ChatCommandCompleter
from cli.chat.prompt import ChatPromptManager
from cli.chat.renderer import ChatRenderer, ThinkingScrubber
from cli.chat.session import ChatReplSession
from cli.chat.theme import (
    GLYPH_AGENT,
    GLYPH_THINK,
    GLYPH_TOOL,
    GLYPH_USER,
    ChatPalette,
    get_chat_palette,
)
from prompt_toolkit.document import Document


# ------------------------------------------------------------------------------
# 1. Theme and Palette Tests
# ------------------------------------------------------------------------------

def test_chat_palette_defaults():
    """Verify default palette values and theme derivation."""
    palette = get_chat_palette("retro_vintage")
    assert palette.primary is not None
    assert palette.accent is not None
    assert palette.user is not None
    assert palette.agent is not None
    assert palette.thinking is not None
    assert palette.success is not None
    assert palette.danger is not None


def test_chat_palette_switching():
    """Verify modern_dark and high_contrast theme derivation."""
    palette_dark = get_chat_palette("modern_dark")
    assert palette_dark.background == "#0F172A"

    palette_contrast = get_chat_palette("high_contrast")
    assert palette_contrast.background == "#000000"


# ------------------------------------------------------------------------------
# 2. Thinking Scrubber Tests
# ------------------------------------------------------------------------------

def test_thinking_scrubber_single_chunk():
    """Verify complete thinking block within a single chunk."""
    scrubber = ThinkingScrubber()
    think, content = scrubber.process_chunk("<think>Checking RSI values</think>Based on RSI, EURUSD is oversold.")
    assert think == "Checking RSI values"
    assert content == "Based on RSI, EURUSD is oversold."
    assert scrubber.get_full_thinking() == "Checking RSI values"
    assert scrubber.get_full_content() == "Based on RSI, EURUSD is oversold."


def test_thinking_scrubber_split_chunks():
    """Verify thinking tags split across multiple token stream chunks."""
    scrubber = ThinkingScrubber()

    t1, c1 = scrubber.process_chunk("Hello. <th")
    assert c1 == "Hello. "
    assert t1 is None

    t2, c2 = scrubber.process_chunk("ink>Reasoning step 1. ")
    assert t2 == "Reasoning step 1. "
    assert c2 is None

    t3, c3 = scrubber.process_chunk("Reasoning step 2.</th")
    assert t3 == "Reasoning step 2."
    assert c3 is None

    t4, c4 = scrubber.process_chunk("ink>Final response here.")
    assert t4 is None
    assert c4 == "Final response here."

    assert scrubber.get_full_thinking() == "Reasoning step 1. Reasoning step 2."
    assert scrubber.get_full_content() == "Hello. Final response here."


# ------------------------------------------------------------------------------
# 3. Chat Renderer Tests
# ------------------------------------------------------------------------------

def test_chat_renderer_visual_elements(capsys):
    """Test renderer visual output blocks."""
    test_console = Console(record=True, width=90)
    renderer = ChatRenderer(theme_name="retro_vintage", console=test_console)

    # 1. Banner
    renderer.render_banner("auto", "PAPER", "sess_123", is_live_service=True)
    out = test_console.export_text()
    assert "MONIKA QUANTITATIVE TRADING DESK" in out
    assert "ONLINE" in out

    # 2. User prompt
    renderer.render_user_prompt("Analyze XAUUSD liquidity")
    out = test_console.export_text()
    assert "Analyze XAUUSD liquidity" in out
    assert "User" in out

    # 3. Thinking card
    renderer.render_thinking_card("Analyzing Order Book depth...", elapsed_s=1.2)
    out = test_console.export_text()
    assert "Reasoning (1.2s)" in out
    assert "Analyzing Order Book depth..." in out

    # 4. Tool start and result
    renderer.render_tool_start("fetch_market_depth", {"symbol": "EURUSD", "depth": 10})
    renderer.render_tool_result("fetch_market_depth", summary="Fetched 10 depth levels", duration_ms=45.0)
    out = test_console.export_text()
    assert "fetch_market_depth" in out
    assert "OK" in out

    # 5. Approval card
    action = {
        "id": "act_999",
        "description": "Execute Market Order",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "volume": 0.10,
        "sl": 2650.0,
        "tp": 2690.0,
    }
    renderer.render_approval_card(action)
    out = test_console.export_text()
    assert "TRADE AUTHORIZATION REQUIRED" in out
    assert "XAUUSD" in out
    assert "/allow" in out

    # 6. Telemetry footer
    renderer.render_telemetry_footer(tokens_in=120, tokens_out=340, latency_s=0.85)
    out = test_console.export_text()
    assert "460 tokens" in out
    assert "0.85s" in out


# ------------------------------------------------------------------------------
# 4. Auto-Completer Tests
# ------------------------------------------------------------------------------

def test_chat_completer():
    """Verify ChatCommandCompleter completions."""
    completer = ChatCommandCompleter()

    # Slash prefix -> all slash commands suggested
    doc_empty = Document("/")
    completions = [c.text for c in completer.get_completions(doc_empty, None)]
    assert "/help" in completions
    assert "/model" in completions
    assert "/positions" in completions
    assert "/status" in completions

    # Prefix match
    doc_p = Document("/po")
    completions = [c.text for c in completer.get_completions(doc_p, None)]
    assert completions == ["/positions"]

    # Model argument completion
    doc_model = Document("/model f")
    completions = [c.text for c in completer.get_completions(doc_model, None)]
    assert "fast" in completions

    # Theme argument completion
    doc_theme = Document("/theme r")
    completions = [c.text for c in completer.get_completions(doc_theme, None)]
    assert "retro_vintage" in completions


# ------------------------------------------------------------------------------
# 5. Slash Command Router Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_command_router_basic():
    """Verify basic slash commands (/help, /clear, /exit, /model, /theme)."""
    test_console = Console(record=True, width=90)
    renderer = ChatRenderer(console=test_console)
    prompt_mgr = ChatPromptManager()
    router = ChatCommandRouter(renderer, prompt_mgr)

    # 1. Non-command
    res = await router.handle("Hello Monika")
    assert not res.handled

    # 2. /help
    res = await router.handle("/help")
    assert res.handled
    assert "MONIKA INTERACTIVE COMMAND REFERENCE" in test_console.export_text()

    # 3. /model
    res = await router.handle("/model fast")
    assert res.handled
    assert prompt_mgr.active_model == "gemini-3.5-flash-lite"

    res = await router.handle("/model reasoning")
    assert res.handled
    assert prompt_mgr.active_model == "gemini-3.8-flash"

    # 4. /theme
    res = await router.handle("/theme modern_dark")
    assert res.handled
    assert renderer.theme_name == "modern_dark"

    # 5. /exit
    res = await router.handle("/exit")
    assert res.handled
    assert res.should_exit


@pytest.mark.asyncio
async def test_command_router_trade_approvals():
    """Verify /allow, /deny, /session generate proper payloads."""
    test_console = Console(record=True, width=90)
    renderer = ChatRenderer(console=test_console)
    prompt_mgr = ChatPromptManager()
    router = ChatCommandRouter(renderer, prompt_mgr)

    # /allow with pending id
    res = await router.handle("/allow", pending_action_id="act_456")
    assert res.handled
    assert res.action_payload == {
        "type": "approval_response",
        "action_id": "act_456",
        "decision": "allow_once",
    }

    # /deny with explicit arg
    res = await router.handle("/deny act_789")
    assert res.handled
    assert res.action_payload == {
        "type": "approval_response",
        "action_id": "act_789",
        "decision": "deny",
    }

    # /session
    res = await router.handle("/session", pending_action_id="act_456")
    assert res.handled
    assert res.action_payload["decision"] == "allow_session"


@pytest.mark.asyncio
async def test_command_router_export():
    """Verify /export creates valid transcript file."""
    test_console = Console(record=True, width=90)
    renderer = ChatRenderer(console=test_console)
    prompt_mgr = ChatPromptManager()
    router = ChatCommandRouter(renderer, prompt_mgr)

    history = [
        {"sender": "user", "text": "What is the RSI of EURUSD?"},
        {"sender": "agent", "text": "EURUSD RSI(14) is currently 42.5."},
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        md_file = os.path.join(tmp_dir, "test_export.md")
        res = await router.handle(f"/export {md_file}", history_records=history)
        assert res.handled
        assert os.path.exists(md_file)
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Monika Chat Transcript Export" in content
            assert "EURUSD RSI(14) is currently 42.5" in content

        json_file = os.path.join(tmp_dir, "test_export.json")
        res2 = await router.handle(f"/export {json_file}", history_records=history)
        assert res2.handled
        assert os.path.exists(json_file)


# ------------------------------------------------------------------------------
# 6. Prompt Manager & Bottom Toolbar Tests
# ------------------------------------------------------------------------------

def test_prompt_manager_toolbar():
    """Verify prompt manager dynamic bottom toolbar HTML generation."""
    pm = ChatPromptManager()
    pm.update_telemetry(
        model="gemini-3.8-flash",
        mode="LIVE",
        status="ONLINE",
        latency_s=1.45,
        tokens=350,
    )

    toolbar_html = pm._get_bottom_toolbar()
    html_text = toolbar_html.value
    assert "MONIKA" in html_text
    assert "gemini-3.8-flash" in html_text
    assert "LIVE" in html_text
    assert "ONLINE" in html_text
    assert "350 tok" in html_text
    assert ("1.4s" in html_text or "1.5s" in html_text)


# ------------------------------------------------------------------------------
# 7. Chat REPL Session Lifecycle Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_repl_session_interrupt():
    """Verify single-turn interrupt handling."""
    session = ChatReplSession(offline=True)
    mock_agent = MagicMock()
    mock_agent.interrupt = MagicMock(return_value=True)
    session.local_agent = mock_agent

    mock_task = MagicMock()
    mock_task.done.return_value = False
    session.current_turn_task = mock_task

    # Trigger interrupt
    session._handle_interrupt()

    assert session.is_interrupted
    mock_agent.interrupt.assert_called_once()
    mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_chat_repl_session_offline_turn():
    """Verify offline local agent execution turn."""
    session = ChatReplSession(offline=True)
    mock_agent = MagicMock()
    mock_agent.handle = AsyncMock(return_value=("Analysis complete: No risk breach.", None))
    session.local_agent = mock_agent

    await session._execute_turn("Check risk exposure")

    assert len(session.history) == 1
    assert session.history[0]["sender"] == "agent"
    assert "Analysis complete" in session.history[0]["text"]
