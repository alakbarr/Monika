# ==============================================================================
# File: tests/test_architecture_parity.py
# ==============================================================================

"""
Test Architecture Parity and Clean Service Layer Facades (Phase 5).
Verifies two-way import parity between src/monika/ and trading-agent/ shims,
as well as functional correctness of the Application Service Layer.
"""

import time
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock

# 1. Canonical imports from src/monika
from monika.application.services import (
    TradingService as CanonicalTradingService,
    MarketIntelService as CanonicalMarketIntelService,
    GeneralHarnessService as CanonicalGeneralHarnessService,
    PortfolioService as CanonicalPortfolioService,
    OrderPreviewResult,
    TradeExecutionResult,
)

# 2. Compatibility shim imports from trading-agent/services
from monika.application.services import (
    TradingService as ShimTradingService,
    MarketIntelService as ShimMarketIntelService,
    GeneralHarnessService as ShimGeneralHarnessService,
    PortfolioService as ShimPortfolioService,
)


def test_service_layer_class_identity_parity():
    """Verify shims export identical class references as canonical implementations."""
    assert ShimTradingService is CanonicalTradingService
    assert ShimMarketIntelService is CanonicalMarketIntelService
    assert ShimGeneralHarnessService is CanonicalGeneralHarnessService
    assert ShimPortfolioService is CanonicalPortfolioService


def test_trading_service_preview_token_lifecycle():
    """Verify pre-trade token generation, signature validation, and expiration."""
    symbol = "EURUSD"
    action = "BUY"
    volume = 0.5
    now = time.time()
    expires_at = now + 60.0

    token = CanonicalTradingService.generate_preview_token(symbol, action, volume, expires_at)
    assert isinstance(token, str)
    assert len(token) == 64  # SHA256 hex digest length

    # Valid token verification
    assert CanonicalTradingService.verify_preview_token(token, symbol, action, volume, expires_at) is True

    # Tampered volume
    assert CanonicalTradingService.verify_preview_token(token, symbol, action, 1.0, expires_at) is False

    # Tampered symbol
    assert CanonicalTradingService.verify_preview_token(token, "GBPUSD", action, volume, expires_at) is False

    # Expired token
    expired_at = now - 10.0
    expired_token = CanonicalTradingService.generate_preview_token(symbol, action, volume, expired_at)
    assert CanonicalTradingService.verify_preview_token(expired_token, symbol, action, volume, expired_at) is False


@pytest.mark.asyncio
async def test_trading_service_preview_and_paper_submit(db_session):
    """Verify manual order preview calculation and paper execution flow."""
    preview = await CanonicalTradingService.preview_manual_order(
        session=db_session,
        symbol="XAUUSD",
        action="BUY",
        volume=0.1,
        entry_price=2650.0,
        stop_loss=2640.0,
        take_profit=2670.0,
        is_paper=True,
    )

    assert isinstance(preview, OrderPreviewResult)
    assert preview.symbol == "XAUUSD"
    assert preview.action == "BUY"
    assert preview.estimated_risk_usd > 0
    assert preview.estimated_reward_usd > 0
    assert preview.preview_token is not None

    # Submit paper order with valid preview token
    exec_res = await CanonicalTradingService.submit_order(
        session=db_session,
        symbol=preview.symbol,
        action=preview.action,
        volume=preview.volume,
        entry_price=preview.entry_price,
        stop_loss=preview.stop_loss,
        take_profit=preview.take_profit,
        is_paper=True,
        preview_token=preview.preview_token,
        token_expires_at=preview.expires_at,
        actor="unit_test",
    )

    assert isinstance(exec_res, TradeExecutionResult)
    assert exec_res.success is True
    assert exec_res.ticket is not None
    assert exec_res.is_paper is True

    # Verify position is queryable via CanonicalPortfolioService
    open_positions = await CanonicalPortfolioService.get_open_positions(db_session, symbol="XAUUSD")
    assert len(open_positions) == 1
    assert open_positions[0].symbol == "XAUUSD"
    assert float(open_positions[0].volume or 0.0) == 0.1


