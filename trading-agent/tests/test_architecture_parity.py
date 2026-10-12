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
from services import (
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
    df = pd.DataFrame({
        "open": [1.1000 + i * 0.0005 for i in range(50)],
        "high": [1.1020 + i * 0.0005 for i in range(50)],
        "low": [1.0990 + i * 0.0005 for i in range(50)],
        "close": [1.1010 + i * 0.0005 for i in range(50)],
        "volume": [1000.0 + i * 10 for i in range(50)],
    }, index=dates)

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
    import risk.trade_proposal as shim_tp
    import monika.domain.risk.trade_proposal as canon_tp
    assert shim_tp.TradeProposal is canon_tp.TradeProposal

    import risk.risk_gate as shim_rg
    import monika.domain.risk.risk_gate as canon_rg
    assert shim_rg.RiskGate is canon_rg.RiskGate

    import risk.position_sizing as shim_ps
    import monika.domain.risk.position_sizing as canon_ps
    assert shim_ps.PositionSizer is canon_ps.PositionSizer

    # 2. Execution Domain Identity
    import execution.broker_plugin as shim_bp
    import monika.domain.execution.broker_plugin as canon_bp
    assert shim_bp.BrokerPlugin is canon_bp.BrokerPlugin

    import execution.verification_engine as shim_ve
    import monika.domain.execution.verification_engine as canon_ve
    assert shim_ve.EvidenceFirstVerifier is canon_ve.EvidenceFirstVerifier

    # 3. Indicators / Alpha Zoo Identity & Shared Registry State
    import indicators.alpha_zoo.registry as shim_reg
    import monika.domain.indicators.alpha_zoo.registry as canon_reg
    assert shim_reg.FactorRegistry is canon_reg.FactorRegistry

    # Ensure factors registered via canonical or shim are visible in both
    import indicators.alpha_zoo as shim_zoo
    import monika.domain.indicators.alpha_zoo as canon_zoo
    assert shim_zoo.FactorRegistry is canon_zoo.FactorRegistry
    assert len(shim_zoo.FactorRegistry.list_factors()) >= 10
    assert len(canon_zoo.FactorRegistry.list_factors()) >= 10


def test_infrastructure_layer_identity_and_parity():
    """Verify PR-2 infrastructure layer shims preserve exact object identity and runtime contracts."""
    # 1. Database models & engine identity
    import database.models as shim_models
    import monika.infrastructure.database.models as canon_models
    assert shim_models.Base is canon_models.Base
    assert shim_models.Trade is canon_models.Trade

    import database.domain_models as shim_dm
    import monika.infrastructure.database.domain_models as canon_dm
    assert shim_dm.Base is canon_dm.Base
    assert shim_dm.PriceOHLCV is canon_dm.PriceOHLCV

    # 2. Broker adapters identity
    import execution.broker_adapter as shim_ba
    import monika.infrastructure.brokers.broker_adapter as canon_ba
    assert shim_ba.SimulatedBrokerAdapter is canon_ba.SimulatedBrokerAdapter

    import risk.approval_transport as shim_at
    import monika.infrastructure.brokers.approval_transport as canon_at
    assert shim_at.ApprovalTransport is canon_at.ApprovalTransport
    assert shim_at.ApprovalRequestPayload is canon_at.ApprovalRequestPayload

    # 3. LLM Providers identity
    import analysis.providers.provider_registry as shim_pr
    import monika.infrastructure.providers.provider_registry as canon_pr
    assert shim_pr.ProviderRegistry is canon_pr.ProviderRegistry

    import analysis.providers.llm_factory as shim_lf
    import monika.infrastructure.providers.llm_factory as canon_lf
    assert shim_lf.LLMFactory is canon_lf.LLMFactory

    # 4. Credentials & Error taxonomy identity
    import provider.credential_pool as shim_cp
    import monika.infrastructure.credentials.credential_pool as canon_cp
    assert shim_cp.CredentialPool is canon_cp.CredentialPool

    import provider.error_taxonomy as shim_et
    import monika.infrastructure.credentials.error_taxonomy as canon_et
    assert shim_et.FailoverReason is canon_et.FailoverReason
    assert shim_et.ErrorClassifier is canon_et.ErrorClassifier

    # 5. TimesFM ML Engine identity
    import indicators.timesfm_engine as shim_tfm
    import monika.infrastructure.ml.timesfm_engine as canon_tfm
    assert shim_tfm.TimesFMEngine is canon_tfm.TimesFMEngine


def test_core_foundation_identity_and_parity():
    """Verify class identity and behavioral parity between legacy and canonical core foundation."""
    # 1. Config identity
    import config.settings as shim_cfg
    import monika.core.config.settings as canon_cfg
    assert shim_cfg.load_settings is canon_cfg.load_settings

    import config.schemas as shim_sch
    import monika.core.config.schemas as canon_sch
    assert shim_sch.TradingAgentConfig is canon_sch.TradingAgentConfig

    # 2. Security identity
    import security.terminal_guard as shim_tg
    import monika.core.security.terminal_guard as canon_tg
    assert shim_tg.validate_command is canon_tg.validate_command
    assert shim_tg.assert_safe_read_path is canon_tg.assert_safe_read_path

    import security.credential_vault as shim_cv
    import monika.core.security.credential_vault as canon_cv
    assert shim_cv.CredentialVault is canon_cv.CredentialVault

    # 3. Telemetry identity
    import logging_observability.activity_logger as shim_al
    import monika.core.telemetry.activity_logger as canon_al
    assert shim_al.ActivityLogger is canon_al.ActivityLogger

    import logging_observability.tracing.tracer as shim_tr
    import monika.core.telemetry.tracing.tracer as canon_tr
    assert shim_tr.AgentTracer is canon_tr.AgentTracer
    assert shim_tr.Span is canon_tr.Span
    assert shim_tr.get_tracer is canon_tr.get_tracer

    # 4. Primitives identity
    import utils.clock as shim_clk
    import monika.core.primitives.clock as canon_clk
    assert shim_clk.now is canon_clk.now
    assert shim_clk.set_simulated_now is canon_clk.set_simulated_now

    import utils.protocol.event_bus as shim_eb
    import monika.core.primitives.event_bus as canon_eb
    assert shim_eb.EventBus is canon_eb.EventBus

    import utils.typesafe.jev_primitives as shim_jev
    import monika.core.primitives.jev_primitives as canon_jev
    assert shim_jev.Choice is canon_jev.Choice
    assert shim_jev.Score is canon_jev.Score



