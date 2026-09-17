"""
Constrained Sampling Support — grammar-based structured output for local & remote providers.

Architecture preparation for Ollama/vLLM/OpenAI/Gemini providers supporting JSON schema
and grammar constraints.
Adopted from Pi's constrained-sampling.ts pattern.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger("TradingAgent.ConstrainedSampling")


@dataclass
class ConstrainedSamplingConfig:
    """Configuration for grammar-constrained LLM output generation."""
    json_schema: Optional[Dict[str, Any]] = None   # JSON Schema for structured output
    lark_grammar: Optional[str] = None              # Lark grammar string
    regex_pattern: Optional[str] = None             # Regex constraint pattern
    strict: bool = True                             # Enforce additionalProperties: false


def make_strict_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JSON Schema into strict mode subset for constrained sampling.

    Adopted from Pi's makeStrictJsonSchema() pattern:
    - Sets additionalProperties: false recursively on objects
    - Expands required array to include all declared properties
    - Normalizes nested objects and arrays
    """
    if not isinstance(schema, dict):
        return schema

    result = dict(schema)

    # Recursive processing for object types
    if result.get("type") == "object" and "properties" in result:
        result["additionalProperties"] = False
        props = dict(result.get("properties", {}))
        result["required"] = list(props.keys())
        for key, prop_schema in props.items():
            props[key] = make_strict_json_schema(prop_schema)
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
