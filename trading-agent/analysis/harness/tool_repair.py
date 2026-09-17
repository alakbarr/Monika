# ==============================================================================
# File: analysis/harness/tool_repair.py
# ==============================================================================

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.ToolRepair")

TOOL_NAME_ALIASES: Dict[str, str] = {
    "run_shell": "web_search",
    "search": "web_search",
    "search_web": "web_search",
    "google_search": "web_search",
    "fetch_price": "get_price_data",
    "get_prices": "get_price_data",
    "price_data": "get_price_data",
    "technical_analysis": "get_technical_analysis",
    "get_ta": "get_technical_analysis",
    "calculate_size": "calculate_position_size",
    "position_size": "calculate_position_size",
    "submit_analysis": "submit_asset_analysis",
    "submit_asset": "submit_asset_analysis",
    "submit_trade_analysis": "submit_asset_analysis",
    "submit_brief": "submit_fundamental_brief",
    "submit_fundamental": "submit_fundamental_brief",
    "market_snapshot": "get_verified_market_snapshot",
    "verified_snapshot": "get_verified_market_snapshot",
    "ground_truth_snapshot": "get_verified_market_snapshot",
    "get_calendar": "get_economic_calendar",
    "get_economic_calendars": "get_economic_calendar",
    "get_positions": "get_open_positions",
    "get_open_position": "get_open_positions",
    "write_scratchpad": "update_scratchpad",
    "read_scratchpad": "read_scratchpad",
}


def repair_tool_name(raw_name: str) -> str:
    """Auto-repair hallucinated, aliased, or namespaced tool names."""
    if not raw_name or not isinstance(raw_name, str):
        return ""

    clean = raw_name.strip().strip("\"'` ")
    if clean.endswith("()"):
        clean = clean[:-2].strip()

    # Strip prefixes like tools. functions. tool. fn.
    for ns in ("tools.", "functions.", "tool.", "fn.", "default.", "modules."):
        if clean.startswith(ns):
            clean = clean[len(ns):].strip()

    # Handle doubled prefixes e.g. submit_submit_
    for pfx in ("submit_", "get_", "load_", "calculate_"):
        double_pfx = pfx + pfx
        while clean.startswith(double_pfx):
            clean = clean[len(pfx):]

    # Check alias map
    if clean in TOOL_NAME_ALIASES:
        repaired = TOOL_NAME_ALIASES[clean]
        logger.info(f"Auto-repaired tool name: '{raw_name}' -> '{repaired}'")
        return repaired

    # Check registry aliases
    try:
        from analysis.tools.registry import default_tool_registry
        canonical = default_tool_registry.resolve_name(clean)
        if canonical != clean:
            logger.info(f"Registry resolved tool alias: '{clean}' -> '{canonical}'")
            return canonical
    except Exception:
        pass

    return clean


def repair_tool_arguments(args: Any) -> Dict[str, Any]:
    """Repair corrupted JSON arguments (trailing commas, python constants, single quotes)."""
    if isinstance(args, dict):
        return args

    if not args:
        return {}

    if not isinstance(args, str):
        try:
            return dict(args)
        except Exception:
            return {}

    args_str = args.strip()
    if not args_str:
        return {}

    # Try standard parse first
    try:
        return json.loads(args_str)
    except json.JSONDecodeError:
        pass

    # Repair common LLM syntax defects:
    # 1. Trailing commas before closing braces/brackets
    cleaned = re.sub(r',\s*([}\]])', r'\1', args_str)

    # 2. Python booleans and None
    cleaned = re.sub(r'\bNone\b', 'null', cleaned)
    cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
    cleaned = re.sub(r'\bFalse\b', 'false', cleaned)

    # 3. Single quotes to double quotes
    if "'" in cleaned and '"' not in cleaned:
        cleaned = cleaned.replace("'", '"')

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"Failed to auto-repair JSON tool arguments: '{args_str[:120]}'")
        return {}
