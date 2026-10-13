# ==============================================================================
# File: application/analysis/tools/definitions/base.py
# ==============================================================================

"""
Base schema helpers and JSON definition minifiers for LLM tools.
"""

from __future__ import annotations

from typing import Any


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Fungsi helper pencetak JSON Schema (Anthropic format)."""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def minify_tool_definitions(tools: list[dict]) -> list[dict]:
    """
    Pi Minimal Tool Schemas: Strips superfluous narrative prose while preserving
    exact parameter keys, types, enums, required constraints, and primary description.
    Saves up to 60% declaration tokens across multi-turn agent loops.
    """
    minified = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        m_tool = dict(t)
        raw_desc = m_tool.get("description", "")
        if raw_desc:
            first_line = raw_desc.strip().split("\n")[0].split(". ")[0].strip()
            m_tool["description"] = first_line if first_line.endswith(".") else f"{first_line}."

        schema = m_tool.get("input_schema")
        if isinstance(schema, dict):
            new_schema = dict(schema)
            props = new_schema.get("properties")
            if isinstance(props, dict):
                new_props = {}
                for p_name, p_val in props.items():
                    if isinstance(p_val, dict):
                        cp = dict(p_val)
                        p_desc = cp.get("description", "")
                        if p_desc and len(p_desc) > 80:
                            cp["description"] = p_desc.split(". ")[0].split("\n")[0].strip()
                        new_props[p_name] = cp
                    else:
                        new_props[p_name] = p_val
                new_schema["properties"] = new_props
            m_tool["input_schema"] = new_schema
        minified.append(m_tool)
    return minified


def make_strict_tool_definitions(tools: list[dict]) -> list[dict]:
    """
    DeepSeek / OpenAI strict schema compliance:
    Ensures all properties are declared in required and additionalProperties is False.
    """
    strict_tools = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        st = dict(t)
        schema = st.get("input_schema")
        if isinstance(schema, dict):
            sc = dict(schema)
            sc["additionalProperties"] = False
            props = sc.get("properties", {})
            if isinstance(props, dict):
                sc["required"] = list(props.keys())
            st["input_schema"] = sc
        strict_tools.append(st)
    return strict_tools


__all__ = [
    "_tool",
    "minify_tool_definitions",
    "make_strict_tool_definitions",
]
