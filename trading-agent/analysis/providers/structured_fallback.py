# ==============================================================================
# File: analysis/providers/structured_fallback.py
# ==============================================================================

"""
Resilient Structured Output Fallback Engine.
Attempts native structured JSON generation first; gracefully falls back to
free-text generation + resilient JSON extraction when schema constraints fail.
"""

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, List, Type, cast
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("TradingAgent.Providers.StructuredFallback")

from analysis.providers.base_provider import extract_and_parse_json


@dataclass
class StructuredOutputResult:
    """Telemetry-rich container for structured output parsing and degradation status."""
    data: Dict[str, Any]
    success: bool
    degradation_stage: str  # "native" | "repaired_json" | "regex_field_recovery" | "default_fallback" | "failed"
    error: Optional[str] = None
    extracted_fields: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    model_instance: Optional[Any] = None


def extract_key_values_by_regex(text: str, fields: List[str]) -> Dict[str, Any]:
    """
    Pass 2 fallback: Extract key-value pairs from free-text LLM responses when JSON decoding fails.
    Matches quoted or unquoted keys with string, numeric, boolean, or array literals.
    Supports separators ':', '=', or 'is'.
    """
    if not text or not fields:
        return {}

    extracted = {}
    sep = r'(?::|=|is)\s*'
    for f in fields:
        # Pattern 1: string value -> "key": "value" or key is 'value'
        str_match = re.search(rf'["\']?\b{re.escape(f)}\b["\']?\s*{sep}["\']([^"\'\r\n]+)["\']', text, re.IGNORECASE)
        if str_match:
            extracted[f] = str_match.group(1).strip()
            continue

        # Pattern 2: number/float value -> "key": 123.45 or key is 0.85
        num_match = re.search(rf'["\']?\b{re.escape(f)}\b["\']?\s*{sep}(-?[0-9]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
        if num_match:
            raw_num = num_match.group(1)
            extracted[f] = float(raw_num) if "." in raw_num else int(raw_num)
            continue

        # Pattern 3: boolean value -> "key": true / false or key is true
        bool_match = re.search(rf'["\']?\b{re.escape(f)}\b["\']?\s*{sep}(true|false|yes|no)\b', text, re.IGNORECASE)
        if bool_match:
            extracted[f] = bool_match.group(1).lower() in ("true", "yes")
            continue

        # Pattern 4: array of strings/numbers -> "key": ["a", "b"]
        arr_match = re.search(rf'["\']?\b{re.escape(f)}\b["\']?\s*{sep}\[([^\]]+)\]', text, re.IGNORECASE)
        if arr_match:
            items = [item.strip().strip('"\'') for item in arr_match.group(1).split(",") if item.strip()]
            extracted[f] = items
            continue

    return extracted


def parse_structured_output(
    text: str,
    pydantic_model: Optional[Type[BaseModel]] = None,
    required_fields: Optional[List[str]] = None,
    defaults: Optional[Dict[str, Any]] = None,
) -> StructuredOutputResult:
    """
    Two-pass resilient structured output parser with telemetry.
    Pass 1: Direct JSON parsing & model validation.
    Pass 2: Fallback extraction (repaired JSON -> regex key-value extraction -> defaults).
    """
    if not text or not isinstance(text, str):
        return StructuredOutputResult(
            data=defaults or {},
            success=False,
            degradation_stage="failed",
            error="Empty or non-string input",
            missing_fields=list((defaults or {}).keys()),
        )

    # Infer fields from Pydantic model if provided
    expected_fields = list(required_fields or [])
    if pydantic_model and hasattr(pydantic_model, "model_fields"):
        expected_fields = list(set(expected_fields) | set(pydantic_model.model_fields.keys()))

    clean_text = text.strip()

    # --- Pass 1: Direct JSON parse ---
    try:
        raw_dict = json.loads(clean_text)
        if isinstance(raw_dict, dict):
            if pydantic_model:
                try:
                    instance = pydantic_model.model_validate(raw_dict)
                    return StructuredOutputResult(
                        data=raw_dict,
                        success=True,
                        degradation_stage="native",
                        extracted_fields=list(raw_dict.keys()),
                        model_instance=instance,
                    )
                except ValidationError as ve:
                    logger.debug(f"[StructuredParser] Native JSON failed Pydantic validation: {ve}")
            else:
                return StructuredOutputResult(
                    data=raw_dict,
                    success=True,
                    degradation_stage="native",
                    extracted_fields=list(raw_dict.keys()),
                )
    except Exception:
        pass

    # --- Pass 2: Repaired JSON extraction ---
    repaired_dict = extract_and_parse_json(clean_text)
    if isinstance(repaired_dict, dict) and repaired_dict:
        # Check Pydantic validation if model provided
        if pydantic_model:
            try:
                instance = pydantic_model.model_validate(repaired_dict)
                return StructuredOutputResult(
                    data=repaired_dict,
                    success=True,
                    degradation_stage="repaired_json",
                    extracted_fields=list(repaired_dict.keys()),
                    model_instance=instance,
                )
            except ValidationError:
                # Merge with defaults or attempt regex completion
                pass
        else:
            return StructuredOutputResult(
                data=repaired_dict,
                success=True,
                degradation_stage="repaired_json",
                extracted_fields=list(repaired_dict.keys()),
            )

    # --- Pass 3: Regex Key-Value Extraction ---
    regex_extracted = extract_key_values_by_regex(clean_text, expected_fields)
    combined = dict(repaired_dict or {})
    for k, v in regex_extracted.items():
        if k not in combined or combined[k] is None:
            combined[k] = v

    if combined and any(f in combined for f in expected_fields):
        # Fill missing with defaults if available
        missing = [f for f in expected_fields if f not in combined]
        if defaults:
            for k, v in defaults.items():
                if k not in combined:
                    combined[k] = v

        model_inst = None
        if pydantic_model:
            try:
                model_inst = pydantic_model.model_validate(combined)
            except ValidationError:
                pass

        return StructuredOutputResult(
            data=combined,
            success=True,
            degradation_stage="regex_field_recovery",
            extracted_fields=list(combined.keys()),
            missing_fields=missing,
            model_instance=model_inst,
        )

    # --- Pass 4: Default Fallback ---
    if defaults:
        return StructuredOutputResult(
            data=dict(defaults),
            success=False,
            degradation_stage="default_fallback",
            error="Parsed zero fields from LLM response; applied default fallback.",
            missing_fields=expected_fields,
        )

    return StructuredOutputResult(
        data={"raw_output": clean_text},
        success=False,
        degradation_stage="failed",
        error="Unable to extract structured data from response.",
        missing_fields=expected_fields,
    )


async def invoke_structured_or_freetext(
    client: Any,
    prompt: str,
    system_prompt: str,
    schema: Optional[Dict[str, Any]] = None,
    pydantic_model: Optional[Type[BaseModel]] = None,
    required_fields: Optional[List[str]] = None,
    defaults: Optional[Dict[str, Any]] = None,
    task_role: str = "",
) -> Dict[str, Any]:
    """
    Attempts structured output generation via client.classify_json first.
    If that fails or client does not support structured output, falls back to
    client.generate() and two-pass resilient extraction.
    """
    # 1. Try structured output if method exists
    classify_fn: Any = getattr(client, "classify_json", None)
    if callable(classify_fn):
        try:
            result = await cast(Any, classify_fn)(prompt, system_prompt, schema=schema)
            if isinstance(result, dict) and result:
                return result
        except Exception as struct_err:
            logger.warning(
                f"[StructuredFallback] classify_json failed for role '{task_role}': {struct_err}. "
                f"Gracefully degrading to free-text generation..."
            )

    # 2. Fallback to free-text generation + resilient parser
    try:
        generate_fn: Any = getattr(client, "generate", None)
        if callable(generate_fn):
            combined_prompt = f"{system_prompt}\n\n{prompt}\n\nIMPORTANT: Respond ONLY with a valid JSON object."
            raw_output = await cast(Any, generate_fn)(combined_prompt)
            if hasattr(raw_output, "text"):
                raw_text = raw_output.text
            elif isinstance(raw_output, dict):
                raw_text = raw_output.get("text", "")
            else:
                raw_text = str(raw_output)

            res = parse_structured_output(
                raw_text,
                pydantic_model=pydantic_model,
                required_fields=required_fields,
                defaults=defaults,
            )
            return res.data
    except Exception as gen_err:
        logger.error(f"[StructuredFallback] Free-text fallback failed for role '{task_role}': {gen_err}")
        if defaults:
            return dict(defaults)
        return {"error": str(gen_err)}

    return {"error": "No viable generation method found on client"}
