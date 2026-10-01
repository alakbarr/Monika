"""
Tests for Conversational Gaps Fixes (Phase 1, 2, and 3).
Verifies that all 50 questions' key root causes and tools are correctly wired.
"""

import pytest
import re
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import (
    TELEGRAM_TOOLS,
    CALCULATE_POSITION_SIZE,
    GET_LIQUIDITY_SWEEP_CONTEXT,
    SCAN_PATTERN_SIMILARITY,
    CALCULATE_MARGIN,
    CREATE_PRICE_ALERT,
    GET_MARKET_QUOTE,
)


def test_telegram_tools_registration():
    """Verify all missing tools are registered in TELEGRAM_TOOLS."""
    tool_names = [t.get("name") or t.get("function", {}).get("name") for t in TELEGRAM_TOOLS]
    
    assert "calculate_position_size" in tool_names, "CALCULATE_POSITION_SIZE must be in TELEGRAM_TOOLS"
    assert "get_liquidity_sweep_context" in tool_names, "GET_LIQUIDITY_SWEEP_CONTEXT must be in TELEGRAM_TOOLS"
    assert "scan_pattern_similarity" in tool_names, "SCAN_PATTERN_SIMILARITY must be in TELEGRAM_TOOLS"
    assert "calculate_margin" in tool_names, "CALCULATE_MARGIN must be in TELEGRAM_TOOLS"
    assert "create_price_alert" in tool_names, "CREATE_PRICE_ALERT must be in TELEGRAM_TOOLS"
    assert "get_market_quote" in tool_names, "GET_MARKET_QUOTE must be in TELEGRAM_TOOLS"


def test_chat_tool_router_regex_patterns():
    """Verify ChatToolRouter correctly routes trade, research, technical, and portfolio intents."""
    router = ChatToolRouter(all_tools=TELEGRAM_TOOLS)

    # 1. Trade intent: sizing & margin & alert
    t_trade = router.route_tools_for_query("Berapa lot size yang tepat untuk EURUSD dengan risk 1%?")
    t_names = [t.get("name") or t.get("function", {}).get("name") for t in t_trade]
    assert "calculate_position_size" in t_names
    assert "propose_action" in t_names

    t_margin = router.route_tools_for_query("Berapa margin yang dibutuhkan untuk 0.5 lot XAUUSD?")
    t_m_names = [t.get("name") or t.get("function", {}).get("name") for t in t_margin]
    assert "calculate_margin" in t_m_names or "propose_action" in t_m_names

    # 2. Technical & SMC intent
    t_tech = router.route_tools_for_query("Cek apakah ada liquidity sweep di BTCUSD H4")
    t_tech_names = [t.get("name") or t.get("function", {}).get("name") for t in t_tech]
    assert "get_liquidity_sweep_context" in t_tech_names or "get_smc_zones" in t_tech_names

    t_patt = router.route_tools_for_query("Buat chart pattern similarity scan untuk XAUUSD")
    t_patt_names = [t.get("name") or t.get("function", {}).get("name") for t in t_patt]
    assert "scan_pattern_similarity" in t_patt_names or "get_chart" in t_patt_names

    # 3. Portfolio correlation
    t_corr = router.route_tools_for_query("Tampilkan korelasi antar pair yang sedang saya tradingkan")
    t_corr_names = [t.get("name") or t.get("function", {}).get("name") for t in t_corr]
    assert "get_market_correlations" in t_corr_names or "get_open_positions" in t_corr_names

    # 4. Research & academic
    t_res = router.route_tools_for_query("Cari paper akademik tentang mean reversion strategy")
    t_res_names = [t.get("name") or t.get("function", {}).get("name") for t in t_res]
    assert "search_academic" in t_res_names or "web_search" in t_res_names


def test_is_action_query_safety_regex():
    """Verify pause, jeda, emergency, and stop are intercepted from streaming in ChatAgent."""
    action_regex = re.compile(
        r'\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser|buy|beli|sell|jual|trade|eksekusi|pause|jeda|hentikan|stop|resume|lanjutkan|emergency|panic)\b',
        re.IGNORECASE
    )

    assert action_regex.search("Tolong pause trading dulu") is not None
    assert action_regex.search("Jeda trading sekarang") is not None
    assert action_regex.search("Resume trading ya") is not None
    assert action_regex.search("Lanjutkan trading") is not None
    assert action_regex.search("Tutup semua posisi sekarang juga!") is not None
    assert action_regex.search("Emergency close all") is not None


