# ==============================================================================
# File: graph/nodes/state_pruner.py
# ==============================================================================

"""
Context Window Hygiene & State Pruner.
Eliminates intermediate conversation bloat and raw payloads between LangGraph nodes,
retaining distilled analytical synthesis and ground truths.
"""

import logging
from typing import Any, Dict
from graph.state import TradingState

logger = logging.getLogger("TradingAgent.StatePruner")


def prune_after_fundamental(state: TradingState, *args, **kwargs) -> Dict[str, Any]:
    """Prune raw conversational payload from Stage 1, keeping distilled brief & bias."""
    summary_raw = state.get("summary")
    summary: Dict[str, Any] = dict(summary_raw) if isinstance(summary_raw, dict) else {}
    fund_raw = summary.get("fundamental")
    fund: Dict[str, Any] = dict(fund_raw) if isinstance(fund_raw, dict) else {}

    # Discard voluminous raw conversation, messages, & intermediate observations
    pruned_keys = [
        "raw_conversation",
        "raw_tool_observations",
        "intermediate_scratchpad",
        "tool_call_history",
        "raw_prompt",
        "raw_llm_response",
        "unfiltered_headlines",
    ]
    pruned_count = 0
    for k in pruned_keys:
        if k in fund:
            del fund[k]
            pruned_count += 1

    summary["fundamental"] = fund
    logger.debug(f"[StatePruner] Pruned {pruned_count} verbose keys after fundamental analysis")
    return {"summary": summary}


def prune_after_debate(state: TradingState, *args, **kwargs) -> Dict[str, Any]:
    """Prune verbose dialectic arguments and heavy asset payloads, retaining final consensus and trade plans."""
    debate_states = dict(state.get("debate_states", {}) or {})
    for sym, ds in debate_states.items():
        if isinstance(ds, dict):
            for key in [
                "raw_bull_text",
                "raw_bear_text",
                "raw_judge_text",
                "intermediate_dialogue",
                "transcript",
                "dialogue_history",
            ]:
                ds.pop(key, None)

    # Prune heavy data payloads from asset_analyses
    asset_analyses = dict(state.get("asset_analyses", {}) or {})
    for sym, aa in asset_analyses.items():
        if isinstance(aa, dict):
            for heavy in [
                "raw_candles",
                "raw_order_flow",
                "chart_svg",
                "raw_screener_output",
                "raw_tool_history",
                "intermediate_reasoning",
            ]:
                aa.pop(heavy, None)

    # Prune risk debate turns
    risk_debate_states = dict(state.get("risk_debate_states", {}) or {})
    for sym, rds in risk_debate_states.items():
        if isinstance(rds, dict):
            for key in ["raw_conservative_text", "raw_aggressive_text", "raw_neutral_text", "intermediate_dialogue"]:
                rds.pop(key, None)

    logger.debug("[StatePruner] Pruned intermediate dialogue turns & heavy payloads after dialectic debate")
    return {
        "debate_states": debate_states,
        "asset_analyses": asset_analyses,
        "risk_debate_states": risk_debate_states,
    }


def prune_before_execution(state: TradingState, *args, **kwargs) -> Dict[str, Any]:
    """Ensure execution node receives only validated actionable orders and parameters."""
    actionable = list(state.get("actionable_trades", []) or [])
    clean_actionable = []
    for item in actionable:
        if isinstance(item, dict):
            cleaned = dict(item)
            for heavy in (
                "full_history",
                "raw_chart_base64",
                "all_candles",
                "raw_indicators_df",
                "raw_mt5_ticks",
                "deep_analysis_dump",
            ):
                cleaned.pop(heavy, None)
            clean_actionable.append(cleaned)
        elif isinstance(item, tuple):
            # If actionable trade is stored as a tuple (symbol, plan_dict)
            if len(item) == 2 and isinstance(item[1], dict):
                plan = dict(item[1])
                for heavy in (
                    "full_history",
                    "raw_chart_base64",
                    "all_candles",
                    "raw_indicators_df",
                    "raw_mt5_ticks",
                    "deep_analysis_dump",
                ):
                    plan.pop(heavy, None)
                clean_actionable.append((item[0], plan))
            else:
                clean_actionable.append(item)
        else:
            clean_actionable.append(item)

    logger.debug(f"[StatePruner] Pruned {len(clean_actionable)} actionable trades before execution")
    return {"actionable_trades": clean_actionable}
