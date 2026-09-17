"""
Structured Blackboard Working Memory Graph.

Maintains a typed, shared factual working memory for Stage 2 subagents:
- market_invariants: Real-time empirical facts (price, ATR, DXY, VIX, session).
- technical_poi: Verified SMC zones, unmitigated OBs, FVGs, swing extremes.
- sentiment_positioning: COT net bias, retail contrarian ratio, funding rate.
- macro_drivers: Central bank divergence, yield spreads, surprise scores.
- bull_thesis: Primary bull advocacy points.
- bear_dissent: Primary bear counter-thesis points.
- adjudication_consensus: Final distilled synthesis.

Prevents prompt ballooning by allowing subagents to query specific typed slots
instead of dumping massive raw unparsed text histories into subsequent turns.
"""

from typing import Dict, Any, Optional, List
import json
import logging
from utils.llm.prompt_compressor import estimate_tokens, truncate_to_budget

logger = logging.getLogger("TradingAgent.SubagentBlackboard")


class SubagentBlackboard:
    """Typed working memory blackboard shared across specialist turns."""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper().replace("/", "")
        self.slots: Dict[str, Any] = {
            "market_invariants": {},
            "technical_poi": {},
            "sentiment_positioning": {},
            "macro_drivers": {},
            "bull_thesis": {},
            "bear_dissent": {},
            "adjudication_consensus": {},
        }
        self._history_log: List[Dict[str, Any]] = []

    def set_slot(self, slot_name: str, data: Any) -> None:
        """Sets data for a specific blackboard slot."""
        if slot_name in self.slots:
            self.slots[slot_name] = data
            self._history_log.append({"slot": slot_name, "data": data})
            logger.debug(f"[{self.symbol}] Blackboard: slot '{slot_name}' updated.")
        else:
            logger.warning(f"[{self.symbol}] Blackboard: unknown slot '{slot_name}' rejected.")

    def get_slot(self, slot_name: str, default: Any = None) -> Any:
        """Retrieves data from a specific blackboard slot."""
        return self.slots.get(slot_name, default)

    def export_distilled_context(self, max_tokens: int = 1200) -> str:
        """
        Exports a high-density, structured summary of the blackboard state for LLM injection.
        """
        sections = []

        # 1. Market Invariants
        invariants = self.slots.get("market_invariants", {})
        if invariants:
            inv_str = ", ".join(f"{k}: {v}" for k, v in invariants.items() if v is not None)
            sections.append(f"MARKET_INVARIANTS: [{inv_str}]")

        # 2. Technical POI
        tech = self.slots.get("technical_poi", {})
        if tech:
            bias = tech.get("directional_bias", "UNKNOWN")
            conf = tech.get("confidence", "UNKNOWN")
            zone = tech.get("nearest_entry_zone", {})
            sl = tech.get("structural_sl", {})
            sections.append(f"TECH_POI: Bias={bias} ({conf}) | Zone={json.dumps(zone)} | SL={json.dumps(sl)}")

        # 3. Sentiment Positioning
        sent = self.slots.get("sentiment_positioning", {})
        if sent:
            bias = sent.get("directional_bias", "UNKNOWN")
            cot = sent.get("cot_net_position", {})
            retail = sent.get("retail_positioning", {})
            sections.append(f"SENTIMENT: Bias={bias} | COT={json.dumps(cot)} | Retail={json.dumps(retail)}")

        # 4. Macro Drivers
        macro = self.slots.get("macro_drivers", {})
        if macro:
            bias = macro.get("directional_bias", "UNKNOWN")
            dxy = macro.get("dxy_alignment", "UNKNOWN")
            sections.append(f"MACRO: Bias={bias} | DXY={dxy}")

        # 5. Bull vs Bear Debate Points
        bull = self.slots.get("bull_thesis", {})
        bear = self.slots.get("bear_dissent", {})
        if bull or bear:
            bull_arg = bull.get("core_argument", bull.get("thesis", ""))
            bear_arg = bear.get("core_argument", bear.get("thesis", ""))
            if bull_arg:
                sections.append(f"BULL_THESIS: {bull_arg[:200]}")
            if bear_arg:
                sections.append(f"BEAR_DISSENT: {bear_arg[:200]}")

        # 6. Adjudication Consensus
        adj = self.slots.get("adjudication_consensus", {})
        if adj:
            decision = adj.get("decision", adj.get("verdict", "WAIT"))
            conf = adj.get("confidence", 0.0)
            sections.append(f"ADJUDICATION: Decision={decision} (conf={conf})")

        composed = "\n".join(sections)
        return truncate_to_budget(composed, max_tokens=max_tokens)