@pytest.mark.asyncio
async def test_trading_service_emergency_kill(db_session):
    """Verify emergency kill switch activates and records audit state."""
    result = await CanonicalTradingService.emergency_kill(
        session=db_session,
        reason="Test emergency stop",
        actor="test_runner",
    )

    assert result["status"] == "HALTED"
    assert result["actor"] == "test_runner"
    assert result["reason"] == "Test emergency stop"

    # Subsequent order submission must be blocked by kill switch
    rejected = await CanonicalTradingService.submit_order(
        session=db_session,
        symbol="EURUSD",
        action="BUY",
        volume=0.1,
        entry_price=1.1000,
        is_paper=True,
    )
    assert rejected.success is False
    assert "kill switch" in (rejected.error_message or "").lower()


def test_general_harness_service_toolset_queries():
    """Verify GeneralHarnessService toolset queries and schemas."""
    trading_tools = CanonicalGeneralHarnessService.get_toolset_names("TRADING")
    dev_tools = CanonicalGeneralHarnessService.get_toolset_names("DEVELOPER")
    research_tools = CanonicalGeneralHarnessService.get_toolset_names("RESEARCH")

    assert isinstance(trading_tools, list)
    assert isinstance(dev_tools, list)
    assert isinstance(research_tools, list)

    schemas = CanonicalGeneralHarnessService.get_toolset_schema("TRADING", format="openai")
    assert isinstance(schemas, list)


def test_market_intel_service_alpha_evaluation():
    """Verify MarketIntelService executes alpha factor evaluation on OHLCV data."""
    # Create sample synthetic dataframe
    dates = pd.date_range("2026-01-01", periods=50, freq="1h")
    df = pd.DataFrame(
        {
            "open": [1.1000 + i * 0.0005 for i in range(50)],
            "high": [1.1020 + i * 0.0005 for i in range(50)],
            "low": [1.0990 + i * 0.0005 for i in range(50)],
            "close": [1.1010 + i * 0.0005 for i in range(50)],
            "volume": [1000.0 + i * 10 for i in range(50)],
        },
        index=dates,
    )

    result = CanonicalMarketIntelService.evaluate_alpha_factors(
        symbol="EURUSD",
        df=df,
        regime="trending",
        top_k=3,
    )

    assert result is not None
    assert result.symbol == "EURUSD"
    assert result.regime == "trending"
    prompt_context = result.to_prompt_context()
    assert "EURUSD" in prompt_context


def test_domain_core_class_identity_and_functional_parity():
    """Verify PR-1 domain core shims preserve exact object identity and runtime state."""
    # 1. Risk Domain Identity
    import monika.domain.risk.trade_proposal as shim_tp
    import monika.domain.risk.trade_proposal as canon_tp

    assert shim_tp.TradeProposal is canon_tp.TradeProposal

    import monika.domain.risk.risk_gate as shim_rg
    import monika.domain.risk.risk_gate as canon_rg

    assert shim_rg.RiskGate is canon_rg.RiskGate

    import monika.domain.risk.position_sizing as shim_ps
    import monika.domain.risk.position_sizing as canon_ps

    assert shim_ps.PositionSizer is canon_ps.PositionSizer

    # 2. Execution Domain Identity
    import monika.domain.execution.broker_plugin as shim_bp
    import monika.domain.execution.broker_plugin as canon_bp

    assert shim_bp.BrokerPlugin is canon_bp.BrokerPlugin

    import monika.domain.execution.verification_engine as shim_ve
    import monika.domain.execution.verification_engine as canon_ve

    assert shim_ve.EvidenceFirstVerifier is canon_ve.EvidenceFirstVerifier

    # 3. Indicators / Alpha Zoo Identity & Shared Registry State
    import monika.domain.indicators.alpha_zoo.registry as shim_reg
    import monika.domain.indicators.alpha_zoo.registry as canon_reg

    assert shim_reg.FactorRegistry is canon_reg.FactorRegistry

    # Ensure factors registered via canonical or shim are visible in both
    import monika.domain.indicators.alpha_zoo as shim_zoo
    import monika.domain.indicators.alpha_zoo as canon_zoo

    assert shim_zoo.FactorRegistry is canon_zoo.FactorRegistry
    assert len(shim_zoo.FactorRegistry.list_factors()) >= 10
    assert len(canon_zoo.FactorRegistry.list_factors()) >= 10


