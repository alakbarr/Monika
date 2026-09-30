# ==============================================================================
# File: analysis/harness/tool_repair.py
# ==============================================================================

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.ToolRepair")

TOOL_NAME_ALIASES: Dict[str, str] = {
    "run_shell": "web_search",
    "search": "web_search",
    "search_web": "web_search",
    "google_search": "web_search",
    "fetch_price": "get_price_data",
    "get_prices": "get_price_data",
    "price_data": "get_price_data",
    "technical_analysis": "get_technical_analysis",
    "get_ta": "get_technical_analysis",
    "calculate_size": "calculate_position_size",
    "position_size": "calculate_position_size",
    "submit_analysis": "submit_asset_analysis",
    "submit_asset": "submit_asset_analysis",
    "submit_trade_analysis": "submit_asset_analysis",
    "submit_brief": "submit_fundamental_brief",
    "submit_fundamental": "submit_fundamental_brief",
    "market_snapshot": "get_verified_market_snapshot",
    "verified_snapshot": "get_verified_market_snapshot",
    "ground_truth_snapshot": "get_verified_market_snapshot",
    "get_calendar": "get_economic_calendar",
    "get_economic_calendars": "get_economic_calendar",
    "get_positions": "get_open_positions",
    "get_open_position": "get_open_positions",
    "write_scratchpad": "update_scratchpad",
    "read_scratchpad": "read_scratchpad",
}


def repair_tool_name(raw_name: str) -> str:
    """Auto-repair hallucinated, aliased, or namespaced tool names."""
    if not raw_name or not isinstance(raw_name, str):
        return ""

    clean = raw_name.strip().strip("\"'` ")
    if clean.endswith("()"):
        clean = clean[:-2].strip()

    # Strip prefixes like tools. functions. tool. fn.
    for ns in ("tools.", "functions.", "tool.", "fn.", "default.", "modules."):
        if clean.startswith(ns):
            clean = clean[len(ns):].strip()

    # Handle doubled prefixes e.g. submit_submit_
    for pfx in ("submit_", "get_", "load_", "calculate_"):
        double_pfx = pfx + pfx
        while clean.startswith(double_pfx):
            clean = clean[len(pfx):]

    # Check alias map
    if clean in TOOL_NAME_ALIASES:
        repaired = TOOL_NAME_ALIASES[clean]
        logger.info(f"Auto-repaired tool name: '{raw_name}' -> '{repaired}'")
        return repaired

    # Check registry aliases
    try:
        from analysis.tools.registry import default_tool_registry
        canonical = default_tool_registry.resolve_name(clean)
        if canonical != clean:
            logger.info(f"Registry resolved tool alias: '{clean}' -> '{canonical}'")
            return canonical
    except Exception:
        pass

    return clean


def _parse_xml_parameters(text: str) -> Optional[Dict[str, Any]]:
    """Parse XML parameter tags e.g. <parameter name="type">price_level</parameter> into a dict."""
    if not isinstance(text, str) or "<parameter" not in text:
        return None
    matches = re.findall(
        r'<parameter\s+name=["\']([^"\']+)["\']\s*>(.*?)(?:</parameter>|(?=<parameter)|$)',
        text,
        re.DOTALL
    )
    if matches:
        return {k.strip(): v.strip() for k, v in matches}
    return None


def repair_tool_arguments(args: Any) -> Dict[str, Any]:
    """Repair corrupted JSON arguments (trailing commas, python constants, single quotes, XML tags)."""
    if isinstance(args, dict):
        res = dict(args)
        for k, v in list(res.items()):
            if isinstance(v, str) and "<parameter" in v:
                xml_parsed = _parse_xml_parameters(v)
                if xml_parsed:
                    res[k] = xml_parsed
        return res

    if not args:
        return {}

    if not isinstance(args, str):
        try:
            return dict(args)
        except Exception:
            return {}

    args_str = args.strip()
    if not args_str:
        return {}

    # Check for pure XML parameter block first
    xml_dict = _parse_xml_parameters(args_str)
    if xml_dict:
        return xml_dict

    # Try standard parse first
    try:
        parsed = json.loads(args_str)
        if isinstance(parsed, dict):
            for k, v in list(parsed.items()):
                if isinstance(v, str) and "<parameter" in v:
                    xml_p = _parse_xml_parameters(v)
                    if xml_p:
                        parsed[k] = xml_p
            return parsed
        return parsed
    except json.JSONDecodeError:
        pass

    # Repair common LLM syntax defects:
    # 1. Trailing commas before closing braces/brackets
    cleaned = re.sub(r',\s*([}\]])', r'\1', args_str)

    # 2. Python booleans and None
    cleaned = re.sub(r'\bNone\b', 'null', cleaned)
    cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
    cleaned = re.sub(r'\bFalse\b', 'false', cleaned)

    # 3. Single quotes to double quotes
    if "'" in cleaned and '"' not in cleaned:
        cleaned = cleaned.replace("'", '"')

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            for k, v in list(parsed.items()):
                if isinstance(v, str) and "<parameter" in v:
                    xml_p = _parse_xml_parameters(v)
                    if xml_p:
                        parsed[k] = xml_p
            return parsed
        return parsed
    except json.JSONDecodeError:
        logger.warning(f"Failed to auto-repair JSON tool arguments: '{args_str[:120]}'")
        return {}