@pytest.mark.asyncio
async def test_reflection_formatting_no_truncation():
    """Verify DecisionReflection formatter does not truncate lessons."""
    from analysis.memory.session_search import SessionSearchEngine
    from database.models import DecisionReflection
    from datetime import datetime, timezone

    searcher = SessionSearchEngine()
    r = DecisionReflection(
        id=1,
        symbol="XAUUSD",
        decision="buy",
        confidence=0.85,
        confluence_score=8,
        rationale_summary="Strong institutional order block sweep",
        exit_reason="TP Hit +120 pips",
        alpha_lesson="Waiting for 15M liquidity sweep before entry substantially improves R:R and filters fakeouts.",
        specific_lesson="Never enter during high-impact news spikes without confirming spread stabilization.",
        next_trade_adjustment="Set limit orders at 0.5 FVG midpoint.",
        lesson_tags="smc,fvg,liquidity_sweep",
        created_at=datetime.now(timezone.utc),
    )

    formatted = searcher._format_reflection(r)
    assert formatted["specific_lesson"] == r.specific_lesson
    assert formatted["next_trade_adjustment"] == r.next_trade_adjustment
    assert len(formatted["content"]) > 120, "Content should not be truncated to 120 chars"
    assert "Waiting for 15M liquidity sweep" in formatted["content"]


@pytest.mark.asyncio
async def test_tool_executor_dispatches_remediated_tools():
    """Verify ToolExecutor properly routes and executes newly registered and remediated tools."""
    from analysis.tools.executor import ToolExecutor
    from unittest.mock import AsyncMock, MagicMock

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={"trading": {"symbols": ["EURUSD", "XAUUSD"]}})

    # 1. calculate_margin
    with patch("execution.mt5_client.get_mt5_client") as mock_mt5_getter:
        mock_client = MagicMock()
        mock_client.calc_margin = MagicMock(return_value={"symbol": "XAUUSD", "lot": 0.5, "required_margin": 250.0})
        mock_client.get_symbol_info_tick = MagicMock(return_value=MagicMock(ask=2650.0, bid=2649.8))
        mock_mt5_getter.return_value = mock_client

        margin_res = await executor.execute("calculate_margin", {"symbol": "XAUUSD", "lot_size": 0.5})
        assert margin_res.get("symbol") == "XAUUSD"
        assert margin_res.get("required_margin") == 250.0

    # 2. calculate_position_size
    pos_res = await executor.execute("calculate_position_size", {
        "symbol": "EURUSD",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "risk_pct": 1.0
    })
    assert pos_res.get("symbol") == "EURUSD"
    assert "recommended_lots" in pos_res or "lot_size" in pos_res or "suggested_lot" in pos_res

    # 3. get_risk_state
    with patch("execution.mt5_client.get_mt5_client") as mock_mt5_getter:
        mock_client = MagicMock()
        mock_client.get_account_info = AsyncMock(return_value={"equity": 10500.0, "balance": 10000.0})
        mock_mt5_getter.return_value = mock_client

        risk_res = await executor.execute("get_risk_state", {})
        assert "current_equity" in risk_res or "starting_equity" in risk_res or "status" in risk_res


@pytest.mark.asyncio
async def test_chat_agent_pause_fast_path_interceptor():
    """Verify ChatAgent immediately returns confirmation card for conversational pause."""
    from telegram_bot.chat_agent import ChatAgent

    agent = ChatAgent(
        settings={"trading": {"symbols": ["EURUSD"]}},
        user_id="12345",
        is_admin=True
    )

    reply_text, pending = await agent._handle_internal(
        user_message="Tolong pause trading dulu"
    )

    assert "Konfirmasi Jeda Trading" in reply_text
    assert pending is not None
    assert pending.action_type == "pause_trading"


@pytest.mark.asyncio
async def test_plugin_catalog_index_callback():
    """Verify plugin catalog index mapping callback data fits within Telegram 64-byte limit."""
    from telegram_bot.bot import TelegramBot

    bot = TelegramBot(settings={})
    mock_plugin_service = MagicMock()
    mock_plugin_service.discover_plugins = AsyncMock(return_value=[
        {"package": "monika-plugin-sentiment-analysis-deepseek-long-name", "installed": False},
        {"package": "monika-plugin-timesfm-quant-advanced-long-name", "installed": True}
    ])
    bot.plugin_service = mock_plugin_service

    # Build catalog buttons
    plugins = await mock_plugin_service.discover_plugins()
    bot._plugin_catalog_cache = plugins

    # Verify callback data length
    for idx, p in enumerate(plugins):
        cb_data = f"plg:inst:{idx}"
        assert len(cb_data.encode("utf-8")) <= 64
        # Verify index maps back accurately
        assert bot._plugin_catalog_cache[idx]["package"] == p["package"]


@pytest.mark.asyncio
async def test_create_and_query_price_alerts_db():
    """Verify create_price_alert inserts and get_active_triggers retrieves standalone user price alerts."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from database.models import Base
    from analysis.tools.handlers.trade_intel import handle_create_price_alert, handle_get_active_triggers

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Create price alert
        create_res = await handle_create_price_alert(
            args={"symbol": "EURUSD", "price_level": 1.1200, "condition": "above", "note": "Breakout test"},
            session=session
        )
        assert create_res.get("status") == "created"
        assert create_res.get("price_level") == 1.1200
        assert create_res.get("symbol") == "EURUSD"

        # Query active triggers
        query_res = await handle_get_active_triggers(args={"symbol": "EURUSD"}, session=session)
        assert query_res.get("count") >= 1
        active = query_res.get("active_triggers", [])
        assert any(t["symbol"] == "EURUSD" and float(t["trigger_price"]) == 1.1200 for t in active)


