"""
Progressive Tool Disclosure Registry.

Instead of injecting 50+ tool schemas into every prompt (which causes context poisoning,
high latency, and cache invalidation), this registry provides:
1. Core Primitives (always pinned, ~200 tokens)
2. Category Packs (loaded on demand via `load_tool_category`, ~300-500 tokens)
3. Direct Schema Resolution
"""

import logging
from typing import List, Dict, Any, Optional

from analysis.tools.tools_definitions import (
    ALL_TOOLS,
    STAGE1_TOOLS,
    STAGE2_TOOLS,
    TELEGRAM_TOOLS,
    GET_MARKET_QUOTE,
    _tool,
)

logger = logging.getLogger("TradingAgent.ToolRegistry")

LOAD_TOOL_CATEGORY_TOOL = _tool(
    name="load_tool_category",
    description=(
        "Dynamically loads full parameter schemas for a specialized tool category into your active context. "
        "Available categories: 'MACRO', 'TECHNICAL', 'SENTIMENT', 'EXECUTION', 'POSITION'."
    ),
    properties={
        "category": {
            "type": "string",
            "enum": ["MACRO", "TECHNICAL", "SENTIMENT", "EXECUTION", "POSITION"],
            "description": "Category of tools to load into active session schema.",
        }
    },
    required=["category"],
)

SEARCH_TOOLS_TOOL = _tool(
    name="search_tools",
    description=(
        "Semantic and keyword discovery of available tools across the registry. "
        "Find tools by capability, indicator name, data type, or asset class without loading all schemas."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "Keywords or capability to search for (e.g. 'volatility', 'order flow', 'news', 'yields').",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of tools to return (default 5).",
        },
    },
    required=["query"],
)

DESCRIBE_TOOL_TOOL = _tool(
    name="describe_tool",
    description=(
        "Retrieve the complete parameter schema and usage specification for a specific tool by name."
    ),
    properties={
        "tool_name": {
            "type": "string",
            "description": "Exact name of the tool to describe (e.g. 'get_smc_zones', 'get_bond_yield_spreads').",
        }
    },
    required=["tool_name"],
)

CALCULATE_POSITION_SIZE_TOOL = _tool(
    name="calculate_position_size",
    description=(
        "Deterministic position sizing calculator. Given symbol, entry, stop_loss, direction, and risk percentage, "
        "calculates the exact lot size, risk in USD, pip value, and ATR ratio. "
        "MANDATORY: LLM must use this tool and NOT calculate lot sizes manually."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'EURUSD', 'XAUUSD')"},
        "entry_price": {"type": "number", "description": "Planned entry price"},
        "stop_loss": {"type": "number", "description": "Stop loss price level"},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Trade direction (optional)"},
        "risk_pct": {"type": "number", "description": "Risk percentage of account (e.g. 1.0 for 1%)"},
    },
    required=["symbol", "entry_price", "stop_loss"],
)