def test_infrastructure_layer_identity_and_parity():
    """Verify PR-2 infrastructure layer shims preserve exact object identity and runtime contracts."""
    # 1. Database models & engine identity
    import monika.infrastructure.database.models as shim_models
    import monika.infrastructure.database.models as canon_models

    assert shim_models.Base is canon_models.Base
    assert shim_models.Trade is canon_models.Trade

    import monika.infrastructure.database.domain_models as shim_dm
    import monika.infrastructure.database.domain_models as canon_dm

    assert shim_dm.Base is canon_dm.Base
    assert shim_dm.PriceOHLCV is canon_dm.PriceOHLCV

    # 2. Broker adapters identity
    import monika.infrastructure.brokers.broker_adapter as shim_ba
    import monika.infrastructure.brokers.broker_adapter as canon_ba

    assert shim_ba.SimulatedBrokerAdapter is canon_ba.SimulatedBrokerAdapter

    import monika.infrastructure.brokers.approval_transport as shim_at
    import monika.infrastructure.brokers.approval_transport as canon_at

    assert shim_at.ApprovalTransport is canon_at.ApprovalTransport
    assert shim_at.ApprovalRequestPayload is canon_at.ApprovalRequestPayload

    # 3. LLM Providers identity
    import monika.infrastructure.providers.provider_registry as shim_pr
    import monika.infrastructure.providers.provider_registry as canon_pr

    assert shim_pr.ProviderRegistry is canon_pr.ProviderRegistry

    import monika.infrastructure.providers.llm_factory as shim_lf
    import monika.infrastructure.providers.llm_factory as canon_lf

    assert shim_lf.LLMFactory is canon_lf.LLMFactory

    # 4. Credentials & Error taxonomy identity
    import monika.infrastructure.credentials.credential_pool as shim_cp
    import monika.infrastructure.credentials.credential_pool as canon_cp

    assert shim_cp.CredentialPool is canon_cp.CredentialPool

    import monika.infrastructure.credentials.error_taxonomy as shim_et
    import monika.infrastructure.credentials.error_taxonomy as canon_et

    assert shim_et.FailoverReason is canon_et.FailoverReason
    assert shim_et.ErrorClassifier is canon_et.ErrorClassifier

    # 5. TimesFM ML Engine identity
    import monika.infrastructure.ml.timesfm_engine as shim_tfm
    import monika.infrastructure.ml.timesfm_engine as canon_tfm

    assert shim_tfm.TimesFMEngine is canon_tfm.TimesFMEngine


def test_core_foundation_identity_and_parity():
    """Verify class identity and behavioral parity between legacy and canonical core foundation."""
    # 1. Config identity
    import monika.core.config.settings as shim_cfg
    import monika.core.config.settings as canon_cfg

    assert shim_cfg.load_settings is canon_cfg.load_settings

    import monika.core.config.schemas as shim_sch
    import monika.core.config.schemas as canon_sch

    assert shim_sch.TradingAgentConfig is canon_sch.TradingAgentConfig

    # 2. Security identity
    import monika.core.security.terminal_guard as shim_tg
    import monika.core.security.terminal_guard as canon_tg

    assert shim_tg.validate_command is canon_tg.validate_command
    assert shim_tg.assert_safe_read_path is canon_tg.assert_safe_read_path

    import monika.core.security.credential_vault as shim_cv
    import monika.core.security.credential_vault as canon_cv

    assert shim_cv.CredentialVault is canon_cv.CredentialVault

    # 3. Telemetry identity
    import monika.core.telemetry.activity_logger as shim_al
    import monika.core.telemetry.activity_logger as canon_al

    assert shim_al.ActivityLogger is canon_al.ActivityLogger

    import monika.core.telemetry.tracing.tracer as shim_tr
    import monika.core.telemetry.tracing.tracer as canon_tr

    assert shim_tr.AgentTracer is canon_tr.AgentTracer
    assert shim_tr.Span is canon_tr.Span
    assert shim_tr.get_tracer is canon_tr.get_tracer

    # 4. Primitives identity
    import monika.core.primitives.clock as shim_clk
    import monika.core.primitives.clock as canon_clk

    assert shim_clk.now is canon_clk.now
    assert shim_clk.set_simulated_now is canon_clk.set_simulated_now

    import monika.application.protocol.event_bus as shim_eb
    import monika.core.primitives.event_bus as canon_eb

    assert shim_eb.EventBus is canon_eb.EventBus

    import monika.core.primitives.jev_primitives as shim_jev
    import monika.core.primitives.jev_primitives as canon_jev

    assert shim_jev.Choice is canon_jev.Choice
    assert shim_jev.Score is canon_jev.Score


