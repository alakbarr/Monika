import pytest
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS


def test_chat_tool_router_intent_matching():
    router = ChatToolRouter(TELEGRAM_TOOLS)

    # 1. Diagnostic intent ("Kenapa bot gak buka posisi dari pagi?", "Kenapa tadi kena SL?")
    diag_bundle = router.route_tools_for_query("Kenapa bot gak buka posisi dari pagi?")
    tool_names = [t.get("name") for t in diag_bundle if isinstance(t, dict)]
    assert "get_system_health" in tool_names or "get_trade_details" in tool_names or "get_rejection_history" in tool_names

    # 2. Scripting & sandbox intent ("Buatkan script python korelasi rolling")
    script_bundle = router.route_tools_for_query("Buatkan script python untuk hitung korelasi rolling 14 hari")
    script_tool_names = [t.get("name") for t in script_bundle if isinstance(t, dict)]
    assert "execute_analysis_code" in script_tool_names

    # 3. Conditional Analysis Intent ("XAUUSD aman gak buat buy?")
    buy_bundle = router.route_tools_for_query("XAUUSD aman gak buat buy?")
    buy_tool_names = [t.get("name") for t in buy_bundle if isinstance(t, dict)]
    assert "get_smc_zones" in buy_tool_names or "get_order_blocks" in buy_tool_names or "get_dxy" in buy_tool_names

    # 4. Analytical query intent ("Tampilkan statistik winrate per session")
    audit_bundle = router.route_tools_for_query("Tampilkan statistik winrate, profit factor, dan holding time per session")
    audit_tool_names = [t.get("name") for t in audit_bundle if isinstance(t, dict)]
    assert "run_analytical_query" in audit_tool_names
