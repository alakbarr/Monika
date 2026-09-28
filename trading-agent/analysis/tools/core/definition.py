# ==============================================================================
# File: analysis/tools/core/definition.py
# ==============================================================================

"""
Core Tool and Parameter Definitions with Multi-Tier Sandboxing Metadata.
Institutional-grade tool orchestration architecture.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type


class ToolCategory(str, Enum):
    CORE = "core"
    QUANT_TRADING = "quant_trading"
    WEB_RESEARCH = "web_research"
    SYSTEM_EXEC = "system_exec"
    COMMUNICATION = "communication"
    DATA_ANALYSIS = "data_analysis"


class ExecutionTier(int, Enum):
    TIER_1_INPROCESS = 1    # Fast in-process computation (TimesFM, math, numpy, indicator formulas)
    TIER_2_HOST_KERNEL = 2  # Guarded subprocess execution on host OS (NT-guard + terminal guard)
    TIER_3_CONTAINER = 3    # Isolated Docker/OCI container execution


@dataclass
class ToolParameter:
    name: str
    type_name: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum_values: Optional[List[str]] = None

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert parameter to standard JSON Schema attribute format."""
        schema_type = "string"
        t = self.type_name.lower()
        if "dict" in t or "mapping" in t or "object" in t:
            schema_type = "object"
        elif "list" in t or "sequence" in t or "set" in t or "array" in t:
            schema_type = "array"
        elif "int" in t:
            schema_type = "integer"
        elif "float" in t or "number" in t or "decimal" in t:
            schema_type = "number"
        elif "bool" in t:
            schema_type = "boolean"

        res: Dict[str, Any] = {
            "type": schema_type,
            "description": self.description,
        }
        if schema_type == "array":
            item_type = "string"
            if "int" in t:
                item_type = "integer"
            elif "float" in t or "number" in t:
                item_type = "number"
            elif "bool" in t:
                item_type = "boolean"
            elif "dict" in t or "object" in t:
                item_type = "object"
            res["items"] = {"type": item_type}
        elif schema_type == "object":
            res.setdefault("additionalProperties", True)

        if self.enum_values:
            res["enum"] = self.enum_values
        if self.default is not None:
            res["default"] = self.default
        return res


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)
    category: ToolCategory = ToolCategory.CORE
    tier: ExecutionTier = ExecutionTier.TIER_1_INPROCESS
    has_side_effects: bool = False
    is_model_tool: bool = True
    timeout_seconds: float = 30.0
    handler: Optional[Callable[..., Any]] = None

    def to_openai_schema(self) -> Dict[str, Any]:
        """Export tool definition to standard OpenAI/Anthropic/Gemini function calling schema."""
        properties: Dict[str, Any] = {}
        required_fields: List[str] = []

        for p_name, param in self.parameters.items():
            properties[p_name] = param.to_json_schema()
            if param.required:
                required_fields.append(p_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                },
            },
        }