def test_interface_layer_identity_and_parity():
    """Verify class identity and behavioral parity between legacy and canonical interface layer."""
    # 1. Telegram identity & sub-routers
    import monika.interfaces.telegram.bot as shim_tgb
    import monika.interfaces.telegram.bot as canon_tgb

    assert shim_tgb.TelegramBot is canon_tgb.TelegramBot

    import monika.interfaces.telegram.command_router as shim_cr
    import monika.interfaces.telegram.command_router as canon_cr

    assert shim_cr.CommandType is canon_cr.CommandType
    assert shim_cr.ParsedCommand is canon_cr.ParsedCommand

    import monika.interfaces.telegram.routers as shim_routers
    import monika.interfaces.telegram.routers as canon_routers

    assert shim_routers.TradingRouter is canon_routers.TradingRouter
    assert shim_routers.RiskRouter is canon_routers.RiskRouter
    assert shim_routers.MarketRouter is canon_routers.MarketRouter
    assert shim_routers.QuantRouter is canon_routers.QuantRouter
    assert shim_routers.AdminRouter is canon_routers.AdminRouter

    # 2. CLI identity
    import monika.interfaces.cli.main as shim_cli
    import monika.interfaces.cli.main as canon_cli

    assert shim_cli.main is canon_cli.main

    import monika.interfaces.cli.tui as shim_tui
    import monika.interfaces.cli.tui as canon_tui

    assert shim_tui.TradingAgentApp is canon_tui.TradingAgentApp

    # 3. Dashboard identity
    import monika.interfaces.dashboard.api as shim_dash
    import monika.interfaces.dashboard.api as canon_dash

    assert shim_dash.app is canon_dash.app

    import monika.interfaces.dashboard.rbac as shim_rbac
    import monika.interfaces.dashboard.rbac as canon_rbac

    assert shim_rbac.Role is canon_rbac.Role
    assert shim_rbac.resolve_role is canon_rbac.resolve_role

    # 4. Gateway identity
    import monika.interfaces.gateway.omnichannel_router as shim_omni
    import monika.interfaces.gateway.omnichannel_router as canon_omni

    assert shim_omni.OmnichannelRouter is canon_omni.OmnichannelRouter

    import monika.interfaces.gateway.api_server as shim_gw_api
    import monika.interfaces.gateway.api_server as canon_gw_api

    assert shim_gw_api.app is canon_gw_api.app
    assert shim_gw_api.chat_completions is canon_gw_api.chat_completions


def test_data_ingestion_layer_identity_and_parity():
    """Verify PR-5 data ingestion shims preserve exact object identity and runtime contracts."""
    # 1. Data Sources identity
    import monika.infrastructure.data_ingestion.sources.bond_yields_fetcher as shim_by
    import monika.infrastructure.data_ingestion.sources.bond_yields_fetcher as canon_by

    assert shim_by.BondYieldFetcher is canon_by.BondYieldFetcher

    import monika.infrastructure.data_ingestion.sources.cftc_cot as shim_cot
    import monika.infrastructure.data_ingestion.sources.cftc_cot as canon_cot

    assert shim_cot.CFTCCOTFetcher is canon_cot.CFTCCOTFetcher

    import monika.infrastructure.data_ingestion.sources.circuit_breaker as shim_cb
    import monika.infrastructure.data_ingestion.sources.circuit_breaker as canon_cb

    assert shim_cb.DataFeedCircuitBreaker is canon_cb.DataFeedCircuitBreaker

    # 2. Scrapers identity
    import monika.infrastructure.data_ingestion.scrapers.base_scraper as shim_bs
    import monika.infrastructure.data_ingestion.scrapers.base_scraper as canon_bs

    assert shim_bs.BaseScraper is canon_bs.BaseScraper

    import monika.infrastructure.data_ingestion.scrapers.macro.cme_fedwatch as shim_fw
    import monika.infrastructure.data_ingestion.scrapers.macro.cme_fedwatch as canon_fw

    assert shim_fw.FedWatchScraper is canon_fw.FedWatchScraper

    import monika.infrastructure.data_ingestion.scrapers.news.rss_base as shim_rss
    import monika.infrastructure.data_ingestion.scrapers.news.rss_base as canon_rss

    assert shim_rss.RssBaseScraper is canon_rss.RssBaseScraper

    # 3. Market Data Service identity
    import monika.application.services.market_data_service as shim_mds
    import monika.application.services.market_data_service as canon_mds

    assert shim_mds.MarketDataService is canon_mds.MarketDataService


