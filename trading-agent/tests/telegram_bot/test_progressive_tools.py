import pytest
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS


def test_chat_tool_router_progressive_loading():
    """Memastikan ChatToolRouter memuat tool secara progresif tanpa membakar token."""
    router = ChatToolRouter(TELEGRAM_TOOLS)
    total_tools_count = len(TELEGRAM_TOOLS)
    assert total_tools_count >= 30, f"Total tools seharusnya >= 30, terdeteksi: {total_tools_count}"
    
    # 1. Kueri portofolio tunggal -> hanya tool portofolio (< 10 tools)
    tools_balance = router.route_tools_for_query("Berapa balance dan equity akun saya sekarang?")
    assert 1 <= len(tools_balance) <= 10
    tool_names_balance = [t["name"] for t in tools_balance]
    assert "get_account_info" in tool_names_balance
    assert "get_open_positions" in tool_names_balance
    
    # 2. Kueri trading -> memuat propose_action & account tools
    tools_trade = router.route_tools_for_query("Beli 0.1 lot EURUSD pasang SL di 1.0850")
    tool_names_trade = [t["name"] for t in tools_trade]
    assert "propose_action" in tool_names_trade
    assert len(tools_trade) < total_tools_count
    
    # 3. Kueri sapaan murni -> Zero-Tool mode (hemat 100% token)
    tools_greet = router.route_tools_for_query("Halo selamat pagi")
    assert len(tools_greet) == 0
    
    # 4. Kueri ambigu / tidak terklasifikasi -> Core Primitives (6 tools), BUKAN 36 tools!
    tools_ambiguous = router.route_tools_for_query("Menurutmu bagaimana kondisi sekarang?")
    assert len(tools_ambiguous) == 6
    tool_names_ambiguous = [t["name"] for t in tools_ambiguous]
    assert "get_account_info" in tool_names_ambiguous
    assert "propose_action" in tool_names_ambiguous
    assert "get_market_session" in tool_names_ambiguous
    
    # 5. Kueri kompleks multi-domain (>= 3 domain) -> Fallback ke full tools
    complex_query = (
        "Cek balance portofolio saya, bagaimana teknikal chart EURUSD dan RSI-nya, "
        "serta bagaimana berita makro CPI dan sentimen VIX hari ini?"
    )
    tools_complex = router.route_tools_for_query(complex_query)
    assert len(tools_complex) == total_tools_count
