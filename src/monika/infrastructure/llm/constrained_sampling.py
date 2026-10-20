"""
Constrained Sampling Support — grammar-based structured output for local & remote providers.

Architecture preparation for Ollama/vLLM/OpenAI/Gemini providers supporting JSON schema
and grammar constraints.
Normalizes JSON schemas for constrained decoding.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.ConstrainedSampling")


@dataclass
class ConstrainedSamplingConfig:
    """Configuration for grammar-constrained LLM output generation."""

    json_schema: Optional[Dict[str, Any]] = None  # JSON Schema for structured output
    lark_grammar: Optional[str] = None  # Lark grammar string
    regex_pattern: Optional[str] = None  # Regex constraint pattern
    strict: bool = True  # Enforce additionalProperties: false


UNSUPPORTED_STRICT_SCHEMA_KEYS = frozenset(
    {
        "$ref",
        "$defs",
        "definitions",
        "oneOf",
        "allOf",
        "not",
        "patternProperties",
        "additionalItems",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


def can_use_strict_schema(schema: Dict[str, Any]) -> bool:
    """Recursively checks if a schema contains unsupported keywords for strict mode."""
    if not isinstance(schema, dict):
        return True

    for k in schema.keys():
        if k in UNSUPPORTED_STRICT_SCHEMA_KEYS:
            return False

    props = schema.get("properties")
    if isinstance(props, dict):
        for p in props.values():
            if isinstance(p, dict) and not can_use_strict_schema(p):
                return False

    items = schema.get("items")
    if isinstance(items, dict):
        if not can_use_strict_schema(items):
            return False
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and not can_use_strict_schema(item):
                return False

    for combo in ("anyOf", "oneOf", "allOf"):
        arr = schema.get(combo)
        if isinstance(arr, list):
            for sub in arr:
                if isinstance(sub, dict) and not can_use_strict_schema(sub):
                    return False

    return True


def make_strict_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JSON Schema into strict mode subset for constrained sampling.

    Strict-schema normalization rules:
    - Sets additionalProperties: false recursively on objects
    - Expands required array to include all declared properties
    - For any property key not in original_required, wraps in nullable form (anyOf with type: null)
      and strips default to ensure strict mode compliance on omitted optional fields
    - Normalizes nested objects and arrays
    """
    if not isinstance(schema, dict):
        return schema

    result = dict(schema)

    # Recursive processing for object types
    if result.get("type") == "object" and "properties" in result:
        result["additionalProperties"] = False
        props = dict(result.get("properties", {}))

        has_explicit_required = "required" in result
        original_required = set(result.get("required") or []) if has_explicit_required else set(props.keys())

        result["required"] = list(props.keys())

        for key, prop_schema in props.items():
            strict_prop = make_strict_json_schema(prop_schema) if isinstance(prop_schema, dict) else prop_schema
            if key not in original_required:
                if isinstance(strict_prop, dict):
                    prop_clean = dict(strict_prop)
                    prop_clean.pop("default", None)
                    is_nullable = False
                    if prop_clean.get("type") == "null":
                        is_nullable = True
                    elif isinstance(prop_clean.get("type"), list) and "null" in prop_clean["type"]:
                        is_nullable = True
                    elif "anyOf" in prop_clean and any(
                        isinstance(sub, dict) and sub.get("type") == "null" for sub in prop_clean["anyOf"]
                    ):
                        is_nullable = True

                    if not is_nullable:
                        props[key] = {"anyOf": [prop_clean, {"type": "null"}]}
                    else:
                        props[key] = prop_clean
                else:
                    props[key] = strict_prop
            else:
                props[key] = strict_prop

        result["properties"] = props

    # Process array items
    if result.get("type") == "array" and "items" in result:
        result["items"] = make_strict_json_schema(result["items"])

    # Process anyOf/oneOf/allOf
    for combo_key in ("anyOf", "oneOf", "allOf"):
        if combo_key in result and isinstance(result[combo_key], list):
            result[combo_key] = [make_strict_json_schema(s) for s in result[combo_key]]

    return result


def resolve_grammar_for_provider(
    config: ConstrainedSamplingConfig,
    provider: str,
) -> Optional[Dict[str, Any]]:
    """Resolve constrained sampling config to provider-specific request parameters.

    Returns parameter dictionary to merge into LLM request kwargs, or None if unsupported.
    """
    prov = (provider or "").lower()
    if not config.json_schema:
        return None

    strict_schema = make_strict_json_schema(config.json_schema) if config.strict else config.json_schema

    if "ollama" in prov:
        return {"format": strict_schema}
    elif "openai" in prov or "openrouter" in prov or "deepseek" in prov or "groq" in prov:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": config.strict,
                    "schema": strict_schema,
                },
            }
        }
    elif "gemini" in prov:
        return {
            "responseMimeType": "application/json",
            "responseSchema": config.json_schema,
        }

    return None
