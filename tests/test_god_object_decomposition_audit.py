# ==============================================================================
# File: tests/test_phase4_god_object_decomposition_audit.py
# Phase 4 God Object Decomposition & Layer Decoupling Verification
# ==============================================================================

import inspect
import sys
from unittest.mock import patch, MagicMock
import pytest


def test_risk_gate_node_modular_subpackage():
    """Verify that graph.nodes.risk sub-package exposes pure modular components."""
    from monika.application.graph.nodes.risk import (
        _safe_num,
        resolve_and_repair_levels,
        audit_trade_rejection,
        run_quant_arbitration,
        ai_portfolio_synthesis,
        apply_portfolio_synthesis_reduction,
        send_proposal_notifications,
    )
    from monika.application.graph.nodes.risk_gate_node import risk_gate_node

    assert callable(risk_gate_node)
    assert callable(_safe_num)
    assert callable(resolve_and_repair_levels)
    assert callable(audit_trade_rejection)
    assert callable(run_quant_arbitration)
    assert callable(ai_portfolio_synthesis)
    assert callable(apply_portfolio_synthesis_reduction)
    assert callable(send_proposal_notifications)


def test_chat_agent_domain_layer_isolation():
    """Verify that chat_agent contains the authoritative CoreChatAgent implementation."""
    from monika.application.agent.chat_agent import ChatAgent as CoreChatAgent, PendingAction

    # Ensure CoreChatAgent is defined in monika.application.agent.chat_agent, not re-exported from telegram
    assert CoreChatAgent.__module__ in ("monika.application.agent.chat_agent", "agent.chat_agent")
    assert PendingAction.__module__ in ("monika.application.agent.chat_agent", "agent.chat_agent")

    # CoreChatAgent must have all conversational methods
    assert hasattr(CoreChatAgent, "handle")
    assert hasattr(CoreChatAgent, "_handle_internal")
    assert hasattr(CoreChatAgent, "_handle_token_callback_stream")
    assert hasattr(CoreChatAgent, "_classify_query_complexity")
    assert hasattr(CoreChatAgent, "confirm_action")
    assert hasattr(CoreChatAgent, "reject_action")


def test_telegram_chat_agent_subclasses_core_agent():
    """Verify that telegram_bot.chat_agent subclasses CoreChatAgent and re-exports cleanly."""
    from monika.application.agent.chat_agent import ChatAgent as CoreChatAgent
    import monika.interfaces.telegram.chat_agent as tg_mod
    from monika.interfaces.telegram.chat_agent import ChatAgent as TGChatAgent, TelegramChatAgent

    assert issubclass(TelegramChatAgent, CoreChatAgent)
    assert TGChatAgent is TelegramChatAgent
    assert hasattr(tg_mod, "TELEGRAM_MAX_CHARS")
    assert hasattr(tg_mod, "_sanitize_telegram_format")


def test_module_proxy_synchronizes_mocks():
    """Verify that patching telegram_bot.chat_agent transparently mirrors to agent.chat_agent."""
    import monika.application.agent.chat_agent as core_mod
    import monika.interfaces.telegram.chat_agent as tg_mod

    mock_client = MagicMock()
    with patch("monika.interfaces.telegram.chat_agent.get_client_for_task", return_value=mock_client):
        assert tg_mod.get_client_for_task("test") is mock_client
        assert core_mod.get_client_for_task("test") is mock_client

    # Verify restoration after context manager exit
    assert tg_mod.get_client_for_task is not mock_client
    assert core_mod.get_client_for_task is not mock_client


def test_headless_callers_do_not_import_telegram_bot_chat_agent():
    """Verify that headless gateways and engines import from agent.chat_agent directly."""
    import monika.interfaces.gateway.api_server as api_mod
    import monika.application.scheduler.unified_cron_engine as cron_mod
    import monika.interfaces.cli.main as cli_main_mod

    # Check source code of key functions for direct core chat_agent imports
    api_src = inspect.getsource(api_mod.get_default_chat_agent)
    assert "monika.application.agent.chat_agent" in api_src or "from agent.chat_agent import ChatAgent" in api_src

    cron_src = inspect.getsource(cron_mod.UnifiedCronEngine._dispatch_job)
    assert "monika.application.agent.chat_agent" in cron_src or "from agent.chat_agent import ChatAgent" in cron_src

    cli_src = inspect.getsource(cli_main_mod._cmd_ask)
    assert "monika.application.agent.chat_agent" in cli_src or "from agent.chat_agent import ChatAgent" in cli_src