def test_agent_and_graph_layer_identity_and_parity():
    """Verify PR-6a agent, graph, and checkpointer shims preserve exact object identity and runtime contracts."""
    # 1. Agent layer identity
    import monika.application.agent.agent_loop as shim_al
    import monika.application.agent.agent_loop as canon_al

    assert shim_al.SystemAgentLoop is canon_al.SystemAgentLoop

    import monika.application.agent.startup_checks as shim_sc
    import monika.application.agent.startup_checks as canon_sc

    assert shim_sc.StartupChecker is canon_sc.StartupChecker
    assert shim_sc.run_startup_checks is canon_sc.run_startup_checks

    import monika.application.agent.task_registry as shim_tr
    import monika.application.agent.task_registry as canon_tr

    assert shim_tr.TaskRegistry is canon_tr.TaskRegistry

    # 2. Graph layer identity
    import monika.application.graph.workflow as shim_gw
    import monika.application.graph.workflow as canon_gw

    assert shim_gw.build_trading_graph is canon_gw.build_trading_graph

    import monika.application.graph.state as shim_gs
    import monika.application.graph.state as canon_gs

    assert shim_gs.merge_dicts is canon_gs.merge_dicts
    assert shim_gs.merge_lists is canon_gs.merge_lists

    import monika.application.graph.nodes.data_node as shim_dn
    import monika.application.graph.nodes.data_node as canon_dn

    assert shim_dn.fetch_data_node is canon_dn.fetch_data_node

    import monika.application.graph.nodes.debate.subgraph as shim_ds
    import monika.application.graph.nodes.debate.subgraph as canon_ds

    assert shim_ds.build_debate_subgraph is canon_ds.build_debate_subgraph

    # 3. Checkpointers (infrastructure) identity
    import monika.infrastructure.graph.checkpointers.sqlite_checkpointer as shim_sqcp
    import monika.infrastructure.graph.checkpointers.sqlite_checkpointer as canon_sqcp

    assert shim_sqcp.SqliteCheckpointSaver is canon_sqcp.SqliteCheckpointSaver

    import monika.infrastructure.graph.checkpointers.dual_checkpointer as shim_dcp
    import monika.infrastructure.graph.checkpointers.dual_checkpointer as canon_dcp

    assert shim_dcp.DualCheckpointSaver is canon_dcp.DualCheckpointSaver


