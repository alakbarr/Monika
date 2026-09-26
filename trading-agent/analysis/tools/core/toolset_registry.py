# ==============================================================================
# File: analysis/tools/core/toolset_registry.py
# ==============================================================================

"""
Unified Modular Toolset Registry.
Institutional-grade tool orchestration architecture.

Manages registration, capability classification, role-based toolset filtering,
and schema compilation for LLM agents.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Set

from analysis.tools.core.definition import (
    ExecutionTier,
    ToolCategory,
    ToolDefinition,
)

logger = logging.getLogger("TradingAgent.Analysis.Tools.Registry")


class ToolsetRegistry:
    """Thread-safe registry for modular tools with role and tier filtering."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool_def_or_fn: Any) -> ToolDefinition:
        """Register a ToolDefinition or a @monika_tool decorated function."""
        if hasattr(tool_def_or_fn, "__monika_tool_def__"):
            tool_def: ToolDefinition = getattr(tool_def_or_fn, "__monika_tool_def__")
        elif isinstance(tool_def_or_fn, ToolDefinition):
            tool_def = tool_def_or_fn
        else:
            raise TypeError(f"Expected ToolDefinition or @monika_tool decorated function, got {type(tool_def_or_fn)}")

        self._tools[tool_def.name] = tool_def
        logger.debug(f"[ToolsetRegistry] Registered tool '{tool_def.name}' [{tool_def.category.value}]")
        return tool_def

    def unregister(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_all_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def filter_tools(
        self,
        categories: Optional[List[ToolCategory]] = None,
        max_tier: Optional[ExecutionTier] = None,
        is_model_tool: Optional[bool] = True,
    ) -> List[ToolDefinition]:
        """Filter registered tools by categories, maximum sandbox tier, and model availability."""
        matched = []
        for t in self._tools.values():
            if is_model_tool is not None and t.is_model_tool != is_model_tool:
                continue
            if categories and t.category not in categories:
                continue
            if max_tier and t.tier > max_tier:
                continue
            matched.append(t)
        return matched

    def export_openai_schemas(
        self,
        categories: Optional[List[ToolCategory]] = None,
        max_tier: Optional[ExecutionTier] = None,
    ) -> List[Dict[str, Any]]:
        """Exports JSON schemas matching the specified criteria."""
        tools = self.filter_tools(categories=categories, max_tier=max_tier, is_model_tool=True)
        return [t.to_openai_schema() for t in tools]


_GLOBAL_TOOLSET_REGISTRY = ToolsetRegistry()


def get_toolset_registry() -> ToolsetRegistry:
    return _GLOBAL_TOOLSET_REGISTRY
