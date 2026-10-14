# ==============================================================================
# File: analysis/harness/tool_repair.py
# ==============================================================================

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.ToolRepair")

TOOL_NAME_ALIASES: Dict[str, str] = {
    # Search & Web
    "run_shell": "web_search",
    "search": "web_search",
    "search_web": "web_search",
    "google_search": "web_search",
    "academic_search": "search_academic",
    "arxiv_search": "search_academic",
    "fetch_url": "read_url",
    "url_reader": "read_url",
    # Price & Technical Data
    "fetch_price": "get_price_data",
    "get_prices": "get_price_data",
    "price_data": "get_price_data",
    "technical_analysis": "get_technical_analysis",
    "get_ta": "get_technical_analysis",
    "get_technical_indicator": "get_technical_indicators",
    "calculate_size": "calculate_position_size",
    "position_size": "calculate_position_size",
    "get_quote": "get_market_quote",
    "market_quote": "get_market_quote",
    "fetch_quote": "get_market_quote",
    "quote": "get_market_quote",
    # Submissions
    "submit_analysis": "submit_asset_analysis",
    "submit_asset": "submit_asset_analysis",
    "submit_trade_analysis": "submit_asset_analysis",
    "submit_asset_analysis_schema": "submit_asset_analysis",
    "submit_brief": "submit_fundamental_brief",
    "submit_fundamental": "submit_fundamental_brief",
    "submit_fundamental_analysis": "submit_fundamental_brief",
    "submit_fundamental_brief_schema": "submit_fundamental_brief",
    # Macro & Calendar
    "market_snapshot": "get_verified_market_snapshot",
    "verified_snapshot": "get_verified_market_snapshot",
    "ground_truth_snapshot": "get_verified_market_snapshot",
    "get_calendar": "get_economic_calendar",
    "get_economic_calendars": "get_economic_calendar",
    "get_treasury_yield": "get_treasury_yields",
    "get_interest_rate": "get_interest_rates",
    "get_market_sessions": "get_market_session",
    "surprise_summary": "get_surprise_summary",
    "economic_surprise_summary": "get_surprise_summary",
    "get_economic_surprise_summary": "get_surprise_summary",
    # Sentiment & COT
    "get_precomputed_cot_signal": "get_precomputed_cot_signals",
    "get_cot_signals": "get_precomputed_cot_signals",
    "cot_signals": "get_precomputed_cot_signals",
    "precomputed_cot": "get_precomputed_cot_signals",
    # Account & Positions
    "get_positions": "get_open_positions",
    "get_open_position": "get_open_positions",
    "write_scratchpad": "update_scratchpad",
    "read_scratchpad": "read_scratchpad",
    # News & Intel
    "get_news_item": "get_news_items",
    "get_news": "get_news_digest",
    "save_intelligence": "save_market_intelligence",
    "save_intel": "save_market_intelligence",
    "list_intelligence": "list_active_intelligence",
    "list_intel": "list_active_intelligence",
    "archive_intel": "archive_market_intelligence",
    # SMC & Structural Tools
    "analytical_query": "run_analytical_query",
    "query_analytics": "run_analytical_query",
    "get_inducement": "get_inducements",
    "inducements": "get_inducements",
    "get_breaker_block": "get_breaker_blocks",
    "breaker_blocks": "get_breaker_blocks",
    "get_equal_highs": "get_equal_highs_lows",
    "get_equal_lows": "get_equal_highs_lows",
    "equal_highs_lows": "get_equal_highs_lows",
    "judas_swing": "get_judas_swing",
    "wick_fvg": "get_wick_to_wick_fvg",
    "wick_to_wick_fvg": "get_wick_to_wick_fvg",
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
            clean = clean[len(ns) :].strip()

    # Handle doubled prefixes e.g. submit_submit_
    for pfx in ("submit_", "get_", "load_", "calculate_"):
        double_pfx = pfx + pfx
        while clean.startswith(double_pfx):
            clean = clean[len(pfx) :]

    # Check alias map
    if clean in TOOL_NAME_ALIASES:
        repaired = TOOL_NAME_ALIASES[clean]
        logger.info(f"Auto-repaired tool name: '{raw_name}' -> '{repaired}'")
        return repaired

    # Check registry aliases
    try:
        from monika.application.analysis.tools.registry import default_tool_registry

        canonical = default_tool_registry.resolve_name(clean)
        if canonical != clean:
            logger.info(f"Registry resolved tool alias: '{clean}' -> '{canonical}'")
            return canonical
    except Exception:
        pass

    return clean


def _parse_xml_parameters(text: str) -> Optional[Dict[str, Any]]:
    """Parse XML parameter tags e.g. <parameter name="type">price_level</parameter> or <parameter=type>price_level</parameter> into a dict."""
    if not isinstance(text, str):
        return None
    lower_text = text.lower()
    if "<parameter" not in lower_text and "<arg" not in lower_text:
        return None

    # Matches <parameter name="key">val</parameter>, <parameter=key>val</parameter>,
    # <arg name="key">val</arg>, or <arg=key>val</arg>
    pattern = re.compile(
        r'<(?:parameter|arg)(?:\s+name=["\']?([^"\'\s>]+)["\']?|=\s*["\']?([^"\'\s>]+)["\']?)\s*>(.*?)(?:</(?:parameter|arg)>|(?=<(?:parameter|arg))|$)',
        re.DOTALL | re.IGNORECASE,
    )
    matches = pattern.findall(text)
    if matches:
        res: Dict[str, Any] = {}
        for k1, k2, val in matches:
            key = (k1 or k2).strip()
            v_str = val.strip()
            if "<parameter" in v_str.lower() or "<arg" in v_str.lower():
                nested_xml = _parse_xml_parameters(v_str)
                if nested_xml:
                    res[key] = nested_xml
                    continue
            try:
                parsed_v = json.loads(v_str)
                res[key] = parsed_v
            except Exception:
                if v_str.lower() == "true":
                    res[key] = True
                elif v_str.lower() == "false":
                    res[key] = False
                elif v_str.lower() in ("null", "none"):
                    res[key] = None
                else:
                    res[key] = v_str
        return res
    return None


def repair_tool_arguments(args: Any) -> Dict[str, Any]:
    """Repair corrupted JSON arguments (trailing commas, python constants, single quotes, XML tags)."""
    if isinstance(args, dict):
        res = dict(args)
        for k, v in list(res.items()):
            if isinstance(v, str) and ("<parameter" in v.lower() or "<arg" in v.lower()):
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

    # Strip markdown code fences if present
    if "```" in args_str:
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", args_str, re.IGNORECASE)
        if fence_match:
            args_str = fence_match.group(1).strip()

    # Check for pure XML parameter block first
    xml_dict = _parse_xml_parameters(args_str)
    if xml_dict:
        return xml_dict

    # If text is wrapped in conversational filler, extract the outermost JSON object
    if not args_str.startswith("{") and "{" in args_str and "}" in args_str:
        fb = args_str.find("{")
        lb = args_str.rfind("}")
        if fb != -1 and lb != -1 and lb > fb:
            args_str = args_str[fb : lb + 1]

    # Try standard parse first
    try:
        parsed = json.loads(args_str)
        if isinstance(parsed, dict):
            for k, v in list(parsed.items()):
                if isinstance(v, str) and ("<parameter" in v.lower() or "<arg" in v.lower()):
                    xml_p = _parse_xml_parameters(v)
                    if xml_p:
                        parsed[k] = xml_p
            return parsed
        return parsed
    except json.JSONDecodeError:
        pass

    # Repair common LLM syntax defects:
    # 1. Trailing commas before closing braces/brackets
    cleaned = re.sub(r",\s*([}\]])", r"\1", args_str)

    # 2. Python booleans and None
    cleaned = re.sub(r"\bNone\b", "null", cleaned)
    cleaned = re.sub(r"\bTrue\b", "true", cleaned)
    cleaned = re.sub(r"\bFalse\b", "false", cleaned)

    # 3. Single-quoted keys: 'key': -> "key":
    cleaned = re.sub(r"(?<=[{,\s])'([a-zA-Z0-9_]+)'\s*:", r'"\1":', cleaned)

    # 4. Single quotes to double quotes if purely single-quoted
    if "'" in cleaned and '"' not in cleaned:
        cleaned = cleaned.replace("'", '"')

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            for k, v in list(parsed.items()):
                if isinstance(v, str) and ("<parameter" in v.lower() or "<arg" in v.lower()):
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
            elif req_key == "confidence":
                c_conf = args.get("currency_confidence")
                if isinstance(c_conf, dict) and c_conf:
                    nums = [float(v) for v in c_conf.values() if isinstance(v, (int, float))]
                    args["confidence"] = round(sum(nums) / len(nums), 2) if nums else 0.0
                else:
                    args["confidence"] = 0.0
                if str(args.get("decision", "")).lower() in ("buy", "sell"):
                    args["decision"] = "wait"
                    args["rationale"] = (
                        str(args.get("rationale") or "")
                        + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted confidence score."
                    ).strip()
            elif req_key == "macro_regime":
                args["macro_regime"] = "mixed"
            elif req_key == "timeframe":
                args["timeframe"] = "H1"
            elif req_key == "key_data_points_used":
                args["key_data_points_used"] = {}
            elif req_key == "checklist":
                args["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}
            elif req_key == "priced_in_assessment":
                args["priced_in_assessment"] = {
                    "dominant_driver": "Unknown / missing driver",
                    "priced_in_score": 1,
                    "sell_the_news_risk": "high",
                }
            elif req_key == "strongest_counter_thesis":
                args["strongest_counter_thesis"] = "Counter-thesis unstated by model; risk held high."
            elif req_key == "risk_sentiment":
                args["risk_sentiment"] = "mixed"
            elif req_key == "macro_narrative":
                args["macro_narrative"] = "Macro narrative omitted by model; holding baseline mixed assumptions."
            elif req_key == "reevaluation_trigger":
                args["reevaluation_trigger"] = {
                    "type": "time",
                    "detail": "Immediate reevaluation required due to missing model trigger.",
                }
            elif req_key == "entry_condition":
                args["entry_condition"] = {
                    "type": "market",
                    "detail": "Execution held pending valid institutional entry condition.",
                }
                if str(args.get("decision", "")).lower() in ("buy", "sell"):
                    args["decision"] = "wait"
                    args["rationale"] = (
                        str(args.get("rationale") or "")
                        + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted entry condition."
                    ).strip()
            elif req_key == "rationale":
                args["rationale"] = "Model rationale omitted; evaluated under fail-closed safety policy."
            elif req_key == "confluence_score":
                args["confluence_score"] = 0
                if str(args.get("decision", "")).lower() in ("buy", "sell"):
                    args["decision"] = "wait"
                    args["rationale"] = (
                        str(args.get("rationale") or "")
                        + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted confluence score."
                    ).strip()
            elif req_key == "priced_in_score":
                args["priced_in_score"] = 1
                if str(args.get("decision", "")).lower() in ("buy", "sell"):
                    args["decision"] = "wait"
                    args["rationale"] = (
                        str(args.get("rationale") or "")
                        + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted priced-in score."
                    ).strip()

    # Derive invalidation price and direction from stop loss if missing
    if "stop_loss" in args and "invalidation_price" not in args:
        args["invalidation_price"] = args["stop_loss"]
    if "invalidation_direction" not in args and "direction" in args:
        args["invalidation_direction"] = "below" if str(args.get("direction", "")).lower() == "buy" else "above"

    for key, val in list(args.items()):
        if key == "currency_bias" and isinstance(val, dict):
            BIAS_MAP = {
                "STRONG_BULLISH": "strong_bullish",
                "BULLISH": "bullish",
                "BEARISH": "bearish",
                "STRONG_BEARISH": "strong_bearish",
                "NEUTRAL": "neutral",
                "BULL": "bullish",
                "BEAR": "bearish",
                "LONG": "bullish",
                "SHORT": "bearish",
            }
            norm_biases = {}
            for c_sym, c_dir in val.items():
                c_dir_str = str(c_dir).strip().upper()
                norm_biases[c_sym] = BIAS_MAP.get(c_dir_str, c_dir_str.lower())
            args[key] = norm_biases
            val = norm_biases

        if key not in props:
            continue
        pdef = props[key]
        if not isinstance(pdef, dict):
            continue

        raw_type = pdef.get("type")
        expected_types = [raw_type] if isinstance(raw_type, str) else (raw_type if isinstance(raw_type, list) else [])

        # Enum coercion (case normalization & semantic alias mapping)
        if pdef.get("enum"):
            enums = pdef["enum"]
            if isinstance(val, str):
                val_clean = val.strip()
                enum_map = {str(e).upper(): e for e in enums}
                val_lower = val_clean.lower()
                if val_clean.upper() in enum_map:
                    args[key] = enum_map[val_clean.upper()]
                    val = args[key]
                elif key == "risk_sentiment" or set(enums) == {"risk-on", "risk-off", "mixed"}:
                    norm_sent = val_lower.replace("_", "-").replace(" ", "-")
                    if norm_sent in ("risk-on", "risk-off", "mixed"):
                        args[key] = norm_sent
                    elif norm_sent in ("neutral", "balanced", "cautious", "sideways", "none"):
                        args[key] = "mixed"
                    elif "off" in norm_sent:
                        args[key] = "risk-off"
                    elif "on" in norm_sent:
                        args[key] = "risk-on"
                    else:
                        args[key] = "mixed"
                    val = args[key]
                elif key == "macro_regime" or set(enums) == {
                    "risk_on",
                    "risk_off",
                    "stagflation",
                    "disinflation",
                    "transition",
                    "mixed",
                }:
                    if (
                        "risk_on" in val_lower
                        or "risk-on" in val_lower
                        or "expansion" in val_lower
                        or "growth" in val_lower
                    ):
                        args[key] = "risk_on"
                    elif "risk_off" in val_lower or "risk-off" in val_lower or "crisis" in val_lower:
                        args[key] = "risk_off"
                    elif "stagflation" in val_lower:
                        args[key] = "stagflation"
                    elif "disinflation" in val_lower:
                        args[key] = "disinflation"
                    elif "transition" in val_lower:
                        args[key] = "transition"
                    else:
                        args[key] = "mixed"
                    val = args[key]
                elif key == "invalidation_direction" or set(enums) == {"above", "below"}:
                    if val_lower in ("up", "above", "long", "bull", "bullish", "higher", "top"):
                        args[key] = "above"
                    elif val_lower in ("down", "below", "short", "bear", "bearish", "lower", "bottom"):
                        args[key] = "below"
                    val = args[key]
                elif set(enums) == {"price_level", "indicator", "time", "news"}:
                    if val_lower in ("price", "level", "price_level", "price_action", "sl", "tp"):
                        args[key] = "price_level"
                    elif val_lower in ("time", "date", "timer", "schedule", "review", "periodic"):
                        args[key] = "time"
                    elif val_lower in ("indicator", "rsi", "adx", "ema", "fvg", "ob", "structure"):
                        args[key] = "indicator"
                    elif val_lower in ("news", "event", "nfp", "cpi", "fomc", "catalyst"):
                        args[key] = "news"
                    val = args[key]
                elif set(enums) == {"market", "limit", "trigger"}:
                    if val_lower in ("market", "instant", "market_order", "now"):
                        args[key] = "market"
                    elif val_lower in ("limit", "pending", "limit_order", "fvg_entry", "ob_entry"):
                        args[key] = "limit"
                    elif val_lower in ("trigger", "stop", "stop_order", "breakout"):
                        args[key] = "trigger"
                    val = args[key]
                elif key == "direction" or set(enums) == {"buy", "sell"}:
                    if val_lower in ("buy", "long"):
                        args[key] = "buy"
                    elif val_lower in ("sell", "short"):
                        args[key] = "sell"
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
                except ValueError, TypeError, OverflowError:
                    pass
            elif isinstance(val, str):
                s = val.strip()
                try:
                    f = float(s)
                    if f.is_integer():
                        args[key] = int(f)
                except ValueError, TypeError, OverflowError:
                    pass
        elif "number" in expected_types:
            if isinstance(val, bool):
                pass
            elif isinstance(val, str):
                s = val.strip().replace("$", "").replace(",", "")
                try:
                    args[key] = float(s)
                except ValueError, TypeError:
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
                args[key] = [FACTOR_ALIASES.get(str(item).strip().lower(), str(item)) for item in args[key]]
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
                    elif key in ("bias_continuity_justification", "bias_change_justification"):
                        if any(
                            w in s.lower()
                            for w in ("not required", "none", "n/a", "no sticky", "not applicable", "null")
                        ):
                            parsed_obj = {}
                        else:
                            parsed_obj = {"USD": s}

                if isinstance(parsed_obj, dict):
                    args[key] = parsed_obj
                    val = parsed_obj
                    logger.info(f"Coerced string/XML to object for '{key}'")

            if isinstance(val, dict):
                coerce_tool_arguments(val, pdef)

    return args


def deep_repair_tool_arguments(
    tool_name: str,
    args: Dict[str, Any],
    schema: Dict[str, Any],
    error_msg: str,
    assistant_text: str = "",
) -> bool:
    """
    Attempt intelligent, self-healing repair of tool arguments when jsonschema.validate() fails.
    Returns True if successfully repaired and validated, False otherwise.
    """
    if not isinstance(args, dict) or not isinstance(schema, dict):
        return False

    import jsonschema

    props = schema.get("properties", {})

    # Case 1: Missing required property
    req_match = re.search(r"['\"]([^'\"]+)['\"]\s+is a required property", error_msg)
    if req_match:
        missing_prop = req_match.group(1)
        if missing_prop == "macro_narrative":
            if assistant_text and len(assistant_text.strip()) > 30:
                args["macro_narrative"] = assistant_text.strip()
            else:
                args["macro_narrative"] = (
                    "Macro fundamental overview synthesized from pre-fetched market indicators, "
                    "yield differentials, and monetary policy stances."
                )
        elif missing_prop == "risk_sentiment":
            t_low = (assistant_text or "").lower()
            if "risk-on" in t_low or "risk on" in t_low:
                args["risk_sentiment"] = "risk-on"
            elif "risk-off" in t_low or "risk off" in t_low:
                args["risk_sentiment"] = "risk-off"
            else:
                args["risk_sentiment"] = "mixed"
        elif missing_prop == "macro_regime":
            args["macro_regime"] = "mixed"
        elif missing_prop == "confidence":
            args["confidence"] = 0.0
            if str(args.get("decision", "")).lower() in ("buy", "sell"):
                args["decision"] = "wait"
                args["rationale"] = (
                    str(args.get("rationale") or "")
                    + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted confidence score."
                ).strip()
        elif missing_prop == "checklist":
            args["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}
        elif missing_prop == "reevaluation_trigger":
            args["reevaluation_trigger"] = {
                "type": "time",
                "detail": "Immediate reevaluation required due to missing model trigger.",
            }
        elif missing_prop == "entry_condition":
            args["entry_condition"] = {
                "type": "market",
                "detail": "Execution held pending valid institutional entry condition.",
            }
            if str(args.get("decision", "")).lower() in ("buy", "sell"):
                args["decision"] = "wait"
                args["rationale"] = (
                    str(args.get("rationale") or "")
                    + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted entry condition."
                ).strip()
        elif missing_prop == "rationale":
            args["rationale"] = (
                assistant_text[:500]
                if assistant_text
                else "Model rationale omitted; evaluated under fail-closed safety policy."
            )
        elif missing_prop == "confluence_score":
            args["confluence_score"] = 0
            if str(args.get("decision", "")).lower() in ("buy", "sell"):
                args["decision"] = "wait"
                args["rationale"] = (
                    str(args.get("rationale") or "")
                    + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted confluence score."
                ).strip()
        elif missing_prop == "priced_in_score":
            args["priced_in_score"] = 1
            if str(args.get("decision", "")).lower() in ("buy", "sell"):
                args["decision"] = "wait"
                args["rationale"] = (
                    str(args.get("rationale") or "")
                    + " [FAIL-CLOSED]: Proposal forced to WAIT due to omitted priced-in score."
                ).strip()
        elif missing_prop in props and "default" in props[missing_prop]:
            args[missing_prop] = props[missing_prop]["default"]

    # Case 2: Enum mismatch (e.g. 'BEARISH' is not one of [...])
    enum_match = re.search(r"['\"]([^'\"]+)['\"]\s+is not one of\s+\[(.*?)\]", error_msg)
    if enum_match:
        invalid_val = enum_match.group(1)
        allowed_raw = enum_match.group(2)
        allowed_enums = [x.strip().strip("'\"") for x in allowed_raw.split(",")]
        enum_lookup = {e.lower(): e for e in allowed_enums}
        norm_val = invalid_val.strip().lower()

        matched = enum_lookup.get(norm_val)
        if not matched:
            synonyms = {
                "bull": "bullish",
                "bear": "bearish",
                "long": "bullish",
                "short": "bearish",
                "up": "above",
                "down": "below",
                "price": "price_level",
                "level": "price_level",
            }
            cand = synonyms.get(norm_val)
            if cand in enum_lookup:
                matched = enum_lookup[cand]

        if matched:

            def _replace_val(d: Any):
                if isinstance(d, dict):
                    for k, v in list(d.items()):
                        if v == invalid_val:
                            d[k] = matched
                        elif isinstance(v, dict):
                            _replace_val(v)
                elif isinstance(d, list):
                    for i, v in enumerate(d):
                        if v == invalid_val:
                            d[i] = matched
                        elif isinstance(v, (dict, list)):
                            _replace_val(v)

            _replace_val(args)

    # Re-run coerce_tool_arguments on updated args
    coerce_tool_arguments(args, schema)

    # Re-validate
    try:
        jsonschema.validate(instance=args, schema=schema)
        return True
    except Exception:
        return False
