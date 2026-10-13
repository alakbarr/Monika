# ==============================================================================
# File: analysis/tools/handlers/trade_intel/reporting.py
# ==============================================================================

"""
Trade export (Excel/Docx/Pptx/Tearsheet) and journal/log handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.base_handler import ToolHandler
from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry, register_tool
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    DecisionReflection,
    PaperTradeRecord,
    TelegramConversation,
    TradeTrigger,
)
from monika.application.analysis.tools.handlers.trade_intel.base import _get_session_and_settings, logger


async def handle_export_trades_to_excel(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Exports trading history (live positions and paper trades) to an Excel (.xlsx) file."""
    import os
    from datetime import datetime, timezone

    import pandas as pd

    from monika.infrastructure.database.models import PaperTradeRecord, Position

    out_dir = args.get("output_dir") or "data/exports"
    os.makedirs(out_dir, exist_ok=True)
    limit = int(args.get("limit", 500))

    trade_rows = []
    if session:
        # 1. Closed Live Positions
        pos_query = select(Position).where(Position.status == "closed").order_by(Position.closed_at.desc()).limit(limit)
        positions = (await session.execute(pos_query)).scalars().all()
        for p in positions:
            trade_rows.append(
                {
                    "Source": "Live MT5",
                    "Ticket": p.mt5_ticket or p.id,
                    "Symbol": p.symbol,
                    "Direction": p.direction,
                    "Volume": p.volume,
                    "Open Time": p.opened_at.isoformat() if p.opened_at else "",
                    "Close Time": p.closed_at.isoformat() if p.closed_at else "",
                    "Entry Price": p.entry_price,
                    "Exit Price": p.exit_price,
                    "Stop Loss": p.stop_loss,
                    "Take Profit": p.take_profit,
                    "PnL ($)": p.pnl,
                    "PnL (%)": p.pnl_pct,
                    "Holding (Hrs)": round((p.closed_at - p.opened_at).total_seconds() / 3600, 2)
                    if p.closed_at and p.opened_at
                    else 0.0,
                    "Exit Reason": p.exit_reason or "closed",
                }
            )

        # 2. Paper Trades
        paper_query = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == "closed")
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(limit)
        )
        papers = (await session.execute(paper_query)).scalars().all()
        for pt in papers:
            trade_rows.append(
                {
                    "Source": "Paper Trading",
                    "Ticket": f"paper_{pt.id}",
                    "Symbol": pt.symbol,
                    "Direction": pt.direction,
                    "Volume": pt.lot_size or 0.01,
                    "Open Time": pt.opened_at.isoformat() if pt.opened_at else "",
                    "Close Time": pt.closed_at.isoformat() if pt.closed_at else "",
                    "Entry Price": pt.entry_price,
                    "Exit Price": pt.exit_price,
                    "Stop Loss": pt.stop_loss,
                    "Take Profit": pt.take_profit,
                    "PnL ($)": pt.pnl_usd or 0.0,
                    "PnL (%)": pt.pnl_pct or 0.0,
                    "Holding (Hrs)": round(pt.holding_hours or 0.0, 2),
                    "Exit Reason": pt.exit_reason or "closed",
                }
            )

    if not trade_rows:
        return {"status": "empty", "message": "No closed trade records found to export."}

    df = pd.DataFrame(trade_rows)
    filename = (
        args.get("filename") or f"monika_trades_journal_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    filepath = os.path.join(out_dir, filename)

    try:
        # Calculate Executive KPIs
        total_trades = len(df)
        wins = df[df["PnL ($)"] > 0]
        losses = df[df["PnL ($)"] < 0]
        win_rate = round((len(wins) / total_trades) * 100.0, 1) if total_trades > 0 else 0.0
        tot_pnl = round(df["PnL ($)"].sum(), 2)
        gross_profit = wins["PnL ($)"].sum()
        gross_loss = abs(losses["PnL ($)"].sum())
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0
        avg_win = round(wins["PnL ($)"].mean(), 2) if len(wins) > 0 else 0.0
        avg_loss = round(losses["PnL ($)"].mean(), 2) if len(losses) > 0 else 0.0
        top_symbol = df["Symbol"].value_counts().index[0] if "Symbol" in df.columns and not df.empty else "N/A"

        kpi_df = pd.DataFrame(
            [
                {"Metric": "Total Trades Executed", "Value": total_trades},
                {"Metric": "Win Rate (%)", "Value": f"{win_rate}%"},
                {"Metric": "Total Realized PnL ($)", "Value": f"${tot_pnl:,.2f}"},
                {"Metric": "Profit Factor", "Value": profit_factor},
                {"Metric": "Average Win ($)", "Value": f"${avg_win:,.2f}"},
                {"Metric": "Average Loss ($)", "Value": f"${avg_loss:,.2f}"},
                {"Metric": "Most Active Symbol", "Value": top_symbol},
                {"Metric": "Export Timestamp (UTC)", "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")},
            ]
        )

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            kpi_df.to_excel(writer, sheet_name="Executive_KPIs", index=False)
            df.to_excel(writer, sheet_name="Trade_Journal", index=False)

        abs_path = os.path.abspath(filepath)
        if executor and hasattr(executor, "add_pending_file"):
            executor.add_pending_file(
                file_path=abs_path,
                filename=filename,
                caption=f"Jurnal Trading & Executive KPIs ({total_trades} transaksi)",
            )
        return {
            "status": "success",
            "total_records": len(trade_rows),
            "filepath": abs_path,
            "filename": filename,
            "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed writing Excel file: {e}"}


