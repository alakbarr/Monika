"""
File: src/monika/application/agent/harness/pseudo_tool_parser.py

Extracts pseudo-tool invocations from plain-text model responses.
Captures tool calls emitted as:
1. XML/Hermes format: <tool_call name="...">...</tool_call> or <tool_call>{"name": ..., "arguments": ...}</tool_call>
2. Markdown JSON code blocks: ```json {"name": "...", "parameters": ...} ```
3. Direct structured payload blocks matching mandatory tools (e.g. submit_asset_analysis with decision/rationale).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from monika.application.agent.harness.tool_repair import repair_tool_arguments

logger = logging.getLogger("TradingAgent.AgentHarness.PseudoToolParser")


def extract_pseudo_tool_calls(
    text: str,
    available_tool_names: Optional[Set[str]] = None,
    mandatory_tool: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract tool calls emitted inside text/markdown instead of native API tool blocks.

    Returns a list of normalized tool_use dictionaries:
        [{"type": "tool_use", "id": str, "name": str, "input": dict}]
    """
    if not text or not isinstance(text, str):
        return []

    cleaned_text = text.strip()
    if not cleaned_text:
        return []

    tools_found: List[Dict[str, Any]] = []
    avail = set(available_tool_names or [])
    call_idx = 0

    # 1. XML-style tool calls: <tool_call name="tool_name">...</tool_call>
    xml_named_pattern = re.compile(
        r'<tool_call\s+name=["\']([a-zA-Z0-9_-]+)["\']\s*>([\s\S]*?)</tool_call>',
        re.IGNORECASE,
    )
    for m in xml_named_pattern.finditer(cleaned_text):
        fn_name = m.group(1).strip()
        raw_body = m.group(2).strip()
        if avail and fn_name not in avail:
            continue
        parsed_args = repair_tool_arguments(raw_body)
        call_idx += 1
        tools_found.append(
            {
                "type": "tool_use",
                "id": f"call_pseudo_{fn_name}_{call_idx}",
                "name": fn_name,
                "input": parsed_args,
            }
        )

    if tools_found:
        return tools_found

    # 1b. Generic XML-style: <tool_call>{"name": ..., "arguments": ...}</tool_call>
    xml_generic_pattern = re.compile(r"<tool_call>([\s\S]*?)</tool_call>", re.IGNORECASE)
    for m in xml_generic_pattern.finditer(cleaned_text):
        raw_body = m.group(1).strip()
        parsed = repair_tool_arguments(raw_body)
        if isinstance(parsed, dict):
            fn_name = str(parsed.get("name") or parsed.get("tool") or "").strip()
            args = (
                parsed.get("arguments")
                or parsed.get("parameters")
                or parsed.get("input")
                or {k: v for k, v in parsed.items() if k not in ("name", "tool")}
            )
            if fn_name and (not avail or fn_name in avail):
                call_idx += 1
                tools_found.append(
                    {
                        "type": "tool_use",
                        "id": f"call_pseudo_{fn_name}_{call_idx}",
                        "name": fn_name,
                        "input": args if isinstance(args, dict) else repair_tool_arguments(args),
                    }
                )

    if tools_found:
        return tools_found

    # 2. Markdown code fences with JSON: ```json ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for m in fence_pattern.finditer(cleaned_text):
        body = m.group(1).strip()
        if not (body.startswith("{") and body.endswith("}")):
            continue
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = repair_tool_arguments(body)

        if not isinstance(parsed, dict) or not parsed:
            continue

        # Subcase 2a: Tool call wrapper object {"name": "xyz", "arguments": {...}}
        fn_name = str(parsed.get("name") or parsed.get("tool") or "").strip()
        if fn_name and (not avail or fn_name in avail):
            args = (
                parsed.get("arguments")
                or parsed.get("parameters")
                or parsed.get("input")
                or {k: v for k, v in parsed.items() if k not in ("name", "tool")}
            )
            call_idx += 1
            tools_found.append(
                {
                    "type": "tool_use",
                    "id": f"call_pseudo_{fn_name}_{call_idx}",
                    "name": fn_name,
                    "input": args if isinstance(args, dict) else repair_tool_arguments(args),
                }
            )
            continue

        # Subcase 2b: Direct payload matching mandatory tool (e.g. submit_asset_analysis)
        if mandatory_tool and (not avail or mandatory_tool in avail):
            if mandatory_tool == "submit_asset_analysis":
                decision_val = str(parsed.get("decision", "")).strip().lower()
                if decision_val in ("buy", "sell", "wait", "avoid") and ("rationale" in parsed or "symbol" in parsed):
                    call_idx += 1
                    tools_found.append(
                        {
                            "type": "tool_use",
                            "id": f"call_pseudo_{mandatory_tool}_{call_idx}",
                            "name": mandatory_tool,
                            "input": parsed,
                        }
                    )
            elif mandatory_tool == "submit_fundamental_brief":
                if "macro_narrative" in parsed or "risk_sentiment" in parsed or "currency_bias" in parsed:
                    call_idx += 1
                    tools_found.append(
                        {
                            "type": "tool_use",
                            "id": f"call_pseudo_{mandatory_tool}_{call_idx}",
                            "name": mandatory_tool,
                            "input": parsed,
                        }
                    )

    if tools_found:
        return tools_found

    # 3. Direct JSON root in text without code fences
    if cleaned_text.startswith("{") and cleaned_text.endswith("}"):
        try:
            parsed = json.loads(cleaned_text)
        except Exception:
            parsed = repair_tool_arguments(cleaned_text)

        if isinstance(parsed, dict) and parsed:
            fn_name = str(parsed.get("name") or parsed.get("tool") or "").strip()
            if fn_name and (not avail or fn_name in avail):
                args = (
                    parsed.get("arguments")
                    or parsed.get("parameters")
                    or parsed.get("input")
                    or {k: v for k, v in parsed.items() if k not in ("name", "tool")}
                )
                call_idx += 1
                return [
                    {
                        "type": "tool_use",
                        "id": f"call_pseudo_{fn_name}_{call_idx}",
                        "name": fn_name,
                        "input": args if isinstance(args, dict) else repair_tool_arguments(args),
                    }
                ]
            if mandatory_tool and (not avail or mandatory_tool in avail):
                if mandatory_tool == "submit_asset_analysis":
                    decision_val = str(parsed.get("decision", "")).strip().lower()
                    if decision_val in ("buy", "sell", "wait", "avoid") and (
                        "rationale" in parsed or "symbol" in parsed
                    ):
                        return [
                            {
                                "type": "tool_use",
                                "id": f"call_pseudo_{mandatory_tool}_1",
                                "name": mandatory_tool,
                                "input": parsed,
                            }
                        ]
                elif mandatory_tool == "submit_fundamental_brief":
                    if "macro_narrative" in parsed or "risk_sentiment" in parsed or "currency_bias" in parsed:
                        return [
                            {
                                "type": "tool_use",
                                "id": f"call_pseudo_{mandatory_tool}_1",
                                "name": mandatory_tool,
                                "input": parsed,
                            }
                        ]

    return []
