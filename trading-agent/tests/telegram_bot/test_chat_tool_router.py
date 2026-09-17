import pytest
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS


@pytest.fixture
def router():
    return ChatToolRouter(TELEGRAM_TOOLS)


def test_greeting_zero_tools(router):
    tools = router.route_tools_for_query("Halo selamat pagi!")
    assert tools == []


def test_trade_intent_includes_propose_action(router):
    tools = router.route_tools_for_query("Buy 0.1 lot EURUSD dengan SL 1.0800")
    tool_names = [t["name"] for t in tools]
    assert "propose_action" in tool_names
    assert "get_account_info" in tool_names
    assert len(tools) <= 12


def test_portfolio_intent(router):
    tools = router.route_tools_for_query("Berapa saldo balance dan open posisi sekarang?")
    tool_names = [t["name"] for t in tools]
    assert "get_account_info" in tool_names
    assert "get_open_positions" in tool_names
    assert len(tools) <= 10


def test_technical_intent(router):
    tools = router.route_tools_for_query("Tolong analisis chart XAUUSD dan level SMC FVG")
    tool_names = [t["name"] for t in tools]
    assert "get_chart" in tool_names
    assert "get_smc_zones" in tool_names
    assert len(tools) <= 18


def test_system_intent(router):
    tools = router.route_tools_for_query("Cek status server dan biaya token usage")
    tool_names = [t["name"] for t in tools]
    assert "get_system_health" in tool_names
    assert "get_token_usage_and_costs" in tool_names


def test_multi_domain_fallback(router):
    # Query covering portfolio, macro, technical, system
    tools = router.route_tools_for_query(
        "Berapa saldo PnL saya, bagaimana berita FOMC dan kalender ekonomi, tolong cek chart EURUSD rsi, dan berapa biaya token server?"
    )
    assert len(tools) == len(TELEGRAM_TOOLS)


def test_macro_intent_routes_fedwatch_and_yields(router):
    """Verify macro queries route FedWatch, Treasury yields, and Interest rates."""
    tools = router.route_tools_for_query("Bagaimana probabilitas FedWatch untuk FOMC mendatang dan yield Treasury 10Y?")
    tool_names = [t["name"] for t in tools]
    assert "get_fedwatch_probabilities" in tool_names
    assert "get_treasury_yields" in tool_names
    assert "get_interest_rates" in tool_names
    assert "get_eia_oil_inventory" in tool_names


def test_macro_command_includes_target_tools(router):
    """Verify /macro command returns complete 4 macro tools."""
    tools = router.route_tools_for_query("/macro")
    tool_names = [t["name"] for t in tools]
    assert "get_fedwatch_probabilities" in tool_names
    assert "get_treasury_yields" in tool_names
    assert "get_interest_rates" in tool_names
    assert "get_eia_oil_inventory" in tool_names


def test_research_intent_includes_macro_tools(router):
    """Verify research intent includes the 4 macro tools."""
    tools = router.route_tools_for_query("Riset mendalam probabilitas event makro dan konsensus FOMC")
    tool_names = [t["name"] for t in tools]
    assert "get_fedwatch_probabilities" in tool_names
    assert "get_treasury_yields" in tool_names
    assert "get_interest_rates" in tool_names
    assert "get_eia_oil_inventory" in tool_names