@register_tool(
    "export_trades_to_excel",
    aliases=["export_excel", "generate_excel_journal"],
    category="REPORTING",
    parallel_safe=True,
)
class ExportTradesToExcelHandler(ToolHandler):
    name = "export_trades_to_excel"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_export_trades_to_excel(args, session=session, executor=executor, **kwargs)


async def handle_generate_docx_report(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional Microsoft Word (.docx) portfolio performance report."""
    from monika.core.telemetry.reporting.docx_report_generator import DocxReportGenerator
    from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator
    from monika.infrastructure.database.models import PaperTradeRecord, Position

    trades = []
    if session:
        papers = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        for pt in papers:
            trades.append(
                {
                    "symbol": pt.symbol,
                    "pnl_pct": pt.pnl_pct or 0.0,
                    "pnl_usd": pt.pnl_usd or 0.0,
                    "opened_at": pt.opened_at,
                    "closed_at": pt.closed_at,
                    "exit_reason": pt.exit_reason or "tp_hit",
                }
            )

    metrics_res = QuantTearsheetGenerator.generate_from_trades(
        trades=trades, initial_equity=float(args.get("initial_equity", 10000.0))
    )
    metrics_dict = metrics_res.to_dict()

    narrative = (
        args.get("narrative")
        or "During the recent trading cycle, Monika systematically executed Smart Money Concepts (SMC) order-block and liquidity sweep setups while enforcing strict 10-layer RiskGate compliance."
    )
    recommendations = args.get("recommendations") or [
        "Maintain current conservative Kelly sizing across high-volatility sessions.",
        "Ensure news event proximity filters continue to isolate high-impact FOMC/NFP releases.",
    ]

    docx_gen = DocxReportGenerator(output_dir=args.get("output_dir", "data/reports"))
    filepath = docx_gen.generate_report(
        metrics=metrics_dict,
        narrative_synthesis=narrative,
        recommendations=recommendations,
        title=args.get("title", "Monika Quantitative Portfolio Performance Report"),
        filename=args.get("filename"),
    )
    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file") and filepath and os.path.exists(filepath):
        executor.add_pending_file(
            file_path=os.path.abspath(filepath),
            filename=os.path.basename(filepath),
            caption=args.get("title", "Portfolio Performance Report (.docx)"),
        )
    return {
        "status": "success",
        "filepath": filepath,
        "metrics": metrics_dict,
        "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False,
    }


@register_tool(
    "generate_docx_report", aliases=["generate_word_report", "export_docx"], category="REPORTING", parallel_safe=True
)
class GenerateDocxReportHandler(ToolHandler):
    name = "generate_docx_report"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_generate_docx_report(args, session=session, executor=executor, **kwargs)


async def handle_generate_pptx_deck(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional Microsoft PowerPoint (.pptx) pitch and performance deck."""
    from monika.core.telemetry.reporting.pptx_deck_generator import PptxDeckGenerator
    from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator
    from monika.infrastructure.database.models import PaperTradeRecord

    trades = []
    if session:
        papers = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        for pt in papers:
            trades.append(
                {
                    "symbol": pt.symbol,
                    "pnl_pct": pt.pnl_pct or 0.0,
                    "pnl_usd": pt.pnl_usd or 0.0,
                    "opened_at": pt.opened_at,
                    "closed_at": pt.closed_at,
                }
            )

    metrics_res = QuantTearsheetGenerator.generate_from_trades(
        trades=trades, initial_equity=float(args.get("initial_equity", 10000.0))
    )

    deck_gen = PptxDeckGenerator(output_dir=args.get("output_dir", "data/reports"))
    filepath = deck_gen.generate_pitch_deck(
        metrics=metrics_res.to_dict(),
        title=args.get("title", "Monika Autonomous Trading Agent"),
        subtitle=args.get("subtitle", "Quantitative Multi-Agent Architecture & Performance Deck"),
        filename=args.get("filename"),
    )
    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file") and filepath and os.path.exists(filepath):
        executor.add_pending_file(
            file_path=os.path.abspath(filepath),
            filename=os.path.basename(filepath),
            caption=args.get("title", "Executive Pitch Deck (.pptx)"),
        )
    return {
        "status": "success",
        "filepath": filepath,
        "delivered_as_document": True if (executor and hasattr(executor, "add_pending_file")) else False,
    }


@register_tool(
    "generate_pptx_deck", aliases=["generate_powerpoint_deck", "export_pptx"], category="REPORTING", parallel_safe=True
)
class GeneratePptxDeckHandler(ToolHandler):
    name = "generate_pptx_deck"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_generate_pptx_deck(args, session=session, executor=executor, **kwargs)


async def handle_generate_tearsheet_report(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Generates an institutional PDF / HTML quantitative tearsheet report."""
    from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator
    from monika.infrastructure.database.models import PaperTradeRecord

    trades = []
    if session:
        papers = (
            (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == "closed")
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        for pt in papers:
            trades.append(
                {
                    "symbol": pt.symbol,
                    "pnl_pct": pt.pnl_pct or 0.0,
                    "pnl_usd": pt.pnl_usd or 0.0,
                    "opened_at": pt.opened_at,
                    "closed_at": pt.closed_at,
                }
            )

    metrics_res = QuantTearsheetGenerator.generate_from_trades(
        trades=trades, initial_equity=float(args.get("initial_equity", 10000.0))
    )

    format_type = str(args.get("format", "html")).lower()
    os.makedirs("data/reports", exist_ok=True)
    ts_now = int(clock.now().timestamp())
    out_path = os.path.abspath(f"data/reports/tearsheet_{ts_now}.{'pdf' if format_type == 'pdf' else 'html'}")
    html_title = args.get("title", "Monika Quantitative Performance Tearsheet")
    html_content = metrics_res.to_standalone_html(title=html_title)

    if format_type == "pdf":
        try:
            from weasyprint import HTML

            HTML(string=html_content).write_pdf(out_path)
        except Exception:
            out_path = out_path.replace(".pdf", ".html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file"):
        executor.add_pending_file(
            file_path=out_path, filename=os.path.basename(out_path), caption="Institutional Performance Tearsheet"
        )

    return {
        "status": "success",
        "filepath": out_path,
        "metrics": metrics_res.to_dict(),
    }


@register_tool(
    "generate_tearsheet_report",
    aliases=["generate_pdf_report", "export_tearsheet"],
    category="REPORTING",
    parallel_safe=True,
)
class GenerateTearsheetReportHandler(ToolHandler):
    name = "generate_tearsheet_report"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_generate_tearsheet_report(args, session=session, executor=executor, **kwargs)


async def handle_export_dataset_file(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """Exports database tables and decisions into CSV or Apache Parquet format."""
    table_name = str(args.get("table_name", "paper_trades")).lower().strip()
    format_type = str(args.get("format", "csv")).lower().strip()
    os.makedirs("data/exports", exist_ok=True)
    ts_now = int(clock.now().timestamp())
    out_path = os.path.abspath(f"data/exports/{table_name}_{ts_now}.{format_type}")

    if not session:
        return {"error": "Database session required for export_dataset_file"}

    import pandas as pd

    from monika.infrastructure.database.models import AssetAnalysis, MarketChronicle, PaperTradeRecord

    model_map = {
        "paper_trades": PaperTradeRecord,
        "asset_analyses": AssetAnalysis,
        "chronicle": MarketChronicle,
    }
    target_model = model_map.get(table_name, PaperTradeRecord)
    rows = (await session.execute(select(target_model).limit(2000))).scalars().all()

    data = [r.__dict__.copy() for r in rows]
    for d in data:
        d.pop("_sa_instance_state", None)

    df = pd.DataFrame(data)
    if format_type in ("parquet", "pq"):
        try:
            df.to_parquet(out_path)
        except Exception:
            out_path = out_path.replace(".parquet", ".csv")
            df.to_csv(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    executor = kwargs.get("executor")
    if executor and hasattr(executor, "add_pending_file"):
        executor.add_pending_file(
            file_path=out_path, filename=os.path.basename(out_path), caption=f"Dataset Export: {table_name}"
        )

    return {
        "status": "success",
        "filepath": out_path,
        "row_count": len(df),
        "format": format_type,
    }


@register_tool(
    "export_dataset_file", aliases=["export_parquet", "export_table_data"], category="REPORTING", parallel_safe=True
)
class ExportDatasetFileHandler(ToolHandler):
    name = "export_dataset_file"
    category = "REPORTING"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_export_dataset_file(args, session=session, executor=executor, **kwargs)


async def handle_add_journal_entry(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Adds a qualitative trader journal / psychology reflection entry."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "error": "No database session available"}

    content = args.get("content") or args.get("notes") or args.get("text")
    if not content:
        return {"status": "error", "error": "Journal content required"}

    symbol = args.get("symbol")
    clean_sym = symbol.strip().upper().replace("/", "") if symbol else None
    sentiment_tag = str(args.get("sentiment_tag") or args.get("tag") or "discipline").lower().strip()
    ticket_ref = args.get("ticket") or args.get("ticket_ref")
    try:
        t_ref = int(ticket_ref) if ticket_ref else None
    except Exception:
        t_ref = None

    from monika.infrastructure.database.models import UserJournalEntry

    user_id = str(getattr(executor, "user_id", "default") or "default")
    entry = UserJournalEntry(
        user_id=user_id,
        content=str(content),
        symbol=clean_sym,
        sentiment_tag=sentiment_tag,
        ticket_ref=t_ref,
    )
    effective_session.add(entry)
    await effective_session.commit()

    return {
        "status": "success",
        "entry_id": entry.id,
        "message": f"Catatan jurnal trader tersimpan (ID: #{entry.id}, tag: [{sentiment_tag}])",
    }


@register_tool(
    "add_journal_entry", aliases=["record_journal", "log_psychology"], category="ANALYSIS", parallel_safe=False
)
class AddJournalEntryHandler(ToolHandler):
    name = "add_journal_entry"
    category = "ANALYSIS"
    parallel_safe = False

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_add_journal_entry(args, session=session, executor=executor, **kwargs)


async def handle_get_journal_entries(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Retrieves qualitative trader journal entries and reflections."""
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "entries": []}

    limit = int(args.get("limit", 20))
    symbol = args.get("symbol")
    tag = args.get("sentiment_tag") or args.get("tag")

    from monika.infrastructure.database.models import UserJournalEntry

    query = select(UserJournalEntry)
    if symbol:
        clean_sym = symbol.strip().upper().replace("/", "")
        query = query.where(UserJournalEntry.symbol == clean_sym)
    if tag:
        query = query.where(UserJournalEntry.sentiment_tag == str(tag).lower().strip())
    query = query.order_by(desc(UserJournalEntry.timestamp)).limit(limit)

    rows = (await effective_session.execute(query)).scalars().all()
    entries = [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "symbol": r.symbol,
            "sentiment_tag": r.sentiment_tag,
            "content": r.content,
            "ticket_ref": r.ticket_ref,
        }
        for r in rows
    ]
    return {
        "status": "success",
        "count": len(entries),
        "entries": entries,
    }


