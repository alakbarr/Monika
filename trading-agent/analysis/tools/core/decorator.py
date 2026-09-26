# ==============================================================================
# File: analysis/tools/core/decorator.py
# ==============================================================================

"""
Declarative Tool Decorator (@monika_tool).
Institutional-grade tool orchestration architecture.

Automatically extracts parameter types, defaults, and docstrings from Python functions
to construct structured ToolDefinition instances.
"""

from __future__ import annotations

import functools
import inspect
import re
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from analysis.tools.core.definition import (
    ExecutionTier,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
)


def _parse_param_descriptions_from_docstring(docstring: Optional[str]) -> Dict[str, str]:
    """Extracts parameter descriptions from Google/Sphinx style docstrings."""
    if not docstring:
        return {}

    descriptions: Dict[str, str] = {}
    lines = docstring.split("\n")
    current_param: Optional[str] = None
    current_desc: List[str] = []

    for line in lines:
        stripped = line.strip()
        # Match Google style: "param_name (type): description" or "param_name: description"
        match = re.match(r"^(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)$", stripped)
        if match:
            if current_param and current_desc:
                descriptions[current_param] = " ".join(current_desc).strip()
            current_param = match.group(1)
            current_desc = [match.group(2)]
        elif current_param and stripped and not stripped.startswith("Returns:") and not stripped.startswith("Raises:"):
            current_desc.append(stripped)
        elif stripped.startswith("Returns:") or stripped.startswith("Raises:"):
            if current_param and current_desc:
                descriptions[current_param] = " ".join(current_desc).strip()
            current_param = None
            current_desc = []

    if current_param and current_desc:
        descriptions[current_param] = " ".join(current_desc).strip()

    return descriptions


def monika_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: ToolCategory = ToolCategory.CORE,
    tier: ExecutionTier = ExecutionTier.TIER_1_INPROCESS,
    has_side_effects: bool = False,
    is_model_tool: bool = True,
    timeout_seconds: float = 30.0,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for registering functions as first-class Monika tools.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        raw_doc = fn.__doc__ or ""
        # Clean first line as short tool description if not provided
        first_line = raw_doc.strip().split("\n")[0].strip() if raw_doc else ""
        tool_desc = description or first_line or f"Tool {tool_name}"

        sig = inspect.signature(fn)
        param_docs = _parse_param_descriptions_from_docstring(raw_doc)

        try:
            type_hints = get_type_hints(fn)
        except Exception:
            type_hints = {}

        parameters: Dict[str, ToolParameter] = {}
        for p_name, param in sig.parameters.items():
            if p_name in ("self", "cls"):
                continue

            hint = type_hints.get(p_name, str)
            type_name = getattr(hint, "__name__", str(hint))
            is_required = param.default is inspect.Parameter.empty
            default_val = None if is_required else param.default

            p_desc = param_docs.get(p_name, f"Parameter {p_name}")

            parameters[p_name] = ToolParameter(
                name=p_name,
                type_name=type_name,
                description=p_desc,
                required=is_required,
                default=default_val,
            )

        tool_def = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
            category=category,
            tier=tier,
            has_side_effects=has_side_effects,
            is_model_tool=is_model_tool,
            timeout_seconds=timeout_seconds,
            handler=fn,
        )

        fn.__monika_tool_def__ = tool_def  # type: ignore[attr-defined]
        return fn

    return decorator
