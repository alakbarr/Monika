"""
Universal Tool Schema Normalizer for LLM Providers.

Bridges schema discrepancies between OpenAI, Anthropic, Gemini, and raw JSON Schema formats.
Ensures zero-drop tool delivery and polymorphic parameter handling across heterogeneous model providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CanonicalToolSchema:
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolSchemaNormalizer:
    """Normalizes heterogeneous tool representations to provider-specific payloads."""

    @classmethod
    def normalize_tool(cls, tool: Any) -> Optional[CanonicalToolSchema]:
        """Extract canonical name, description, and JSON schema parameters from any tool format."""
        if not isinstance(tool, dict):
            return None

        # 1. Format: OpenAI Function tool {"type": "function", "function": {...}}
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            fn = tool["function"]
            name = str(fn.get("name", "")).strip()
            if not name:
                return None
            desc = str(fn.get("description", ""))
            params = fn.get("parameters") or fn.get("input_schema") or {"type": "object", "properties": {}}
            return CanonicalToolSchema(
                name=name, description=desc, parameters=params if isinstance(params, dict) else {}
            )

        # 2. Format: Anthropic {"name": ..., "input_schema": ...}
        if "input_schema" in tool and "name" in tool:
            name = str(tool.get("name", "")).strip()
            if not name:
                return None
            desc = str(tool.get("description", ""))
            params = tool.get("input_schema") or {"type": "object", "properties": {}}
            return CanonicalToolSchema(
                name=name, description=desc, parameters=params if isinstance(params, dict) else {}
            )

        # 3. Format: Flat / Gemini {"name": ..., "parameters": ...}
        name = str(tool.get("name", "")).strip()
        if not name and "tool" in tool:
            name = str(tool.get("tool", "")).strip()
        if not name:
            return None

        desc = str(tool.get("description", ""))
        params = tool.get("parameters") or tool.get("input_schema") or {"type": "object", "properties": {}}
        return CanonicalToolSchema(name=name, description=desc, parameters=params if isinstance(params, dict) else {})

    @classmethod
    def normalize_tools(cls, tools: Optional[List[Any]]) -> List[CanonicalToolSchema]:
        """Convert a list of raw tool schemas to canonical representations, skipping unparseable entries."""
        if not tools:
            return []
        canonical_list: List[CanonicalToolSchema] = []
        for t in tools:
            canonical = cls.normalize_tool(t)
            if canonical:
                canonical_list.append(canonical)
        return canonical_list

    @classmethod
    def to_openai(cls, tools: Optional[List[Any]], supports_cache_control: bool = False) -> List[Dict[str, Any]]:
        """Serialize tools to OpenAI standard tool calling payload."""
        from monika.infrastructure.providers.openai_provider import (
            _canonicalize_schema,
            sanitize_tool_parameters_schema,
        )

        canonical_tools = cls.normalize_tools(tools)
        sorted_tools = sorted(canonical_tools, key=lambda t: t.name)
        out: List[Dict[str, Any]] = []
        for i, ct in enumerate(sorted_tools):
            clean_params = sanitize_tool_parameters_schema(ct.parameters)
            tool_obj: Dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": ct.name,
                    "description": ct.description,
                    "parameters": _canonicalize_schema(clean_params),
                },
            }
            if supports_cache_control and i == len(sorted_tools) - 1:
                tool_obj["cache_control"] = {"type": "ephemeral"}
            out.append(tool_obj)
        return out

    @classmethod
    def to_anthropic(cls, tools: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Serialize tools to Anthropic format: [{"name": ..., "description": ..., "input_schema": ...}]."""
        canonical_tools = cls.normalize_tools(tools)
        sorted_tools = sorted(canonical_tools, key=lambda t: t.name)
        out: List[Dict[str, Any]] = []
        for ct in sorted_tools:
            out.append(
                {
                    "name": ct.name,
                    "description": ct.description,
                    "input_schema": ct.parameters,
                }
            )
        return out

    @classmethod
    def to_gemini(cls, tools: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Serialize tools to Gemini functionDeclarations format."""
        from monika.infrastructure.providers.gemini_provider import _sanitize_schema_for_gemini
        from monika.infrastructure.providers.openai_provider import _canonicalize_schema

        canonical_tools = cls.normalize_tools(tools)
        sorted_tools = sorted(canonical_tools, key=lambda t: t.name)
        declarations: List[Dict[str, Any]] = []
        for ct in sorted_tools:
            decl = {
                "name": ct.name,
                "description": ct.description,
                "parameters": _canonicalize_schema(_sanitize_schema_for_gemini(ct.parameters)),
            }
            declarations.append(decl)
        if declarations:
            return [{"functionDeclarations": declarations}]
        return []
