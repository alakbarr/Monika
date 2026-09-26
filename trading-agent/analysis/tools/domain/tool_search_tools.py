# ==============================================================================
# File: analysis/tools/domain/tool_search_tools.py
# ==============================================================================

"""
Progressive Tool Search & Schema Materialization Domain Tools.
Drastically cuts prompt token consumption by keeping secondary tool schemas deferred
until discovered via search or category mount.

Tools registered:
  - tool_search: Semantic/keyword discovery of available tools across all categories.
  - describe_tool: Fetches full parameter schema for a specific tool on demand.
  - load_tool_category: Dynamically activates an entire domain tool pack into context.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from analysis.tools.tool_search_engine import ToolSearchEngine
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.ToolSearchTools")

# Global singleton ToolSearchEngine instance
_TOOL_SEARCH_ENGINE = ToolSearchEngine()


def get_tool_search_engine() -> ToolSearchEngine:
    """Return the global ToolSearchEngine singleton, synced with unified_tool_registry."""
    _sync_from_registry(_TOOL_SEARCH_ENGINE)
    return _TOOL_SEARCH_ENGINE


def _sync_from_registry(engine: ToolSearchEngine) -> None:
    """Synchronize registered tools from unified_tool_registry into the search index."""
    for name, entry in unified_tool_registry._tools.items():
        if name not in engine._tools:
            schema = {}
            if hasattr(entry.input_model, "model_json_schema"):
                schema = entry.input_model.model_json_schema()
                schema.pop("title", None)
            engine.register_tool(
                name=entry.name,
                description=entry.description or f"Tool {entry.name}",
                parameters=schema,
                category=entry.category or "GENERAL",
                is_pinned=entry.category in ("FILESYSTEM", "SYSTEM"),
            )


class ToolSearchInput(BaseModel):
    """Input parameters for searching tools across the registry."""
    query: str = Field(
        ...,
        description="Search query or keywords describing desired capability (e.g. 'volatility', 'file patch', 'terminal', 'yields')."
    )
    category: Optional[str] = Field(
        None,
        description="Optional category filter (e.g. 'MACRO', 'TECHNICAL', 'FILESYSTEM', 'SYSTEM', 'KNOWLEDGE')."
    )
    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of search results to return (default 10)."
    )


class DescribeToolInput(BaseModel):
    """Input parameters for retrieving full schema of a specific tool."""
    tool_name: str = Field(
        ...,
        description="Exact name of the tool to inspect (e.g. 'patch', 'terminal', 'calculate_position_size')."
    )


class LoadToolCategoryInput(BaseModel):
    """Input parameters for mounting an entire category pack."""
    category: str = Field(
        ...,
        description="Category name to mount into active tool context (e.g. 'MACRO', 'TECHNICAL', 'SENTIMENT', 'FILESYSTEM', 'SYSTEM')."
    )


@unified_tool_registry.register(
    name="tool_search",
    category="SYSTEM",
    input_model=ToolSearchInput,
)
async def handle_tool_search(
    params: ToolSearchInput,
    context: Optional[Any] = None,
) -> str:
    """Search for relevant tools without loading their complete JSON schemas."""
    engine = get_tool_search_engine()
    results = engine.search_tools(
        query=params.query,
        category=params.category,
        limit=params.limit,
    )
    if not results:
        return f"No tools found matching query '{params.query}' in category '{params.category or 'ALL'}'."
    return json.dumps(results, indent=2)


@unified_tool_registry.register(
    name="describe_tool",
    category="SYSTEM",
    input_model=DescribeToolInput,
)
async def handle_describe_tool(
    params: DescribeToolInput,
    context: Optional[Any] = None,
) -> str:
    """Retrieve full schema and parameter specification for a tool, activating it in the session."""
    engine = get_tool_search_engine()
    desc = engine.describe_tool(params.tool_name)
    if not desc:
        return f"[ERROR] Tool '{params.tool_name}' not found in registry."
    return json.dumps(desc, indent=2)


@unified_tool_registry.register(
    name="load_tool_category",
    category="SYSTEM",
    input_model=LoadToolCategoryInput,
)
async def handle_load_tool_category(
    params: LoadToolCategoryInput,
    context: Optional[Any] = None,
) -> str:
    """Mount all tools in a specific category pack into active session context."""
    engine = get_tool_search_engine()
    loaded = engine.load_category(params.category)
    if not loaded:
        return f"No tools found in category '{params.category}'."
    return f"Successfully loaded {len(loaded)} tools for category '{params.category.upper()}': {', '.join(loaded)}"
