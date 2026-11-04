# ==============================================================================
# File: application/analysis/schemas/strict_schema.py
# ==============================================================================

"""
OpenAI Strict Mode Schema Converters and Pydantic Ref-inliners.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger("TradingAgent.Schemas")


def make_openai_strict_schema(schema_dict: dict) -> dict:
    """
    Transforms standard Pydantic JSON schema into OpenAI strict: true compliant schema.
    Requirements for OpenAI Structured Outputs (strict: true):
    1. 'additionalProperties': False on all object schemas.
    2. Every property in 'properties' MUST be listed in 'required'.
    3. Fields optional in domain logic are made nullable via anyOf: [orig, {"type": "null"}].
    """
    if not isinstance(schema_dict, dict):
        return schema_dict

    s = copy.deepcopy(schema_dict)

    def _patch_object(obj: dict):
        if not isinstance(obj, dict):
            return

        obj.pop("default", None)

        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            props = obj.get("properties", {})
            orig_req = set(obj.get("required", []))
            obj["required"] = list(props.keys())

            for key, prop in props.items():
                if key not in orig_req:
                    if "anyOf" in prop:
                        if not any(item.get("type") == "null" for item in prop["anyOf"]):
                            prop["anyOf"].append({"type": "null"})
                    elif "type" in prop:
                        t = prop["type"]
                        if isinstance(t, str) and t != "null":
                            prop["anyOf"] = [{"type": t}, {"type": "null"}]
                            del prop["type"]
                        elif isinstance(t, list) and "null" not in t:
                            t.append("null")
                    elif "$ref" in prop:
                        ref = prop.pop("$ref")
                        prop["anyOf"] = [{"$ref": ref}, {"type": "null"}]
                _patch_object(prop)

        for k, v in list(obj.items()):
            if k == "properties":
                continue
            if isinstance(v, dict):
                _patch_object(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _patch_object(item)

    _patch_object(s)
    return s


def _inline_refs(schema: Any, defs: Optional[dict[str, Any]] = None) -> Any:
    """Recursively replaces $ref with actual schema definitions to produce
    a flat JSON schema compatible with raw tool execution payloads.
    Also simplifies anyOf null structures common in Pydantic v2 Optionals.
    """
    if defs is None:
        if isinstance(schema, dict):
            raw_defs = schema.get("$defs")
            defs_map: dict[str, Any] = raw_defs if isinstance(raw_defs, dict) else {}
            schema = {k: v for k, v in schema.items() if k != "$defs"}
        else:
            defs_map = {}
    else:
        defs_map = defs

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            if ref_name in defs_map:
                resolved = _inline_refs(dict(defs_map[ref_name]), defs_map)
                extra = {k: v for k, v in schema.items() if k != "$ref"}
                if extra:
                    resolved.update(_inline_refs(extra, defs_map))
                return resolved
            return schema

        # Simplify anyOf with null (Pydantic v2 Optionals)
        if "anyOf" in schema:
            any_of = schema["anyOf"]
            null_branches = [s for s in any_of if isinstance(s, dict) and s.get("type") == "null"]
            non_null_branches = [s for s in any_of if not (isinstance(s, dict) and s.get("type") == "null")]

            if null_branches and len(non_null_branches) == 1:
                non_null_schema = non_null_branches[0]
                merged = {k: v for k, v in schema.items() if k != "anyOf"}
                resolved_non_null = _inline_refs(non_null_schema, defs_map)
                if isinstance(resolved_non_null, dict):
                    merged.update(resolved_non_null)
                if "enum" not in merged and "type" in merged:
                    if isinstance(merged["type"], str):
                        merged["type"] = [merged["type"], "null"]
                    elif isinstance(merged["type"], list) and "null" not in merged["type"]:
                        merged["type"].append("null")
                elif "type" not in merged:
                    merged["anyOf"] = [resolved_non_null, {"type": "null"}]
                if "default" in merged and merged["default"] is None:
                    del merged["default"]
                return merged
            elif null_branches and len(non_null_branches) > 1:
                merged = {k: v for k, v in schema.items()}
                merged["anyOf"] = [_inline_refs(s, defs_map) for s in any_of]
                if "default" in merged and merged["default"] is None:
                    del merged["default"]
                return merged

        res = {}
        for k, v in schema.items():
            if k == "default" and v is None:
                continue
            res[k] = _inline_refs(v, defs_map)
        return res

    elif isinstance(schema, list):
        return [_inline_refs(item, defs_map) for item in schema]

    return schema


def get_tool_schema(pydantic_model: type[BaseModel]) -> dict:
    """Generate a flattened JSON schema for a tool definition."""
    schema = pydantic_model.model_json_schema()
    return _inline_refs(schema)
