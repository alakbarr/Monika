# ==============================================================================
# File: utils/workspace/journal_helper.py
# Description: Obsidian Dataview & Spreadsheet Trading Journal Helper
# Formats trading execution records into structured markdown and tabular rows.
# ==============================================================================

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def format_dataview_journal(trade_data: Dict[str, Any]) -> str:
    """
    Format trade execution data into an Obsidian Dataview-compatible markdown file
    with standardized YAML frontmatter.
    """
    now = datetime.now(timezone.utc)
    date_str = trade_data.get("date") or now.strftime("%Y-%m-%d")
    time_str = trade_data.get("time") or now.strftime("%H:%M:%S UTC")
    symbol = str(trade_data.get("symbol", "UNKNOWN")).upper()
    action = str(trade_data.get("action", "TRADE")).upper()
    ticket = trade_data.get("ticket", "N/A")
    lot = trade_data.get("volume", trade_data.get("lot_size", 0.0))
    entry = trade_data.get("entry_price", trade_data.get("price", 0.0))
    sl = trade_data.get("stop_loss", 0.0)
    tp = trade_data.get("take_profit", 0.0)
    rr = trade_data.get("risk_reward", "1:2.0")
    confidence = trade_data.get("confidence", 0.8)
    setup = trade_data.get("setup_type", "SMC / Structural Invalidation")
    thesis = trade_data.get("thesis", "Algorithmic multi-agent execution following macroeconomic confluence.")
    status = trade_data.get("status", "FILLED")

    content = f"""---
type: trading-journal
date: {date_str}
time: {time_str}
ticket: {ticket}
symbol: {symbol}
action: {action}
lot_size: {lot}
entry_price: {entry}
stop_loss: {sl}
take_profit: {tp}
risk_reward: "{rr}"
confidence_score: {confidence}
setup_type: "{setup}"
status: {status}
tags:
  - trading-journal
  - {symbol.lower()}
  - monika-agent
---

# Trade Record: {action} {symbol} (#{ticket})

## 1. Execution Overview
- **Timestamp**: `{date_str} {time_str}`
- **Symbol**: `{symbol}`
- **Direction**: `{action}`
- **Lot Size**: `{lot}`
- **Entry**: `{entry}`
- **Stop Loss**: `{sl}`
- **Take Profit**: `{tp}`
- **Risk/Reward**: `{rr}`
- **Confidence**: `{confidence:.2f}`

## 2. Analytical Thesis & Confluence
{thesis}

## 3. Post-Trade Review & Empirical Lessons
*(Updated during trade management or upon closure)*
"""
    return content


def format_spreadsheet_row(trade_data: Dict[str, Any]) -> Dict[str, Any]:
    """Format trade record into a dictionary row suitable for Excel or CSV appending."""
    now = datetime.now(timezone.utc)
    return {
        "Date": trade_data.get("date") or now.strftime("%Y-%m-%d"),
        "Time": trade_data.get("time") or now.strftime("%H:%M:%S"),
        "Ticket": trade_data.get("ticket", "N/A"),
        "Symbol": str(trade_data.get("symbol", "")).upper(),
        "Action": str(trade_data.get("action", "")).upper(),
        "Volume": trade_data.get("volume", trade_data.get("lot_size", 0.0)),
        "Entry": trade_data.get("entry_price", trade_data.get("price", 0.0)),
        "SL": trade_data.get("stop_loss", 0.0),
        "TP": trade_data.get("take_profit", 0.0),
        "RR": trade_data.get("risk_reward", "1:2.0"),
        "Setup": trade_data.get("setup_type", "SMC"),
        "Confidence": trade_data.get("confidence", 0.8),
        "Status": trade_data.get("status", "FILLED"),
    }


def record_trade_to_workspace(settings: Optional[Dict[str, Any]], trade_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely writes trade log to Obsidian vault and appends row to Excel spreadsheet
    if workspace paths are configured. Fail-safe: all exceptions are caught and logged.
    """
    res = {
        "obsidian_saved": False,
        "excel_saved": False,
        "obsidian_path": None,
        "excel_path": None,
        "error": None,
    }
    ws_config = settings.get("workspace", {}) if isinstance(settings, dict) else {}

    # 1. Obsidian Journaling
    obs_config = ws_config.get("obsidian", {})
    vault_path_raw = obs_config.get("vault_path") or os.environ.get("OBSIDIAN_VAULT_PATH")
    if vault_path_raw and obs_config.get("enabled", True):
        try:
            vault_path = Path(vault_path_raw).expanduser().resolve()
            journal_folder = obs_config.get("journal_folder", "Trading/Journal")
            target_dir = vault_path / journal_folder
            target_dir.mkdir(parents=True, exist_ok=True)

            now = datetime.now(timezone.utc)
            date_str = trade_data.get("date") or now.strftime("%Y-%m-%d")
            symbol = str(trade_data.get("symbol", "TRADE")).upper().replace("/", "")
            ticket = str(trade_data.get("ticket", "x")).replace("#", "")
            action = str(trade_data.get("action", "EXEC")).upper()

            filename = f"{date_str}-{symbol}-{action}-{ticket}.md"
            file_path = target_dir / filename

            content = format_dataview_journal(trade_data)
            file_path.write_text(content, encoding="utf-8")
            res["obsidian_saved"] = True
            res["obsidian_path"] = str(file_path)
        except Exception as e:
            res["error"] = f"Obsidian write failed: {e}"

    # 2. Excel Journaling
    excel_config = ws_config.get("excel", {})
    excel_path_raw = excel_config.get("journal_path") or os.environ.get("EXCEL_JOURNAL_PATH")
    if excel_path_raw and excel_config.get("enabled", True):
        try:
            excel_path = Path(excel_path_raw).expanduser().resolve()
            excel_path.parent.mkdir(parents=True, exist_ok=True)

            row_data = format_spreadsheet_row(trade_data)
            now = datetime.now(timezone.utc)
            sheet_name = excel_config.get("sheet_name") or now.strftime("%Y-%m")

            import pandas as pd
            if excel_path.suffix.lower() == ".csv":
                df = pd.DataFrame([row_data])
                header = not excel_path.exists()
                df.to_csv(excel_path, mode="a", index=False, header=header, encoding="utf-8")
            else:
                if not excel_path.exists():
                    df = pd.DataFrame([row_data])
                    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                else:
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(excel_path)
                        if sheet_name in wb.sheetnames:
                            ws = wb[sheet_name]
                        else:
                            ws = wb.create_sheet(sheet_name)
                            ws.append(list(row_data.keys()))
                        ws.append(list(row_data.values()))
                        wb.save(excel_path)
                    except Exception:
                        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                            df = pd.DataFrame([row_data])
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
            res["excel_saved"] = True
            res["excel_path"] = str(excel_path)
        except Exception as e:
            err_msg = f"Excel write failed: {e}"
            res["error"] = f"{res['error']}; {err_msg}" if res.get("error") else err_msg

    return res
