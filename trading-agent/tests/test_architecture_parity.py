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