def test_analysis_core_framework_identity_and_parity():
    """Verify PR-6b analysis core framework shims preserve exact object identity and runtime contracts."""
    # 1. Harness & state
    import monika.application.analysis.harness.agent_harness as shim_ah
    import monika.application.analysis.harness.agent_harness as canon_ah

    assert shim_ah.AgentHarness is canon_ah.AgentHarness

    import monika.application.analysis.harness.harness_state as shim_hs
    import monika.application.analysis.harness.harness_state as canon_hs

    assert shim_hs.HarnessState is canon_hs.HarnessState

    import monika.application.analysis.harness.structured_output as shim_so
    import monika.application.analysis.harness.structured_output as canon_so

    assert shim_so.invoke_structured_or_freetext is canon_so.invoke_structured_or_freetext

    # 2. Stages & per_asset runner
    import monika.application.analysis.stages.per_asset.runner as shim_par
    import monika.application.analysis.stages.per_asset.runner as canon_par

    assert shim_par.PerAssetRunner is canon_par.PerAssetRunner

    import monika.application.analysis.stages.preflight_gate as shim_pfg
    import monika.application.analysis.stages.preflight_gate as canon_pfg

    assert shim_pfg.PreFlightTurnGate is canon_pfg.PreFlightTurnGate

    # 3. Grounding & validators
    import monika.application.analysis.validators.output_verifier as shim_ov
    import monika.application.analysis.validators.output_verifier as canon_ov

    assert shim_ov.OutputVerifier is canon_ov.OutputVerifier

    import monika.application.analysis.validators.in_harness_grounding as shim_ihg
    import monika.application.analysis.validators.in_harness_grounding as canon_ihg

    assert shim_ihg.InHarnessGroundingValidator is canon_ihg.InHarnessGroundingValidator

    import monika.application.analysis.validators.precommit_gate as shim_pcg
    import monika.application.analysis.validators.precommit_gate as canon_pcg

    assert shim_pcg.TradePreCommitGate is canon_pcg.TradePreCommitGate

    import monika.application.analysis.arbitration.signal_arbitrator as shim_sa
    import monika.application.analysis.arbitration.signal_arbitrator as canon_sa

    assert shim_sa.SignalArbitrator is canon_sa.SignalArbitrator

    # 4. Prefetch & subagent
    import monika.application.analysis.prefetch.news_digest as shim_nd
    import monika.application.analysis.prefetch.news_digest as canon_nd

    assert shim_nd.NewsDigestProcessor is canon_nd.NewsDigestProcessor

    import monika.application.analysis.subagent_spawner as shim_ss
    import monika.application.analysis.subagent_spawner as canon_ss

    assert shim_ss.DynamicSubagentPool is canon_ss.DynamicSubagentPool
    assert shim_ss.SubagentSpec is canon_ss.SubagentSpec

    import monika.application.analysis.subagent_blackboard as shim_sb
    import monika.application.analysis.subagent_blackboard as canon_sb

    assert shim_sb.SubagentBlackboard is canon_sb.SubagentBlackboard

    # 5. MCP framework
    import monika.application.analysis.mcp.protocol as shim_mcp_proto
    import monika.application.analysis.mcp.protocol as canon_mcp_proto

    assert shim_mcp_proto.JsonRpcRequest is canon_mcp_proto.JsonRpcRequest
    assert shim_mcp_proto.JsonRpcResponse is canon_mcp_proto.JsonRpcResponse

    import monika.application.analysis.mcp.client as shim_mcp_cli
    import monika.application.analysis.mcp.client as canon_mcp_cli

    assert shim_mcp_cli.McpClientManager is canon_mcp_cli.McpClientManager


def test_pr6d_identity_and_parity():
    """Verify PR-6d harness, skills, tools, and execution identity parity."""
    # 1. Harness
    import monika.application.harness.contract as shim_hc
    import monika.application.harness.contract as canon_hc

    assert shim_hc.TradingPlugin is canon_hc.TradingPlugin

    import monika.application.harness.engine as shim_he
    import monika.application.harness.engine as canon_he

    assert shim_he.PluginEngine is canon_he.PluginEngine

    # 2. Skills
    import monika.application.skills.skills_hub as shim_sh
    import monika.application.skills.skills_hub as canon_sh

    assert shim_sh.SkillsHub is canon_sh.SkillsHub

    import monika.application.skills.loader as shim_sl
    import monika.application.skills.loader as canon_sl

    assert shim_sl.load_skill is canon_sl.load_skill

    # 3. Tools
    import monika.application.analysis.tools.registry as shim_tr
    import monika.application.analysis.tools.registry as canon_tr

    assert shim_tr.ToolRegistry is canon_tr.ToolRegistry

    import monika.application.analysis.tools.executor as shim_te
    import monika.application.analysis.tools.executor as canon_te

    assert shim_te.ToolExecutor is canon_te.ToolExecutor

    # 4. Execution orchestration
    import monika.application.execution.execution_service as shim_es
    import monika.application.execution.execution_service as canon_es

    assert shim_es.ExecutionService is canon_es.ExecutionService

    import monika.application.execution.broker_registry as shim_br
    import monika.application.execution.broker_registry as canon_br

    assert shim_br.BrokerAdapterRegistry is canon_br.BrokerAdapterRegistry

    import monika.application.execution.effect_gate as shim_eg
    import monika.application.execution.effect_gate as canon_eg

    assert shim_eg.EffectGate is canon_eg.EffectGate

    import monika.application.execution.service.order_executor as shim_oe
    import monika.application.execution.service.order_executor as canon_oe

    assert shim_oe.OrderExecutorMixin is canon_oe.OrderExecutorMixin

    import monika.application.execution.service.risk_evaluator as shim_re
    import monika.application.execution.service.risk_evaluator as canon_re

    assert shim_re.RiskEvaluatorMixin is canon_re.RiskEvaluatorMixin