class ProgressiveToolRegistry:
    """Manages progressive tool loading and dynamic tool disclosure."""

    CATEGORY_MAP: Dict[str, List[str]] = {
        "MACRO": [
            "get_market_session", "get_fundamental_brief", "get_economic_calendar",
            "get_vix", "get_cot_report", "get_bond_yield_spreads", "get_dxy",
            "get_interest_rates", "get_treasury_yields", "get_fedwatch_probabilities", "get_eia_oil_inventory"
        ],
        "TECHNICAL": [
            "get_price_history", "get_technical_indicators", "get_multi_timeframe_summary",
            "get_atr", "get_swing_points", "get_structure_breaks", "get_smc_zones",
            "get_fibonacci_levels", "get_daily_range_context", "get_optimal_intraday_levels",
            "get_chart", "get_market_quote"
        ],
        "SENTIMENT": [
            "get_news_items", "get_news_digest", "get_fear_greed_index", "get_funding_rate",
            "get_retail_sentiment", "get_forex_sentiment", "get_fxssi_sentiment",
            "get_structured_sentiment"
        ],
        "EXECUTION": [
            "propose_action", "get_spread_snapshot", "get_active_triggers"
        ],
        "POSITION": [
            "get_open_positions", "get_account_info", "get_trade_history",
            "get_trade_details", "get_paper_trading_performance", "get_risk_state",
            "get_asset_analysis", "get_edge_tracker_status", "get_market_correlations"
        ],
    }

    def __init__(self, tools_list: Optional[List[Dict[str, Any]]] = None):
        source_tools = tools_list or ALL_TOOLS
        self._tool_by_name: Dict[str, Dict[str, Any]] = {t["name"]: t for t in source_tools if "name" in t}
        
        # Register built-in registry tools
        self._tool_by_name["load_tool_category"] = LOAD_TOOL_CATEGORY_TOOL
        self._tool_by_name["search_tools"] = SEARCH_TOOLS_TOOL
        self._tool_by_name["describe_tool"] = DESCRIBE_TOOL_TOOL
        self._tool_by_name["calculate_position_size"] = CALCULATE_POSITION_SIZE_TOOL
        self._tool_by_name.setdefault("get_market_quote", GET_MARKET_QUOTE)

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch tool schema definition by name."""
        return self._tool_by_name.get(name)

    def search_tools(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Discover tools across the entire registry by matching query terms against
        tool names, descriptions, categories, and parameter names.
        Returns a concise list of candidate tools with category and description.
        """
        q = (query or "").strip().lower()
        if not q:
            return []

        # Find category for tools
        tool_to_cat = {}
        for cat, tools in self.CATEGORY_MAP.items():
            for t in tools:
                tool_to_cat[t] = cat

        matches = []
        tokens = [t for t in q.split() if len(t) > 1]

        for name, tool in self._tool_by_name.items():
            score = 0
            name_lower = name.lower()
            desc_lower = (tool.get("description") or "").lower()
            cat = tool_to_cat.get(name, "GENERAL")

            # Exact or prefix match on name
            if q in name_lower:
                score += 10
            # Token match on name
            for token in tokens:
                if token in name_lower:
                    score += 5
                if token in desc_lower:
                    score += 2
                if token in cat.lower():
                    score += 3

            if score > 0:
                input_schema = tool.get("input_schema", {})
                props = list(input_schema.get("properties", {}).keys())
                req = input_schema.get("required", [])
                matches.append({
                    "score": score,
                    "name": name,
                    "category": cat,
                    "description": (tool.get("description") or "").split(".")[0],
                    "parameters": props,
                    "required": req,
                })

        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        # Strip score before returning
        return [
            {
                "name": m["name"],
                "category": m["category"],
                "description": m["description"],
                "parameters": m["parameters"],
                "required": m["required"],
            }
            for m in matches[:limit]
        ]

    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve full schema for a specific tool by name."""
        return self.get_tool(tool_name)

    def compact_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a compressed tool schema saving ~50-70% tokens.
        Preserves function name, concise docstring, parameter types, and required fields.
        """
        name = schema.get("name", "")
        desc = schema.get("description", "").strip()
        # Truncate long descriptions to first sentence or 120 chars
        concise_desc = desc.split(".")[0] if "." in desc else desc[:120]
        input_schema = schema.get("input_schema", {})
        props = input_schema.get("properties", {})
        req = input_schema.get("required", [])

        compact_props = {}
        for p_name, p_val in props.items():
            p_dict: Dict[str, Any] = {"type": p_val.get("type", "string")}
            if "enum" in p_val:
                p_dict["enum"] = p_val["enum"]
            p_desc = p_val.get("description", "")
            if p_desc:
                p_dict["desc"] = p_desc.split(".")[0] if "." in p_desc else p_desc[:60]
            compact_props[p_name] = p_dict

        return {
            "name": name,
            "description": concise_desc,
            "input_schema": {
                "type": "object",
                "properties": compact_props,
                "required": req,
            },
        }

    def get_core_schemas(self, stage: str = "stage2") -> List[Dict[str, Any]]:
        """
        Returns minimal core primitive schemas pinned at start of session (~200-400 tokens).
        """
        core_names = [
            "search_tools",
            "describe_tool",
            "load_tool_category",
            "calculate_position_size",
            "get_open_positions",
            "get_market_quote",
        ]
        if stage == "stage1":
            core_names.extend(["submit_fundamental_brief", "get_market_session", "get_economic_calendar"])
        else:
            core_names.extend(["submit_asset_analysis", "get_price_history", "get_technical_indicators"])

        schemas: List[Dict[str, Any]] = []
        for name in core_names:
            tool = self.get_tool(name)
            if tool:
                schemas.append(tool)
        return schemas

    def get_compact_core_schemas(self, stage: str = "stage2") -> List[Dict[str, Any]]:
        """Returns compact representations of core schemas for maximum context efficiency."""
        return [self.compact_schema(s) for s in self.get_core_schemas(stage=stage)]

    def load_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Dynamically retrieves full schemas for a tool category.
        """
        cat_upper = category.upper()
        tool_names = self.CATEGORY_MAP.get(cat_upper, [])
        schemas: List[Dict[str, Any]] = []
        for name in tool_names:
            tool = self.get_tool(name)
            if tool:
                schemas.append(tool)
        return schemas

    get_tools_for_category = load_category

    def get_prescreen_schemas(self) -> List[Dict[str, Any]]:
        """
        Minimal tool schema pack for rapid prescreening (~400 tokens).
        Prunes 80% of unused tool schemas during rapid symbol screening.
        """
        prescreen_tools = [
            "get_price_history", "get_technical_indicators",
            "get_multi_timeframe_summary", "get_market_session"
        ]
        schemas = []
        for name in prescreen_tools:
            tool = self.get_tool(name)
            if tool:
                schemas.append(tool)
        return schemas

    def get_schemas_for_asset(
        self,
        symbol: str,
        stage: str = "stage2",
        is_prescreen: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Dynamically filters tool schemas tailored to symbol asset class and cycle phase.
        Eliminates irrelevant tools (e.g. funding rates on EURUSD, bond spreads on BTCUSD).
        """
        if is_prescreen:
            return self.get_prescreen_schemas()

        base_schemas = self.get_core_schemas(stage=stage)
        sym = (symbol or "").strip().upper().replace("/", "")

        # Asset-specific tool routing
        additional_tools = []
        if sym in ("BTCUSD", "ETHUSD", "SOLUSD") or "crypto" in sym.lower():
            additional_tools.extend(["get_funding_rate", "get_fear_greed_index"])
        else:
            # Forex and Commodities
            additional_tools.extend(["get_bond_yield_spreads", "get_cot_report", "get_dxy"])

        for name in additional_tools:
            tool = self.get_tool(name)
            if tool and tool not in base_schemas:
                base_schemas.append(tool)

        return base_schemas

    def get_stub_summary(self) -> str:
        """Generates compact category stub index for prompt Tier 2."""
        lines = ["## AVAILABLE TOOL CATEGORIES:"]
        for cat, tools in self.CATEGORY_MAP.items():
            lines.append(f"- {cat}: {', '.join(tools[:6])}...")
        return "\n".join(lines)


# Backward-compatible class alias
ToolRegistry = ProgressiveToolRegistry

# Global default instance
default_registry = ProgressiveToolRegistry()