@register_tool(
    "get_journal_entries", aliases=["read_journal", "get_psychology_notes"], category="ANALYSIS", parallel_safe=True
)
class GetJournalEntriesHandler(ToolHandler):
    name = "get_journal_entries"
    category = "ANALYSIS"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_get_journal_entries(args, session=session, executor=executor, **kwargs)


async def handle_read_system_logs(
    args: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs
) -> dict:
    """Reads system runtime and activity logs for diagnosing system behavior and rejections."""
    effective_session = session or getattr(executor, "session", None)
    limit = min(500, int(args.get("lines") or args.get("limit") or 50))
    category = args.get("category")
    search = str(args.get("filter_query") or args.get("search") or "").strip()
    source = str(args.get("source") or "").lower().strip()

    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    possible_log_paths = [
        base_dir / "logs" / "monika.log",
        Path("logs/monika.log"),
        base_dir / "trading_agent.log",
    ]
    log_file = next((p for p in possible_log_paths if p.exists()), None)

    # If source is explicitly file, or search includes ERROR/WARNING, prioritize physical file:
    if log_file and (
        source == "file" or (search and any(w in search.upper() for w in ["ERROR", "WARN", "FAIL", "EXCEPTION"]))
    ):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                if search:
                    import re

                    pattern = (
                        re.compile(re.escape(search), re.IGNORECASE)
                        if not any(c in search for c in "|[]*")
                        else re.compile(search, re.IGNORECASE)
                    )
                    matched_lines = [l.strip() for l in all_lines if pattern.search(l)]
                else:
                    matched_lines = [l.strip() for l in all_lines]
                logs = [{"line": l} for l in matched_lines[-limit:]]
                return {
                    "status": "success",
                    "source": "file",
                    "file_path": str(log_file),
                    "count": len(logs),
                    "logs": logs,
                }
        except Exception as e:
            logger.warning(f"Error reading log file {log_file}: {e}")

    logs = []
    if effective_session and source != "file":
        from monika.infrastructure.database.models import ActivityLog

        q = select(ActivityLog)
        if category and category != "all":
            q = q.where(ActivityLog.category == str(category).lower().strip())
        if search:
            q = q.where(ActivityLog.description.ilike(f"%{search}%"))
        q = q.order_by(desc(ActivityLog.timestamp)).limit(limit)
        try:
            rows = (await effective_session.execute(q)).scalars().all()
            for r in rows:
                logs.append(
                    {
                        "id": r.id,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                        "category": r.category,
                        "actor": r.actor,
                        "description": r.description,
                    }
                )
        except Exception as db_err:
            logger.debug(f"DB log query note: {db_err}")

    if not logs and log_file:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                if search:
                    import re

                    pattern = re.compile(re.escape(search), re.IGNORECASE)
                    matched = [l.strip() for l in all_lines if pattern.search(l)]
                else:
                    matched = [l.strip() for l in all_lines]
                logs = [{"line": l} for l in matched[-limit:]]
        except Exception:
            pass

    return {
        "status": "success",
        "source": "file" if not effective_session or source == "file" else "db_activity_log",
        "count": len(logs),
        "logs": logs,
    }


@register_tool("read_system_logs", aliases=["get_system_logs", "view_logs"], category="SYSTEM", parallel_safe=True)
class ReadSystemLogsHandler(ToolHandler):
    name = "read_system_logs"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(
        self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs
    ) -> Any:
        return await handle_read_system_logs(args, session=session, executor=executor, **kwargs)


__all__ = [
    "handle_export_trades_to_excel",
    "ExportTradesToExcelHandler",
    "handle_generate_docx_report",
    "GenerateDocxReportHandler",
    "handle_generate_pptx_deck",
    "GeneratePptxDeckHandler",
    "handle_generate_tearsheet_report",
    "GenerateTearsheetReportHandler",
    "handle_export_dataset_file",
    "ExportDatasetFileHandler",
    "handle_add_journal_entry",
    "AddJournalEntryHandler",
    "handle_get_journal_entries",
    "GetJournalEntriesHandler",
    "handle_read_system_logs",
    "ReadSystemLogsHandler",
]
