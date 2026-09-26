# ==============================================================================
# File: analysis/tools/tool_search_engine.py
# ==============================================================================

"""
Progressive Tool Search & Deferred Tool Registry Engine.
Context preservation architecture for large toolsets and extensive MCP ecosystems.

When tool count scales to dozens or hundreds (e.g. 88 native tools + remote MCP servers
with thousands of endpoints like Cloudflare/GitLab), serializing every JSON schema
into the system prompt degrades model reasoning, consumes up to 85% of the context window,
and invalidates KV-caches.

Solution (Progressive Disclosure):
  1. PINNED (Core) TOOLS: Essential primitives always exposed directly in the prompt
     (file reading, patching, terminal execution, position sizing, market quotes).
  2. DEFERRED TOOLS: Secondary and domain tools hidden behind meta-tools:
     - tool_search(query, category=None): Returns matching tool names and brief summaries.
     - describe_tool(tool_name): Fetches the full JSON schema of a specific tool on-demand.
     - load_tool_category(category): Mounts an entire domain pack (e.g. 'MACRO', 'BROWSER').
  3. TOKEN BUDGET SENTINEL:
     Monitors schema token burden; automatically transitions deferrable tools into search mode
     when tool definitions exceed the configured token threshold (default 3,500 tokens).
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Tools.ToolSearchEngine")

DEFAULT_TOOL_TOKEN_BUDGET = 3500


@dataclass
class ToolDefinitionRecord:
    name: str
    description: str
    category: str
    parameters: Dict[str, Any]
    is_pinned: bool = False
    is_active: bool = False
    tags: List[str] = field(default_factory=list)


class ToolSearchEngine:
    """
    Manages progressive tool discovery and dynamically controls which tool schemas
    are materialized in the active prompt context.
    """

    def __init__(self, token_budget: int = DEFAULT_TOOL_TOKEN_BUDGET):
        self.token_budget = token_budget
        self._tools: Dict[str, ToolDefinitionRecord] = {}
        self._active_tools: Set[str] = set()

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        category: str = "GENERAL",
        is_pinned: bool = False,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Registers a tool definition into the registry."""
        record = ToolDefinitionRecord(
            name=name,
            description=description,
            category=category.upper(),
            parameters=parameters,
            is_pinned=is_pinned,
            is_active=is_pinned,  # Pinned tools are active by default
            tags=tags or [],
        )
        self._tools[name] = record
        if is_pinned:
            self._active_tools.add(name)

    def search_tools(
        self, query: str, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Searches available tools using token matching and fuzzy similarity.
        Returns a list of dicts with 'name', 'category', and 'description'.
        """
        results = []
        q_lower = query.lower().strip()
        cat_filter = category.upper() if category else None

        for name, record in self._tools.items():
            if cat_filter and record.category != cat_filter:
                continue

            # Direct substring match or multi-token overlap
            score = 0.0
            search_corpus = f"{record.name} {record.description} {' '.join(record.tags)}".lower()

            if q_lower in search_corpus:
                score += 1.0
            else:
                query_tokens = [t for t in q_lower.split() if t]
                matching_tokens = sum(1 for tok in query_tokens if tok in search_corpus)
                if matching_tokens > 0:
                    score += (matching_tokens / max(1, len(query_tokens))) * 0.8

                # Fuzzy sequence matcher
                ratio = difflib.SequenceMatcher(None, q_lower, record.name.lower()).ratio()
                if ratio > 0.4:
                    score += ratio * 0.5

            if score > 0.2:
                results.append((score, record))

        # Sort by relevance score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "name": r.name,
                "category": r.category,
                "description": r.description[:180] + ("..." if len(r.description) > 180 else ""),
            }
            for _, r in results[:limit]
        ]

    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full JSON schema and marks the tool as temporarily active in the session.
        """
        record = self._tools.get(tool_name)
        if not record:
            return None

        # Automatically mount into active set
        self._active_tools.add(tool_name)
        record.is_active = True

        return {
            "name": record.name,
            "description": record.description,
            "category": record.category,
            "parameters": record.parameters,
        }

    def load_category(self, category_name: str) -> List[str]:
        """
        Mounts all tools belonging to a category pack into the active toolset.
        """
        cat_upper = category_name.upper()
        loaded = []
        for name, record in self._tools.items():
            if record.category == cat_upper:
                self._active_tools.add(name)
                record.is_active = True
                loaded.append(name)

        logger.info(f"[ToolSearchEngine] Mounted category '{cat_upper}': {len(loaded)} tools activated.")
        return loaded

    def get_active_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Serializes schemas of all currently active (pinned or mounted) tools
        into OpenAI/Anthropic compatible function calling specifications.
        """
        schemas = []
        for name in sorted(self._active_tools):
            record = self._tools.get(name)
            if record:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": record.name,
                        "description": record.description,
                        "parameters": record.parameters,
                    },
                })
        return schemas

    def estimate_schema_tokens(self) -> int:
        """Estimates total token burden of currently active tool schemas."""
        serialized = json.dumps(self.get_active_tool_schemas())
        return len(serialized) // 4

    def materialize_tools_for_query(self, query: str, top_k: int = 5) -> List[str]:
        """
        Dynamically finds and mounts the top-K relevant tools for a user query or turn context
        if they are not already active, respecting token budgets.
        """
        matches = self.search_tools(query, limit=top_k)
        activated = []
        for m in matches:
            tname = m["name"]
            if tname not in self._active_tools:
                # Check token budget before activating
                if self.estimate_schema_tokens() < self.token_budget:
                    self._active_tools.add(tname)
                    rec = self._tools.get(tname)
                    if rec:
                        rec.is_active = True
                    activated.append(tname)
        return activated

    def execute_progressive_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        executor: Optional[Any] = None,
    ) -> Any:
        """
        Executes a tool discovered progressively. If the tool is not active,
        it automatically describes and activates it, then dispatches execution.
        """
        if tool_name not in self._tools:
            return {"success": False, "error": f"Tool '{tool_name}' not registered in ToolSearchEngine."}

        self.describe_tool(tool_name)

        if executor is not None:
            if hasattr(executor, "execute_tool"):
                return executor.execute_tool(tool_name, arguments)
            elif callable(executor):
                return executor(tool_name, arguments)

        return {
            "success": True,
            "tool_name": tool_name,
            "status": "activated",
            "message": f"Tool '{tool_name}' mounted into active context.",
        }
