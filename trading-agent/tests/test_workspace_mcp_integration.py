# ==============================================================================
# File: tests/test_workspace_mcp_integration.py
# Description: Integration Test for Workspace & Second-Brain MCP Wiring
# Verifies end-to-end integration across settings, MCP client, tool router, and executor.
# ==============================================================================

import asyncio
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_settings
from analysis.mcp.client import McpClientManager
from telegram_bot.chat_tool_router import ChatToolRouter
from analysis.tools.tools_definitions import TELEGRAM_TOOLS
from analysis.tools.unified_registry import unified_tool_registry
from analysis.tools.tool_executor import ToolExecutor
from utils.workspace.journal_helper import format_dataview_journal, format_spreadsheet_row, record_trade_to_workspace


@pytest.mark.asyncio
async def test_mcp_workspace_end_to_end():
    # 1. Verify Settings & MCP Client initialization
    cfg = load_settings()
    mgr = McpClientManager.get_instance(cfg)
    count = await mgr.initialize_servers()
    assert count >= 4, f"Expected at least 4 active MCP servers, got {count}"

    # 2. Verify Tool Registration in Unified Registry
    mcp_tools = [name for name in unified_tool_registry._tools if name.startswith("mcp_")]
    assert "mcp_filesystem_workspace_fs_read_file" in mcp_tools
    assert "mcp_filesystem_workspace_fs_write_file" in mcp_tools
    assert "mcp_excel_tabular_excel_read_sheet" in mcp_tools
    assert "mcp_excel_tabular_excel_append_row" in mcp_tools
    assert "mcp_google_workspace_gsheets_list_files" in mcp_tools
    assert "mcp_google_workspace_gsheets_read_sheet" in mcp_tools
    assert "mcp_google_workspace_gsheets_append_row" in mcp_tools

    # 3. Verify ChatToolRouter Intent Matching
    router = ChatToolRouter(TELEGRAM_TOOLS)
    mcp_tool_defs = [
        entry.get_anthropic_schema()
        for name, entry in unified_tool_registry._tools.items()
        if name.startswith("mcp_")
    ]
    router.update_tools(mcp_tool_defs)

    # Test Obsidian query routing
    q_obsidian = "Tolong baca catatan trading plan saya di Obsidian"
    r_obsidian = router.route_tools_for_query(q_obsidian)
    r_names_obs = [t["name"] for t in r_obsidian]
    assert "mcp_filesystem_workspace_fs_read_file" in r_names_obs

    # Test Excel query routing
    q_excel = "Update spreadsheet excel Trading_Journal.xlsx dengan posisi yang baru saja ditutup"
    r_excel = router.route_tools_for_query(q_excel)
    r_names_excel = [t["name"] for t in r_excel]
    assert "mcp_excel_tabular_excel_append_row" in r_names_excel
    assert any(t in r_names_excel for t in ("get_open_positions", "get_trade_history"))

    # Test Google Drive / Sheets query routing
    q_google = "Tolong cek file di Google Drive folder workspace Monika"
    r_google = router.route_tools_for_query(q_google)
    r_names_google = [t["name"] for t in r_google]
    assert "mcp_google_workspace_gsheets_list_files" in r_names_google

    # Test pure macro query isolation (no workspace tool pollution)
    q_macro = "Bagaimana proyeksi suku bunga FOMC dan yield spread USD malam ini?"
    r_macro = router.route_tools_for_query(q_macro)
    r_names_macro = [t["name"] for t in r_macro]
    assert "mcp_filesystem_workspace_fs_read_file" not in r_names_macro
    assert "mcp_google_workspace_gsheets_list_files" not in r_names_macro

    # 4. ToolExecutor End-to-End Real Execution
    executor = ToolExecutor(None, settings=cfg)
    test_note = os.path.abspath("data/test_journal_verify.md")
    test_sheet = os.path.abspath("data/test_sheet_verify.xlsx")
    vault_test_dir = os.path.abspath("data/test_vault")

    trade = {
        "ticket": 888777,
        "symbol": "XAUUSD",
        "action": "BUY",
        "volume": 0.10,
        "entry_price": 2680.50,
        "stop_loss": 2670.00,
        "take_profit": 2705.00,
        "risk_reward": "1:2.45",
        "confidence": 0.91,
        "thesis": "Gold structural breakout with yield inverted divergence.",
        "status": "FILLED",
    }

    try:
        # Write Obsidian note
        w_res = await executor.execute(
            "mcp_filesystem_workspace_fs_write_file",
            {"path": test_note, "content": format_dataview_journal(trade)},
        )
        assert "status" in str(w_res) or "content" in str(w_res)

        # Read note back
        r_res = await executor.execute(
            "mcp_filesystem_workspace_fs_read_file",
            {"path": test_note},
        )
        assert "type: trading-journal" in str(r_res)
        assert "XAUUSD" in str(r_res)

        # Append row to Excel
        row = format_spreadsheet_row(trade)
        app_res = await executor.execute(
            "mcp_excel_tabular_excel_append_row",
            {"file_path": test_sheet, "sheet_name": "October2026", "row_data": row},
        )
        assert "status" in str(app_res) or "content" in str(app_res)

        # Read sheet back
        s_res = await executor.execute(
            "mcp_excel_tabular_excel_read_sheet",
            {"file_path": test_sheet, "sheet_name": "October2026"},
        )
        assert "XAUUSD" in str(s_res)
        assert "2680.5" in str(s_res)

        # Real Google Drive live file listing via ToolExecutor
        g_res = await executor.execute(
            "mcp_google_workspace_gsheets_list_files",
            {"folder_id": "15PKGN6q0UUab-2dc8AcAXMTG8L5jMRnd"},
        )
        assert "files" in str(g_res) or "count" in str(g_res)

        # 5. Verify record_trade_to_workspace helper
        cfg_test = {
            "workspace": {
                "obsidian": {
                    "enabled": True,
                    "vault_path": vault_test_dir,
                    "journal_folder": "Trading/Journal",
                },
                "excel": {
                    "enabled": True,
                    "journal_path": os.path.join(vault_test_dir, "Trading", "journal.xlsx"),
                    "sheet_name": "TestJournal",
                },
            }
        }
        j_res = record_trade_to_workspace(cfg_test, trade)
        assert j_res["obsidian_saved"] is True
        assert os.path.exists(j_res["obsidian_path"])
        assert j_res["excel_saved"] is True
        assert os.path.exists(j_res["excel_path"])

    finally:
        import shutil
        if os.path.exists(test_note):
            os.remove(test_note)
        if os.path.exists(test_sheet):
            os.remove(test_sheet)
        if os.path.exists(vault_test_dir):
            shutil.rmtree(vault_test_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(test_mcp_workspace_end_to_end())
    print("ALL TESTS PASSED SUCCESSFULLY!")

