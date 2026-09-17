import pytest
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS


@pytest.fixture
def router():
    return ChatToolRouter(TELEGRAM_TOOLS)


def test_command_fast_regex_routing(router):
    """Verifies fast regex dispatch for explicit bot commands."""
    # /trade command
    trade_tools = router.route_tools_for_query("/trade EURUSD buy 0.1")
    trade_names = [t["name"] for t in trade_tools]
    assert "propose_action" in trade_names
    assert "get_account_info" in trade_names

    # /status command
    status_tools = router.route_tools_for_query("/status")
    status_names = [t["name"] for t in status_tools]
    assert "get_system_health" in status_names

    # /sentiment command
    sent_tools = router.route_tools_for_query("/sentiment")
    sent_names = [t["name"] for t in sent_tools]
    assert "get_fear_greed_index" in sent_names
    assert "get_funding_rate" in sent_names
    assert "get_retail_sentiment" in sent_names

    # /report command
    rep_tools = router.route_tools_for_query("/report")
    rep_names = [t["name"] for t in rep_tools]
    assert "get_paper_trading_performance" in rep_names
    assert "get_trade_history" in rep_names

    # /calibration command
    cal_tools = router.route_tools_for_query("/calibration")
    cal_names = [t["name"] for t in cal_tools]
    assert "get_calibration_status" in cal_names
    assert "get_market_correlations" in cal_names

    # /help command
    help_tools = router.route_tools_for_query("/help")
    assert help_tools == []


def test_semantic_vector_routing_specialized_tools(router):
    """
    Verifies that natural language queries activate specialized tools from the 50+ tool catalog
    via semantic vector similarity matching.
    """
    # 1. COT Report
    cot_tools = router.route_tools_for_query("Show me institutional speculative positions from the Commitments of Traders")
    cot_names = [t["name"] for t in cot_tools]
    assert "get_cot_report" in cot_names

    # 2. Crypto Funding Rate & Fear Greed
    crypto_tools = router.route_tools_for_query("What is the perpetual crypto funding rate and fear and greed index?")
    crypto_names = [t["name"] for t in crypto_tools]
    assert "get_funding_rate" in crypto_names or "get_fear_greed" in crypto_names

    # 3. FXSSI Sentiment
    fxssi_tools = router.route_tools_for_query("Check client retail positioning and order book ratio on FXSSI")
    fxssi_names = [t["name"] for t in fxssi_tools]
    assert "get_fxssi_sentiment" in fxssi_names

    # 4. Market Correlations
    corr_tools = router.route_tools_for_query("Check cross-asset correlation matrix between gold, dollar, and yields")
    corr_names = [t["name"] for t in corr_tools]
    assert "get_market_correlations" in corr_names

    # 5. Edge Tracker Status
    edge_tools = router.route_tools_for_query("How are our alpha edge strategies and walk forward win rates performing?")
    edge_names = [t["name"] for t in edge_tools]
    assert "get_edge_tracker_status" in edge_names

    # 6. Fibonacci Retracement Levels
    fibo_tools = router.route_tools_for_query("Calculate Fibonacci retracement and expansion levels for EURUSD")
    fibo_names = [t["name"] for t in fibo_tools]
    assert "get_fibonacci_levels" in fibo_names

    # 7. Volatility Regime
    vol_tools = router.route_tools_for_query("Is market volatility expanding or contracting? Show volatility regime")
    vol_names = [t["name"] for t in vol_tools]
    assert "get_volatility_regime" in vol_names