def test_pr7a_identity_and_parity():
    """Verify PR-7a scheduler and governance identity parity."""
    # 1. Scheduler
    import monika.application.scheduler.unified_cron_engine as shim_uce
    import monika.application.scheduler.unified_cron_engine as canon_uce

    assert shim_uce.UnifiedCronEngine is canon_uce.UnifiedCronEngine

    import monika.application.scheduler.cycle_scheduler as shim_cs
    import monika.application.scheduler.cycle_scheduler as canon_cs

    assert shim_cs.CycleScheduler is canon_cs.CycleScheduler

    import monika.application.scheduler.trailing_stop_manager as shim_tsm
    import monika.application.scheduler.trailing_stop_manager as canon_tsm

    assert shim_tsm.TrailingStopManager is canon_tsm.TrailingStopManager

    import monika.application.scheduler.cron_nlp_parser as shim_cnp
    import monika.application.scheduler.cron_nlp_parser as canon_cnp

    assert shim_cnp.parse_natural_schedule is canon_cnp.parse_natural_schedule

    # 2. Governance
    import monika.application.governance.run_manifest as shim_rm
    import monika.application.governance.run_manifest as canon_rm

    assert shim_rm.RunManifest is canon_rm.RunManifest
    assert shim_rm.RunManifestGenerator is canon_rm.RunManifestGenerator


def test_pr7b_identity_and_parity():
    """Verify PR-7b backtest and evals identity parity."""
    # 1. Backtest
    import monika.application.backtest.walk_forward_engine as shim_wfe
    import monika.application.backtest.walk_forward_engine as canon_wfe

    assert shim_wfe.WalkForwardEngine is canon_wfe.WalkForwardEngine
    assert shim_wfe.WalkForwardResult is canon_wfe.WalkForwardResult

    import monika.application.backtest.outcome_evaluator as shim_oe
    import monika.application.backtest.outcome_evaluator as canon_oe

    assert shim_oe.OutcomeEvaluator is canon_oe.OutcomeEvaluator
    assert shim_oe.ASSET_FRICTION_PROFILE is canon_oe.ASSET_FRICTION_PROFILE

    import monika.application.backtest.monte_carlo_engine as shim_mce
    import monika.application.backtest.monte_carlo_engine as canon_mce

    assert shim_mce.MonteCarloStressTester is canon_mce.MonteCarloStressTester

    import monika.application.backtest.alpha_validation as shim_av
    import monika.application.backtest.alpha_validation as canon_av

    assert shim_av.validate_alpha is canon_av.validate_alpha

    # 2. Evals
    import monika.application.evals.eval_runner as shim_er
    import monika.application.evals.eval_runner as canon_er

    assert shim_er.ABEvalRunner is canon_er.ABEvalRunner

    import monika.application.evals.hostile_market_probe as shim_hmp
    import monika.application.evals.hostile_market_probe as canon_hmp

    assert shim_hmp.HostileMarketProbe is canon_hmp.HostileMarketProbe

    import monika.application.evals.oracles.tool_safety_oracle as shim_tso
    import monika.application.evals.oracles.tool_safety_oracle as canon_tso

    assert shim_tso.ToolSafetyOracle is canon_tso.ToolSafetyOracle


def test_pr7c_identity_and_parity():
    """Verify PR-7c benchmark, plugins, and entrypoint identity parity."""
    # 1. Benchmark
    import monika.application.benchmark.runner as shim_brun
    import monika.application.benchmark.runner as canon_brun

    assert shim_brun.run_benchmark is canon_brun.run_benchmark

    import monika.application.benchmark.model_registry as shim_bmr
    import monika.application.benchmark.model_registry as canon_bmr

    assert shim_bmr.get_candidate_models is canon_bmr.get_candidate_models

    import monika.application.benchmark.task_specs as shim_bts
    import monika.application.benchmark.task_specs as canon_bts

    assert shim_bts.TASKS is canon_bts.TASKS

    # 2. Plugins & Plugin Kernel
    import monika.application.plugins.kernel as shim_pk
    import monika.application.plugins.kernel as canon_pk

    assert shim_pk.TradingPlugin is canon_pk.TradingPlugin
    assert shim_pk.PluginEngine is canon_pk.PluginEngine

    import monika.application.plugins.loader as shim_pl
    import monika.application.plugins.loader as canon_pl

    assert shim_pl.PluginLoader is canon_pl.PluginLoader
    assert shim_pl.topological_sort_plugins is canon_pl.topological_sort_plugins

    # 3. Entrypoints & Services
    import monika.application.bootstrap as shim_boot
    import monika.application.bootstrap as canon_boot

    assert shim_boot.race_dual_stack_socket is canon_boot.race_dual_stack_socket

    import monika.application.services.system_status_service as shim_sss
    import monika.application.services.system_status_service as canon_sss

    assert shim_sss.SystemStatusService is canon_sss.SystemStatusService


