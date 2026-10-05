# ==============================================================================
# File: analysis/tools/handlers/chart_bridge_tools.py
# ==============================================================================

"""
MT5 Chart Objects and Live Window Capture Tool Handlers (Q151).
Allows Monika to inspect user-drawn chart levels (Support/Resistance, Fibonacci,
Trendlines, Rectangles, Indicators) and capture live MT5 chart screenshots
for multimodal visual inference.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.Tools.ChartBridge")


def _get_mt5_client(ctx: dict) -> Any:
    executor = ctx.get("executor")
    return ctx.get("mt5_client") or getattr(executor, "mt5_client", None)


async def handle_get_mt5_chart_objects(args: dict, **ctx) -> dict:
    """
    Extracts user-drawn chart levels (S/R, Trendlines, Fibo, Rectangles)
    and active indicators from the shared MT5 terminal file.
    """
    symbol = str(args.get("symbol", "XAUUSD")).upper()
    client = _get_mt5_client(ctx)

    if not client:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()

    try:
        data = client.get_chart_objects(symbol)
        return data
    except Exception as e:
        logger.error(f"Error fetching MT5 chart objects for {symbol}: {e}")
        return {"status": "error", "symbol": symbol, "error": str(e)}


async def handle_capture_mt5_chart_screenshot(args: dict, **ctx) -> dict:
    """
    Captures an on-demand screenshot of the active MT5 chart window and prepares
    it for Multimodal Vision inspection.
    """
    symbol = str(args.get("symbol", "XAUUSD")).upper()
    timeframe = str(args.get("timeframe", "H1")).upper()
    width = int(args.get("width", 1280))
    height = int(args.get("height", 720))

    client = _get_mt5_client(ctx)
    if not client:
        from execution.mt5_client import get_mt5_client
        client = get_mt5_client()

    try:
        res = await client.capture_chart_screenshot(
            symbol=symbol,
            timeframe=timeframe,
            width=width,
            height=height,
        )

        if not res.get("success"):
            return res

        filepath = res.get("filepath")
        # Ingest into chart vision analyze
        from analysis.tools.domain.multimodal_tools import handle_chart_vision_analyze, ChartVisionInput
        vision_input = ChartVisionInput(
            image_path_or_base64=filepath,
            symbol=symbol,
            timeframe=timeframe,
            focus_areas=["trend", "support_resistance", "indicators", "candlestick_patterns"]
        )
        vision_res = await handle_chart_vision_analyze(vision_input, context=ctx)

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "screenshot_path": filepath,
            "vision_payload": vision_res,
            "message": f"MT5 chart screenshot captured and processed for multimodal vision analysis.",
        }
    except Exception as e:
        logger.error(f"Error capturing MT5 screenshot for {symbol}: {e}")
        return {"status": "error", "symbol": symbol, "error": str(e)}


def register_chart_bridge_tools(registry=None):
    from analysis.tools.registry import ToolRegistry, ToolDefinition
    if registry is None:
        registry = ToolRegistry.get_instance()

    tools = [
        ToolDefinition(
            name="get_mt5_chart_objects",
            description="Inspect user-drawn chart elements on MT5 chart (support/resistance lines, trendlines, Fibonacci levels, indicators) for collaborative analysis (Q151).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name e.g. 'XAUUSD'"},
                },
                "required": ["symbol"],
            },
            handler=handle_get_mt5_chart_objects,
            toolset="market_data",
            requires_db=False,
        ),
        ToolDefinition(
            name="capture_mt5_chart_screenshot",
            description="Capture high-resolution screenshot of the user's active MT5 terminal chart and run multimodal vision inspection (Q151).",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name e.g. 'XAUUSD'"},
                    "timeframe": {"type": "string", "description": "Timeframe e.g. 'H1', 'H4'"},
                    "width": {"type": "integer", "description": "Width in pixels (default 1920)"},
                    "height": {"type": "integer", "description": "Height in pixels (default 1080)"},
                },
                "required": ["symbol"],
            },
            handler=handle_capture_mt5_chart_screenshot,
            toolset="market_data",
            requires_db=False,
        ),
    ]
    for t in tools:
        registry.register(t)


register_chart_bridge_tools()

