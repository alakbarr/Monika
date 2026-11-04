# ==============================================================================
# File: infrastructure/providers/openai_protocol.py
# ==============================================================================

"""
OpenAI Protocol, Schema Canonicalization, and Text Extraction Helpers.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _extract_message_text(choice) -> str:
    """
    Universal robust text extraction across standard OpenAI, OpenRouter, and reasoning models.
    Checks:
    1. choice.message.content
    2. choice.message.reasoning / reasoning_content
    3. choice.message.model_extra (Pydantic v2 OpenRouter extra fields: reasoning, reasoning_content, thought)
    4. choice.message.model_dump()
    """
    if not choice or not hasattr(choice, "message"):
        return ""
    msg = choice.message

    # 1. Standard message content
    content = getattr(msg, "content", None)
    if content is not None and str(content).strip():
        text = str(content)
        if any(tag in text.lower() for tag in ("<think>", "<thought>", "<reasoning>", "<scratchpad>")):
            from monika.infrastructure.providers.streaming_think_scrubber import StreamingThinkScrubber

            clean_text, _ = StreamingThinkScrubber.scrub_text(text)
            if clean_text.strip():
                return clean_text.strip()
        return text

    # 2. Direct reasoning attributes
    reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
    if reasoning is not None and str(reasoning).strip():
        return str(reasoning)

    # 3. Pydantic v2 model_extra dictionary
    model_extra = getattr(msg, "model_extra", None) or {}
    if isinstance(model_extra, dict):
        for key in ["reasoning", "reasoning_content", "thought", "reasoning_text"]:
            val = model_extra.get(key)
            if val is not None and str(val).strip():
                return str(val)

    # 4. Model dump fallback
    if hasattr(msg, "model_dump"):
        try:
            dump = msg.model_dump()
            if isinstance(dump, dict):
                for key in ["content", "reasoning", "reasoning_content", "thought"]:
                    val = dump.get(key)
                    if val is not None and str(val).strip():
                        return str(val)
        except Exception:
            pass

    return ""


def _canonicalize_schema(schema: Any) -> Any:
    """Recursively sort dictionary keys for 100% deterministic JSON serialization and KV-cache prefix stability."""
    if isinstance(schema, dict):
        return {k: _canonicalize_schema(v) for k, v in sorted(schema.items())}
    if isinstance(schema, list):
        return [_canonicalize_schema(item) for item in schema]
    return schema


def sanitize_tool_parameters_schema(schema_dict: Any) -> Any:
    """
    Sanitize JSON Schema for OpenAI / OpenRouter function calling parameters.
    Guarantees 100% compliance with JSON Schema Draft-07 function calling specifications:
    1. Removes any 'default' field whose value is None / null (avoids Azure/OpenAI 400 'None is not valid under any of the given schemas').
    2. Simplifies nullable type arrays like ["string", "null"] to "string" or standard types (avoids Meta 400 'null is not valid under any of the schemas').
    3. Simplifies anyOf with null branches: anyOf: [T, {"type": "null"}] -> T.
    4. Ensures array schemas always contain an 'items' specification.
    5. Ensures object schemas always have 'properties' dict.
    6. Recursively cleans all nested objects, properties, and definitions.
    """
    if not isinstance(schema_dict, dict):
        return schema_dict

    import copy

    s = copy.deepcopy(schema_dict)

    def _clean(d: Any) -> Any:
        if isinstance(d, dict):
            # 1. Remove default if None
            if "default" in d and d["default"] is None:
                del d["default"]

            # 2. Simplify type: [T, "null"] -> T
            if "type" in d and isinstance(d["type"], list):
                non_null_types = [t for t in d["type"] if t != "null"]
                if len(non_null_types) == 1:
                    d["type"] = non_null_types[0]
                elif len(non_null_types) > 1:
                    d["type"] = non_null_types[0]
                else:
                    d["type"] = "string"

            # 3. Simplify anyOf with null branches
            if "anyOf" in d and isinstance(d["anyOf"], list):
                non_null_branches = [
                    b
                    for b in d["anyOf"]
                    if not (isinstance(b, dict) and (b.get("type") == "null" or b == {"type": "null"}))
                ]
                if len(non_null_branches) == 1 and isinstance(non_null_branches[0], dict):
                    cleaned_branch = _clean(non_null_branches[0])
                    del d["anyOf"]
                    d.update(cleaned_branch)
                elif len(non_null_branches) > 1:
                    d["anyOf"] = [_clean(b) for b in non_null_branches]
                else:
                    del d["anyOf"]
                    d["type"] = "string"

            # 4. Guarantee array has items
            if d.get("type") == "array" and "items" not in d:
                d["items"] = {"type": "string"}

            # 5. Guarantee object has properties
            if d.get("type") == "object" and "properties" not in d:
                d["properties"] = {}

            # Recurse for all keys
            for k, v in list(d.items()):
                d[k] = _clean(v)
            return d
        elif isinstance(d, list):
            return [_clean(item) for item in d]
        return d

    return _clean(s)


def make_openai_strict_schema(schema_dict: dict) -> dict:
    """
    Transforms standard Pydantic JSON schema into OpenAI strict: true compliant schema.
    Requirements for OpenAI Structured Outputs (strict: true):
    1. 'additionalProperties': False on all object schemas.
    2. Every property in 'properties' MUST be listed in 'required'.
    3. Fields optional in domain logic are made nullable via anyOf: [orig, {"type": "null"}].
    """
    import copy

    if not isinstance(schema_dict, dict):
        return schema_dict

    s = copy.deepcopy(schema_dict)

    def _patch_object(obj: dict):
        if not isinstance(obj, dict):
            return

        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            props = obj.get("properties", {})
            orig_req = set(obj.get("required", []))
            obj["required"] = list(props.keys())

            for key, prop in props.items():
                if key not in orig_req:
                    if "anyOf" in prop:
                        has_null = any(x.get("type") == "null" for x in prop["anyOf"] if isinstance(x, dict))
                        if not has_null:
                            prop["anyOf"].append({"type": "null"})
                    elif "type" in prop:
                        orig_type = prop["type"]
                        if isinstance(orig_type, str):
                            if orig_type != "null":
                                prop["anyOf"] = [{"type": orig_type}, {"type": "null"}]
                                del prop["type"]
                        elif isinstance(orig_type, list):
                            if "null" not in orig_type:
                                prop["type"] = orig_type + ["null"]
                    else:
                        prop["anyOf"] = [copy.deepcopy(prop), {"type": "null"}]

        for v in obj.values():
            if isinstance(v, dict):
                _patch_object(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _patch_object(item)

    _patch_object(s)
    return s


__all__ = [
    "_canonicalize_schema",
    "_extract_message_text",
    "make_openai_strict_schema",
    "sanitize_tool_parameters_schema",
]
