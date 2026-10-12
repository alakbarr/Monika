import os
import sys
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# Ensure path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telegram_bot.chat_tool_router import ChatToolRouter
from indicators.technical import detect_rsi_divergence
from indicators.smc_advanced import detect_smt_divergence
from analysis.tools.handlers.system_info import handle_get_server_telemetry, handle_capture_terminal_screenshot
from analysis.tools.handlers.position_mgmt import handle_calculate_position_size
from analysis.tools.handlers.market_data_tools import handle_get_synthetic_cross_rate
from analysis.tools.handlers.trade_intel import handle_simulate_price_shock, handle_read_system_logs
from analysis.tools.handlers.db_tools import handle_query_database_sql
from analysis.tools.tools_definitions import ALL_TOOLS, TELEGRAM_TOOLS

def test_tool_definitions():
    telegram_names = {t["name"] for t in TELEGRAM_TOOLS}
    all_names = {t["name"] for t in ALL_TOOLS}
    required = [
        "query_database_sql",
        "capture_terminal_screenshot",
        "get_server_telemetry",
        "get_broker_expenses_summary",
        "get_active_negative_constraints",
        "get_smt_divergence",
    ]
    for r in required:
        assert r in telegram_names, f"{r} missing from TELEGRAM_TOOLS"
        assert r in all_names, f"{r} missing from ALL_TOOLS"
    print("PASS: test_tool_definitions")

def test_router_intents():
    router = ChatToolRouter(TELEGRAM_TOOLS)
    
    # Q25: ditolak
    tools_q25 = router.route_tools_for_query("Kenapa order saya ditolak oleh sistem tadi pagi?")
    tool_names_q25 = [t["name"] for t in tools_q25]
    assert "get_rejected_trade_reasons" in tool_names_q25 or "read_system_logs" in tool_names_q25, f"Q25 failed: {tool_names_q25}"
    
    # Q30: komisi & swap
    tools_q30 = router.route_tools_for_query("Berapa total biaya komisi dan swap yang sudah saya bayar bulan ini?")
    tool_names_q30 = [t["name"] for t in tools_q30]
    assert "get_broker_expenses_summary" in tool_names_q30, f"Q30 failed: {tool_names_q30}"
    
    # Q53: SMT divergence
    tools_q53 = router.route_tools_for_query("Bandingkan struktur grafik DXY vs EURUSD dalam 48 jam terakhir, apakah ada SMT divergence?")
    tool_names_q53 = [t["name"] for t in tools_q53]
    assert "get_smt_divergence" in tool_names_q53, f"Q53 failed: {tool_names_q53}"

    # Q102: performa
    tools_q102 = router.route_tools_for_query("Tampilkan statistik performa sinyal AI berdasarkan tingkat keyakinan")
    tool_names_q102 = [t["name"] for t in tools_q102]
    assert "query_signal_performance" in tool_names_q102, f"Q102 failed: {tool_names_q102}"

    # Q123: database sql
    tools_q123 = router.route_tools_for_query("Tolong jalankan query database SQL untuk melihat data transaksi")
    tool_names_q123 = [t["name"] for t in tools_q123]
    assert "query_database_sql" in tool_names_q123, f"Q123 failed: {tool_names_q123}"

    # Q129: screenshot
    tools_q129 = router.route_tools_for_query("Ambil screenshot layar desktop / terminal MT5 saat ini")
    tool_names_q129 = [t["name"] for t in tools_q129]
    assert "capture_terminal_screenshot" in tool_names_q129, f"Q129 failed: {tool_names_q129}"

    # Q132: telemetry
    tools_q132 = router.route_tools_for_query("Cek penggunaan memori CPU dan disk space server")
    tool_names_q132 = [t["name"] for t in tools_q132]
    assert "get_server_telemetry" in tool_names_q132, f"Q132 failed: {tool_names_q132}"
    
    print("PASS: test_router_intents")

async def async_tests():
    # Telemetry
    res_telem = await handle_get_server_telemetry({})
    assert "cpu" in res_telem, f"Telemetry invalid: {res_telem}"
    assert "memory" in res_telem
    assert "disk" in res_telem
    assert res_telem["cpu"]["usage_pct"] >= 0

    # Screenshot
    res_shot = await handle_capture_terminal_screenshot({"label": "test_verification"})
    assert res_shot["status"] == "success", f"Screenshot failed: {res_shot}"
    assert os.path.exists(res_shot["file_path"]), f"Screenshot file missing: {res_shot['file_path']}"

    print("PASS: test_telemetry_and_screenshot")

    # Price shock & logs
    res_shock = await handle_simulate_price_shock({"pct_change": -5.0})
    assert "shock_applied" in res_shock, f"Price shock invalid: {res_shock}"
    assert "shocked_equity_usd" in res_shock

    res_logs = await handle_read_system_logs({"lines": 5})
    assert "count" in res_logs or "logs" in res_logs, f"Logs invalid: {res_logs}"
    print("PASS: test_price_shock_and_logs")

    # Query DB SQL safety
    res_drop = await handle_query_database_sql({"query": "DROP TABLE positions;"})
    assert res_drop.get("status") == "error", f"Drop test failed: {res_drop}"
    assert "Hanya query SELECT" in res_drop.get("error", "")

    res_sel = await handle_query_database_sql({"query": "SELECT * FROM positions LIMIT 5;"})
    assert res_sel.get("status") in ("success", "error")
    print("PASS: test_query_database_sql_safety")

    # Synthetic cross
    res_cross = await handle_get_synthetic_cross_rate({"pair": "GBPJPY"})
    assert "synthetic_rate" in res_cross or "status" in res_cross
    print("PASS: test_synthetic_cross")

    # Position sizing with custom equity
    res_pos = await handle_calculate_position_size({
        "symbol": "EURUSD",
        "entry_price": 1.0850,
        "stop_loss": 1.0830,
        "risk_pct": 1.0,
        "account_equity": 500.0
    })
    assert "lot_size" in res_pos or "lots" in res_pos or "error" not in res_pos
    print("PASS: test_position_sizing_equity")

def test_indicators():
    # RSI Divergence
    dates = pd.date_range("2026-01-01", periods=60, freq="1h")
    highs = pd.Series(np.linspace(100, 110, 60), index=dates)
    lows = pd.Series(highs - 1.0, index=dates)
    closes = pd.Series(highs - 0.5, index=dates)
    rsi = pd.Series(np.linspace(75, 60, 60), index=dates)
    
    res_div = detect_rsi_divergence(highs, lows, closes, rsi)
    assert "divergence" in res_div
    assert "details" in res_div

    # SMT Divergence
    dates_smt = pd.date_range("2026-01-01", periods=20, freq="1h")
    df_asset1 = pd.DataFrame({
        "high": [10.0 + i * 0.2 for i in range(20)],
        "low": [9.0 + i * 0.2 for i in range(20)],
        "close": [9.5 + i * 0.2 for i in range(20)],
    }, index=dates_smt)
    df_asset2 = pd.DataFrame({
        "high": [100.0 - i * 0.2 for i in range(20)],
        "low": [90.0 - i * 0.2 for i in range(20)],
        "close": [95.0 - i * 0.2 for i in range(20)],
    }, index=dates_smt)

    res_smt = detect_smt_divergence(df_asset1, df_asset2, "EURUSD", "GBPUSD", inverse_correlation=False)
    assert "smt_detected" in res_smt
    print("PASS: test_indicators")

if __name__ == "__main__":
    test_tool_definitions()
    test_router_intents()
    asyncio.run(async_tests())
    test_indicators()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
