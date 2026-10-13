# ==============================================================================
# File: analysis/tools/handlers/trade_intel/registry.py
# ==============================================================================

"""
ToolRegistry registration logic for trade intelligence tools.
"""

from __future__ import annotations

from monika.application.analysis.tools.registry import ToolDefinition, ToolRegistry
from monika.application.analysis.tools.handlers.trade_intel.performance import *
from monika.application.analysis.tools.handlers.trade_intel.simulation import *
from monika.application.analysis.tools.handlers.trade_intel.debate import *
from monika.application.analysis.tools.handlers.trade_intel.reporting import *
from monika.application.analysis.tools.handlers.trade_intel.operations import *


def register_trade_intel_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_trade_history",
            description="Retrieve recent trade history with filters for status, symbol, and pagination.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            handler=handle_get_trade_history,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="export_trades_to_excel",
            description="Export trading journal and performance records to an Excel (.xlsx) spreadsheet document.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}, "filename": {"type": "string"}}},
            handler=handle_export_trades_to_excel,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_docx_report",
            description="Generate institutional Word (.docx) performance report with quantitative tables and LLM narrative.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "narrative": {"type": "string"},
                    "filename": {"type": "string"},
                },
            },
            handler=handle_generate_docx_report,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_pptx_deck",
            description="Generate PowerPoint (.pptx) presentation pitch deck covering multi-agent trading performance.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "filename": {"type": "string"},
                },
            },
            handler=handle_generate_pptx_deck,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="generate_tearsheet_report",
            description="Generate institutional HTML / PDF performance tearsheet from trading record database.",
            parameters={"type": "object", "properties": {"format": {"type": "string"}, "title": {"type": "string"}}},
            handler=handle_generate_tearsheet_report,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="export_dataset_file",
            description="Export database records (paper_trades, asset_analyses, chronicle) to CSV or Apache Parquet file.",
            parameters={
                "type": "object",
                "properties": {"table_name": {"type": "string"}, "format": {"type": "string"}},
            },
            handler=handle_export_dataset_file,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="cancel_stale_pending_orders",
            description="Cancel resting MT5 pending orders older than max_age_hours.",
            parameters={"type": "object", "properties": {"max_age_hours": {"type": "number"}}},
            handler=handle_cancel_stale_pending_orders,
            toolset="trade_intel",
            requires_db=False,
        ),
        ToolDefinition(
            name="close_positions_batch",
            description="Close positions filtered by profit, loss, or all without triggering emergency daemon pause.",
            parameters={
                "type": "object",
                "properties": {"filter_type": {"type": "string"}, "reason": {"type": "string"}},
            },
            handler=handle_close_positions_batch,
            toolset="trade_intel",
            requires_db=False,
        ),
        ToolDefinition(
            name="run_walk_forward_analysis",
            description="Run Walk-Forward Analysis (WFA) on trading strategy to evaluate out-of-sample statistical robustness.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "strategy": {"type": "string"},
                    "n_folds": {"type": "integer"},
                },
            },
            handler=handle_run_walk_forward_analysis,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_graduation_status",
            description="Calculate paper-to-live trading graduation progress, win rate, and readiness scorecard.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_graduation_status,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="add_journal_entry",
            description="Record a trader journal note or psychology reflection (FOMO, discipline, trade reflection).",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "symbol": {"type": "string"},
                    "sentiment_tag": {"type": "string"},
                    "ticket": {"type": "integer"},
                },
                "required": ["content"],
            },
            handler=handle_add_journal_entry,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_journal_entries",
            description="Retrieve qualitative trader journal notes and psychology reflections.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "symbol": {"type": "string"},
                    "sentiment_tag": {"type": "string"},
                },
            },
            handler=handle_get_journal_entries,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="simulate_price_shock",
            description="Simulate sudden adverse or favorable price movements (pips or percent) on current positions and equity.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "shock_pips": {"type": "number"},
                    "shock_pct": {"type": "number"},
                },
            },
            handler=handle_simulate_price_shock,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="read_system_logs",
            description="Read system activity and runtime logs to diagnose execution decisions, rejections, and health.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "category": {"type": "string"},
                    "search": {"type": "string"},
                },
            },
            handler=handle_read_system_logs,
            toolset="trade_intel",
            requires_db=True,
        ),
        ToolDefinition(
            name="run_parameter_plateau_optimization",
            description="Run Parameter Flat Plateau Optimization to find robust, curve-fitting-resistant parameter regions.",
            parameters={
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "n_trials": {"type": "integer"}},
            },
            handler=handle_run_parameter_plateau_optimization,
            toolset="trade_intel",
        ),
        ToolDefinition(
            name="get_recent_tick_flow",
            description="Fetches recent MT5 tick flow order flow delta (aggressive buy vs sell volume) over the last N minutes.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "minutes": {"type": "integer"}}},
            handler=handle_get_recent_tick_flow,
            toolset="trade_intel",
        ),
        ToolDefinition(
            name="export_tick_data",
            description="Exports historical tick data from MT5 to a CSV file for download or local quantitative research.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "hours": {"type": "integer"}}},
            handler=handle_export_tick_data,
            toolset="trade_intel",
        ),
        ToolDefinition(
            name="get_broker_expenses_summary",
            description="Aggregates broker expenses (commissions, swap charges, and financing fees) over a specified period.",
            parameters={"type": "object", "properties": {"days": {"type": "integer"}, "symbol": {"type": "string"}}},
            handler=handle_get_broker_expenses_summary,
            toolset="trade_intel",
            requires_db=False,
        ),
    ]
    for t in tools:
        registry.register(t)


__all__ = ["register_trade_intel_tools"]
