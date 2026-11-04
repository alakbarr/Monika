# ==============================================================================
# File: infrastructure/providers/gemini_protocol.py
# ==============================================================================

"""
Gemini Protocol, Schema Sanitization, and Response Liveness Checkers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from monika.infrastructure.llm.rate_limiting.streaming import StreamResult

logger = logging.getLogger("TradingAgent.GeminiProvider")


def _gemini_stream_parser(chunk: dict, result: StreamResult) -> bool:
    if not isinstance(chunk, dict):
        return False
    candidates = chunk.get("candidates", [])
    if candidates:
        cand = candidates[0]
        content = cand.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            if part.get("thought") is True:
                result.thinking_text += part.get("text", "")
                ts = part.get("thoughtSignature") or part.get("thought_signature")
                if ts and not getattr(result, "thought_signature", None):
                    setattr(result, "thought_signature", ts)
            elif "text" in part:
                result.text += part.get("text", "")
            elif "functionCall" in part:
                fc = part["functionCall"]
                ts = part.get("thoughtSignature") or part.get("thought_signature") or fc.get("id")
                result.tool_calls.append(
                    {"name": fc.get("name", ""), "args": fc.get("args", {}), "thoughtSignature": ts}
                )
        finish = cand.get("finishReason", "")
        if finish:
            result.finish_reason = finish

    if "usageMetadata" in chunk:
        result.usage = chunk["usageMetadata"]

    return bool(result.finish_reason)


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return schema

    from monika.infrastructure.providers.schema_normalizer import inline_json_refs

    schema = inline_json_refs(schema)
    if not isinstance(schema, dict):
        return schema

    sanitized = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema"):
            continue
        if k == "allOf" and isinstance(v, list):
            merged_properties = {}
            merged_required = set()
            for item in v:
                if isinstance(item, dict):
                    s_item = _sanitize_schema_for_gemini(item)
                    merged_properties.update(s_item.get("properties", {}))
                    merged_required.update(s_item.get("required", []))
            sanitized["type"] = "OBJECT"
            if merged_properties:
                sanitized["properties"] = merged_properties
            if merged_required:
                sanitized["required"] = sorted(merged_required)
            continue
        if k in ("anyOf", "oneOf") and isinstance(v, list):
            non_null_items = [
                item for item in v if isinstance(item, dict) and str(item.get("type", "")).lower() != "null"
            ]
            has_null = any(isinstance(item, dict) and str(item.get("type", "")).lower() == "null" for item in v)
            if len(non_null_items) == 1:
                inner = _sanitize_schema_for_gemini(non_null_items[0])
                for ik, iv in inner.items():
                    sanitized[ik] = iv
                if has_null:
                    sanitized["nullable"] = True
                continue
            elif len(non_null_items) > 1:
                sanitized["type"] = "STRING"
                types_str = ", ".join(str(it.get("type", "object")) for it in non_null_items)
                sanitized["description"] = (schema.get("description", "") + f" (Accepted types: {types_str})").strip()
                if has_null:
                    sanitized["nullable"] = True
                continue
        if k == "type" and isinstance(v, list):
            valid_types = [t for t in v if t != "null"]
            sanitized[k] = valid_types[0].upper() if valid_types else "STRING"
            if "null" in v:
                sanitized["nullable"] = True
            continue
        if k == "type" and isinstance(v, str):
            if "enum" in schema:
                sanitized[k] = "STRING"
            else:
                sanitized[k] = v.upper()
            continue
        if k == "enum" and isinstance(v, list):
            sanitized[k] = [str(x) for x in v]
            if "type" in sanitized:
                sanitized["type"] = "STRING"
            continue

        if isinstance(v, dict):
            sanitized[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            sanitized[k] = [_sanitize_schema_for_gemini(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v

    return sanitized


GEMINI_MODEL_ALIASES = {
    # Safe Gemini 3.x & 4.x Models (Active)
    "gemini-4-argon": "gemini-4-argon",
    "gemini-4": "gemini-4-argon",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.6-flash": "gemini-3.6-flash",
    "gemini-3.7-flash": "gemini-3.7-flash",
    "gemini-3.8-flash": "gemini-3.8-flash",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini-2.5-pro": "gemini-3.1-pro-preview",
    "gemini-1.5-pro": "gemini-3.1-pro-preview",
    "gemini-3-pro": "gemini-3.1-pro-preview",
    # Live & Audio Models
    "gemini-3.8-live": "gemini-3.8-live",
    "gemini-3.8-live-extended-thinking": "gemini-3.8-live-extended-thinking",
    "gemini-3.5-transcribe-live": "gemini-3.5-transcribe-live",
    "gemini-3-flash-live": "gemini-3-flash-live",
}

GEMINI_THINKING_LEVEL_MAP = {
    "none": "MINIMAL",
    "minimal": "MINIMAL",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "xhigh": "HIGH",
    "max": "HIGH",
}


def _check_gemini_block(data: Any) -> Optional[str]:
    """Return block reason if response was blocked or empty, None if OK."""
    if not isinstance(data, dict):
        return "invalid_response_format"

    pf = data.get("promptFeedback", {})
    block_reason = pf.get("blockReason")
    if block_reason:
        return f"prompt_blocked:{block_reason}"

    candidates = data.get("candidates", [])
    if not candidates:
        return "empty_candidates"

    finish = candidates[0].get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "MALICIOUS"):
        return f"candidate_blocked:{finish}"

    return None


__all__ = [
    "GEMINI_MODEL_ALIASES",
    "GEMINI_THINKING_LEVEL_MAP",
    "_check_gemini_block",
    "_gemini_stream_parser",
    "_sanitize_schema_for_gemini",
]
