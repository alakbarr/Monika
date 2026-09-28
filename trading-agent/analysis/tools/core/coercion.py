# ==============================================================================
# File: analysis/tools/core/coercion.py
# ==============================================================================

"""
Robust Parameter Coercion for LLM Function Calling.
Institutional-grade tool orchestration architecture.

Handles common LLM formatting inconsistencies: stringified JSON dictionaries,
boolean string representations ('true'/'false'), integer-from-float conversions,
and comma-separated string lists.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from analysis.tools.core.definition import ToolParameter

logger = logging.getLogger("TradingAgent.Analysis.Tools.Coercion")


def coerce_value(val: Any, param: ToolParameter) -> Any:
    """Coerces a single parameter value according to its ToolParameter specification."""
    if val is None:
        return param.default

    t = param.type_name.lower()

    # Dictionary / Object coercion
    if "dict" in t or "mapping" in t:
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            trimmed = val.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    return json.loads(trimmed)
                except Exception:
                    pass
        return val

    # List / Array coercion
    if "list" in t or "sequence" in t or "set" in t or "array" in t:
        if isinstance(val, list):
            return val
        if isinstance(val, (set, tuple)):
            return list(val)
        if isinstance(val, str):
            trimmed = val.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                try:
                    return json.loads(trimmed)
                except Exception:
                    pass
            # Split comma separated tokens
            return [x.strip() for x in trimmed.split(",") if x.strip()]
        return [val]

    # Boolean coercion
    if "bool" in t:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("true", "1", "yes", "y", "t", "on"):
                return True
            if s in ("false", "0", "no", "n", "f", "off"):
                return False
            if param.default is not None:
                return param.default
            return False
        return bool(val)

    # Integer coercion
    if "int" in t:
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            try:
                # Handle "10.0" -> 10
                return int(float(val.strip()))
            except ValueError:
                pass
        return val

    # Float/Number coercion
    if "float" in t or "number" in t or "decimal" in t:
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val.strip())
            except ValueError:
                pass
        return val

    # String coercion
    if "str" in t:
        if isinstance(val, str):
            return val
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    return val


def coerce_arguments(
    params_spec: Dict[str, ToolParameter],
    raw_args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Coerces raw arguments dictionary according to the ToolParameters specifications.
    Supplies default values for missing optional parameters.
    """
    coerced: Dict[str, Any] = {}

    for name, param in params_spec.items():
        if name in raw_args:
            coerced[name] = coerce_value(raw_args[name], param)
        elif param.default is not None or not param.required:
            coerced[name] = param.default
        else:
            # Missing required parameter: keep None or let downstream handler validate
            coerced[name] = None

    # Include extra kwargs passed by LLM that aren't in spec
    for k, v in raw_args.items():
        if k not in coerced:
            coerced[k] = v

    return coerced
