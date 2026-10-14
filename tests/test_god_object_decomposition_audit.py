# ==============================================================================
# File: tests/test_phase4_god_object_decomposition_audit.py
# Phase 4 God Object Decomposition & Layer Decoupling Verification
# ==============================================================================

import inspect
from pathlib import Path
import sys
from typing import Any
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
    assert CoreChatAgent.__module__ in ("monika.application.agent.chat_agent", "monika.application.agent.chat_agent")
    assert PendingAction.__module__ in ("monika.application.agent.chat_agent", "monika.application.agent.chat_agent")

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


def test_models_decomposition_facade_and_submodules():
    """Verify that models.py and all domain_models submodules are <= 800 lines and synchronized."""
    from pathlib import Path
    from monika.infrastructure.database import models
    from monika.infrastructure.database import domain_models

    dm_dir = Path("src/monika/infrastructure/database/domain_models")
    assert dm_dir.is_dir()

    for py_file in dm_dir.glob("*.py"):
        line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, f"{py_file} exceeds 800 LOC ({line_count} lines)"

    models_path = Path("src/monika/infrastructure/database/models.py")
    models_lines = len(models_path.read_text(encoding="utf-8").splitlines())
    assert models_lines <= 800, f"models.py exceeds 800 LOC ({models_lines} lines)"

    # Identity check
    assert models.Base is domain_models.Base
    assert models.Trade is domain_models.Trade
    assert models.Order is domain_models.Order
    assert models.Position is domain_models.Position
    assert models.PriceOHLCV is domain_models.PriceOHLCV
    assert models.AssetAnalysis is domain_models.AssetAnalysis
    assert models.SystemConfig is domain_models.SystemConfig

    # Total classes parity
    assert len(models.__all__) >= 74
    for sym in models.__all__:
        assert hasattr(models, sym), f"Missing {sym} on models"
        assert hasattr(domain_models, sym), f"Missing {sym} on domain_models"

    # Monkeypatch synchronization
    original = models.Trade
    try:
        dummy: Any = object()
        setattr(models, "Trade", dummy)
        assert domain_models.Trade is dummy
        import monika.infrastructure.database.domain_models.trading as dm_trading

        assert dm_trading.Trade is dummy
    finally:
        setattr(models, "Trade", original)
        assert domain_models.Trade is original


def test_tui_decomposition_facade_and_submodules():
    """Verify interfaces/cli/tui.py decomposition into tui_app with submodules <= 800 LOC."""
    from monika.interfaces.cli import tui
    from monika.interfaces.cli import tui_app

    tui_app_dir = Path("src/monika/interfaces/cli/tui_app")
    assert tui_app_dir.is_dir()

    for py_file in tui_app_dir.rglob("*.py"):
        line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, f"{py_file} exceeds 800 LOC ({line_count} lines)"

    tui_path = Path("src/monika/interfaces/cli/tui.py")
    tui_lines = len(tui_path.read_text(encoding="utf-8").splitlines())
    assert tui_lines <= 800, f"tui.py exceeds 800 LOC ({tui_lines} lines)"

    # Identity check
    assert tui.TradingDashboard is tui_app.TradingDashboard
    assert tui.TradingAgentApp is tui_app.TradingAgentApp
    assert tui.LiveTickerBanner is tui_app.LiveTickerBanner
    assert tui.StatusBar is tui_app.StatusBar
    assert tui.KillConfirmModalScreen is tui_app.KillConfirmModalScreen
    assert tui.run_tui is tui_app.run_tui
    assert tui.DEFAULT_API_URL == tui_app.DEFAULT_API_URL
    assert tui.COMMAND_SUGGESTIONS == tui_app.COMMAND_SUGGESTIONS
    assert tui.DETERMINISTIC_RISK_CHECKS == tui_app.DETERMINISTIC_RISK_CHECKS

    # Monkeypatch synchronization
    original = tui.TradingDashboard
    try:
        dummy: Any = object()
        setattr(tui, "TradingDashboard", dummy)
        assert tui_app.TradingDashboard is dummy
        import monika.interfaces.cli.tui_app.dashboard as tui_dashboard

        assert tui_dashboard.TradingDashboard is dummy
    finally:
        setattr(tui, "TradingDashboard", original)
        assert tui_app.TradingDashboard is original


def test_per_asset_runner_decomposition_and_submodules():
    """Verify application/analysis/stages/per_asset/runner.py decomposition into runner_mixins <= 800 LOC."""
    from monika.application.analysis.stages.per_asset import runner
    from monika.application.analysis.stages.per_asset import runner_mixins
    from monika.application.analysis.stages.per_asset_stage import PerAssetStage

    runner_mixins_dir = Path("src/monika/application/analysis/stages/per_asset/runner_mixins")
    assert runner_mixins_dir.is_dir()

    for py_file in runner_mixins_dir.rglob("*.py"):
        line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        assert line_count <= 800, f"{py_file} exceeds 800 LOC ({line_count} lines)"

    runner_path = Path("src/monika/application/analysis/stages/per_asset/runner.py")
    runner_lines = len(runner_path.read_text(encoding="utf-8").splitlines())
    assert runner_lines <= 800, f"runner.py exceeds 800 LOC ({runner_lines} lines)"

    # Verify inheritance structure
    assert issubclass(runner.PerAssetRunner, runner_mixins.BatchOrchestratorMixin)
    assert issubclass(runner.PerAssetRunner, runner_mixins.PrescreenMixin)
    assert issubclass(runner.PerAssetRunner, runner_mixins.RecoveryMixin)
    assert issubclass(runner.PerAssetRunner, runner_mixins.PostProcessVerificationMixin)
    assert issubclass(runner.PerAssetRunner, runner_mixins.SingleAssetAnalysisMixin)
    assert issubclass(PerAssetStage, runner.PerAssetRunner)

    # Verify functions
    assert callable(runner._get_asyncio)
    assert callable(runner._get_clock)
