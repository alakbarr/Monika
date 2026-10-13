import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import ALL_TOOLS
import analysis.tools.handlers
from analysis.tools.registry import default_tool_registry

def test_execution_tools_registered():
    assert "compile_mql5_ea" in default_tool_registry._handler_classes or "compile_mql5_ea" in default_tool_registry._tools
    assert "get_mt5_broker_logs" in default_tool_registry._handler_classes or "get_mt5_broker_logs" in default_tool_registry._tools
    assert "get_mt5_terminal_info" in default_tool_registry._handler_classes or "get_mt5_terminal_info" in default_tool_registry._tools
    assert "get_inverted_fvg" in default_tool_registry._handler_classes or "get_inverted_fvg" in default_tool_registry._tools
    assert "backup_database" in default_tool_registry._handler_classes or "backup_database" in default_tool_registry._tools

def test_router_execution_queries():
    router = ChatToolRouter(ALL_TOOLS)
    queries = [
        "Tolong buatkan custom Expert Advisor (MQL5) sederhana berbasis strategi Moving Average Crossover dan compile filenya.",
        "Buka MetaTrader 5, pilih tab Journal, lalu copy dan kirimkan 10 pesan log broker terakhir ke saya.",
        "Cek apakah tombol Algo Trading di toolbar MetaTrader 5 sedang berwarna hijau (aktif) atau merah (mati)."
    ]
    for q in queries:
        tools = router.route_tools_for_query(q)
        names = [t["name"] for t in tools]
        assert any(k in names for k in ["compile_mql5_ea", "get_mt5_broker_logs", "get_mt5_terminal_info", "terminal", "computer_use"]), f"Routing failed for: {q}"

if __name__ == "__main__":
    test_execution_tools_registered()
    test_router_execution_queries()
    print("ALL FASE 2 TESTS PASSED!")