def test_pr7d_identity_and_parity():
    """Verify PR-7d utilities distribution identity parity."""
    # 1. Core Analytics
    import monika.core.analytics.cost_tracker as shim_ct
    import monika.core.analytics.cost_tracker as canon_ct

    assert shim_ct.CostTracker is canon_ct.CostTracker

    import monika.core.analytics.chart_generator as shim_cg
    import monika.core.analytics.chart_generator as canon_cg

    assert shim_cg.generate_candlestick_chart is canon_cg.generate_candlestick_chart

    # 2. Core Calibration
    import monika.core.calibration.confidence_calibrator as shim_cc
    import monika.core.calibration.confidence_calibrator as canon_cc

    assert shim_cc.fit_platt_scaling is canon_cc.fit_platt_scaling

    # 3. Core Streaming & Sanitizer (Coupling #10.3)
    import monika.core.streaming.stream_scrubber as shim_ss
    import monika.core.streaming.stream_scrubber as canon_ss

    assert shim_ss.StatefulStreamScrubber is canon_ss.StatefulStreamScrubber

    import monika.core.streaming.sanitizer as canon_san
    import monika.interfaces.telegram.sanitizer as canon_tgsan

    assert canon_tgsan.strip_emojis_and_emoticons is canon_san.strip_emojis_and_emoticons

    # 4. Core Validation
    import monika.core.validation.data_validator as shim_dv
    import monika.core.validation.data_validator as canon_dv

    assert shim_dv.validate_data_freshness is canon_dv.validate_data_freshness

    # 5. Core Security
    import monika.core.security.threat_detector as shim_td
    import monika.core.security.threat_detector as canon_td

    assert shim_td.ThreatDetector is canon_td.ThreatDetector

    # 6. Infrastructure API
    import monika.infrastructure.api.gemini_rate_limiter as shim_grl
    import monika.infrastructure.api.gemini_rate_limiter as canon_grl

    assert shim_grl.GeminiRateLimiter is canon_grl.GeminiRateLimiter

    # 7. Infrastructure Infra
    import monika.infrastructure.infra.container as shim_ic
    import monika.infrastructure.infra.container as canon_ic

    assert shim_ic.ServiceContainer is canon_ic.ServiceContainer

    # 8. Infrastructure LLM
    import monika.infrastructure.llm.caveman_compressor as shim_cmc
    import monika.infrastructure.llm.caveman_compressor as canon_cmc

    assert shim_cmc.compress_tool_payload is canon_cmc.compress_tool_payload

    # 9. Domain Market
    import monika.domain.market.session_info as shim_si
    import monika.domain.market.session_info as canon_si

    assert shim_si.get_current_market_session is canon_si.get_current_market_session

    # 10. Application Protocol
    import monika.application.protocol.context_coherence as shim_coco
    import monika.application.protocol.context_coherence as canon_coco

    assert shim_coco.compute_brief_price_divergence is canon_coco.compute_brief_price_divergence

    # 11. Application Plugins Manager
    import monika.application.plugins.manager.manager as shim_pm
    import monika.application.plugins.manager.manager as canon_pm

    assert shim_pm.PluginManager is canon_pm.PluginManager

    # 12. Application Scheduler
    import monika.application.scheduler.wall_clock as shim_wc
    import monika.application.scheduler.wall_clock as canon_wc

    assert shim_wc.parse_time_list is canon_wc.parse_time_list

    # 13. Interfaces Workspace
    import monika.interfaces.workspace.journal_helper as shim_jh
    import monika.interfaces.workspace.journal_helper as canon_jh

    assert shim_jh.format_dataview_journal is canon_jh.format_dataview_journal

    # 14. Infrastructure Storage
    import monika.infrastructure.storage.spill_store as shim_sps
    import monika.infrastructure.storage.spill_store as canon_sps

    assert shim_sps.SpillStore is canon_sps.SpillStore