def coerce_tool_arguments(args: Dict[str, Any], schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Coerce stringified primitives, arrays, objects, and enums in tool arguments to match expected JSON schema types."""
    if not isinstance(args, dict) or not isinstance(schema, dict):
        return args

    props = schema.get("properties")
    if not isinstance(props, dict):
        return args

    # Inject defaults for missing required properties if defined in schema or well-known
    required_keys = schema.get("required", [])
    for req_key in required_keys:
        if req_key not in args and req_key in props:
            pdef = props[req_key]
            if isinstance(pdef, dict) and "default" in pdef:
                args[req_key] = pdef["default"]
            elif req_key == "timeframe":
                args["timeframe"] = "H1"

    for key, val in list(args.items()):
        if key not in props:
            continue
        pdef = props[key]
        if not isinstance(pdef, dict):
            continue

        raw_type = pdef.get("type")
        expected_types = [raw_type] if isinstance(raw_type, str) else (raw_type if isinstance(raw_type, list) else [])

        # Enum coercion (case normalization & timeframe alias mapping)
        if pdef.get("enum"):
            enums = pdef["enum"]
            if isinstance(val, str):
                val_clean = val.strip()
                enum_map = {str(e).upper(): e for e in enums}
                if val_clean.upper() in enum_map:
                    args[key] = enum_map[val_clean.upper()]
                    val = args[key]
                elif key == "timeframe" or set(enums).issubset({"M15", "H1", "H4", "D1"}):
                    tf_upper = val_clean.upper()
                    tf_aliases = {"1H": "H1", "4H": "H4", "1D": "D1", "15M": "M15"}
                    canonical_tf = tf_aliases.get(tf_upper, tf_upper)
                    if canonical_tf in enum_map:
                        args[key] = enum_map[canonical_tf]
                        val = args[key]
                    elif canonical_tf == "M15" and "H1" in enum_map:
                        args[key] = enum_map["H1"]
                        val = args[key]
                        logger.info(f"Coerced timeframe 'M15' to 'H1' for '{key}'")

        if "integer" in expected_types:
            if isinstance(val, bool):
                pass
            elif isinstance(val, (int, float)):
                try:
                    f = float(val)
                    if f.is_integer():
                        args[key] = int(f)
                except (ValueError, TypeError, OverflowError):
                    pass
            elif isinstance(val, str):
                s = val.strip()
                try:
                    f = float(s)
                    if f.is_integer():
                        args[key] = int(f)
                except (ValueError, TypeError, OverflowError):
                    pass
        elif "number" in expected_types:
            if isinstance(val, bool):
                pass
            elif isinstance(val, str):
                s = val.strip().replace("$", "").replace(",", "")
                try:
                    args[key] = float(s)
                except (ValueError, TypeError):
                    pass
        elif "boolean" in expected_types:
            if isinstance(val, str):
                s = val.strip().lower()
                if s in ("true", "1", "yes"):
                    args[key] = True
                elif s in ("false", "0", "no"):
                    args[key] = False
        elif "string" in expected_types:
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                args[key] = str(val)
        elif "array" in expected_types:
            if isinstance(val, str):
                s = val.strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        args[key] = json.loads(s)
                        val = args[key]
                    except Exception:
                        args[key] = [s]
                        val = args[key]
                elif not s or s.lower() in ("none", "null", "n/a", "[]"):
                    args[key] = []
                    val = args[key]
                else:
                    args[key] = [s]
                    val = args[key]
                logger.info(f"Coerced string to array for '{key}'")

            if key == "confluence_factors" and isinstance(args.get(key), list):
                FACTOR_ALIASES = {
                    "microstructure": "microstructure_ok",
                    "order_flow": "microstructure_ok",
                    "vpin_ok": "microstructure_ok",
                    "pattern": "historical_pattern_consensus",
                    "pattern_similarity": "historical_pattern_consensus",
                    "chart_pattern": "historical_pattern_consensus",
                }
                args[key] = [
                    FACTOR_ALIASES.get(str(item).strip().lower(), str(item))
                    for item in args[key]
                ]
        elif "object" in expected_types:
            if isinstance(val, str):
                s = val.strip()
                parsed_obj = None
                xml_dict = _parse_xml_parameters(s)
                if xml_dict:
                    parsed_obj = xml_dict
                elif s.startswith("{") and s.endswith("}"):
                    try:
                        parsed_obj = json.loads(s)
                    except Exception:
                        pass

                if not parsed_obj:
                    if key == "reevaluation_trigger":
                        parsed_obj = {"type": "time", "detail": s}
                    elif key == "entry_condition":
                        parsed_obj = {"type": "market", "detail": s}
                    elif key == "specialist_adjudication":
                        parsed_obj = {
                            "conflict_detected": True,
                            "conflict_reason": s,
                            "resolution_path": "cancel_setup",
                            "resolution_justification": s,
                        }
                    elif key == "priced_in_override_justification":
                        parsed_obj = {
                            "override_reason": s,
                            "why_stage1_wrong": s,
                            "post_event_evidence": s,
                        }

                if isinstance(parsed_obj, dict):
                    args[key] = parsed_obj
                    val = parsed_obj
                    logger.info(f"Coerced string/XML to object for '{key}'")

            if isinstance(val, dict):
                coerce_tool_arguments(val, pdef)

    return args

