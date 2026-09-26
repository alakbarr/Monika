# ==============================================================================
# File: analysis/memory/mechanical_anchor_index.py
# ==============================================================================

"""
Mechanical Anchor Index for High-Precision Numeric Fact Retention.
Institutional-grade memory and context protection architecture.

Extracts, locks, and guarantees retention of critical financial numbers:
order tickets, stop losses, take profits, lot sizes, margin limits, and risk ratios.
Prevents catastrophic numerical hallucination during context compression.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.Memory.MechanicalAnchorIndex")

# Regular expressions for financial invariants
_TICKET_REGEX = re.compile(r"\b(?:ticket|order|position)\s*(?:#|id|no\.?)?\s*([0-9]{4,10})\b", re.IGNORECASE)
_SL_TP_REGEX = re.compile(r"\b(SL|TP|Stop\s*Loss|Take\s*Profit)\s*(?:@|:|at|=)?\s*([0-9]+\.[0-9]+)\b", re.IGNORECASE)
_LOT_REGEX = re.compile(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:lots?|volume)\b", re.IGNORECASE)
_PERCENT_RISK_REGEX = re.compile(r"\b([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:risk|drawdown|equity)\b", re.IGNORECASE)


class MechanicalAnchorIndex:
    """Extracts and preserves deterministic numeric constraints across prompt turns."""

    def __init__(self):
        self._anchors: Dict[str, Any] = {}

    def extract_anchors(self, text: str) -> Dict[str, Any]:
        """Scans text and extracts numeric anchor entities."""
        if not text:
            return {}

        found: Dict[str, Any] = {}

        # 1. Order Tickets
        tickets: Set[str] = set()
        for m in _TICKET_REGEX.finditer(text):
            tickets.add(m.group(1))
        if tickets:
            found["tickets"] = sorted(list(tickets))

        # 2. Stop Loss & Take Profit Levels
        price_levels: Dict[str, float] = {}
        for m in _SL_TP_REGEX.finditer(text):
            tag = "SL" if "sl" in m.group(1).lower() or "stop" in m.group(1).lower() else "TP"
            try:
                price_levels[tag] = float(m.group(2))
            except ValueError:
                pass
        if price_levels:
            found["price_levels"] = price_levels

        # 3. Lot Sizes
        lots: Set[float] = set()
        for m in _LOT_REGEX.finditer(text):
            try:
                lots.add(float(m.group(1)))
            except ValueError:
                pass
        if lots:
            found["lots"] = sorted(list(lots))

        # 4. Percent Risk / Drawdown
        risks: Set[float] = set()
        for m in _PERCENT_RISK_REGEX.finditer(text):
            try:
                risks.add(float(m.group(1)))
            except ValueError:
                pass
        if risks:
            found["risk_percentages"] = sorted(list(risks))

        # Merge into session anchors
        for k, v in found.items():
            if isinstance(v, dict):
                self._anchors.setdefault(k, {}).update(v)
            elif isinstance(v, list):
                existing = set(self._anchors.setdefault(k, []))
                existing.update(v)
                self._anchors[k] = sorted(list(existing))

        return found

    def get_anchors(self) -> Dict[str, Any]:
        return dict(self._anchors)

    def render_anchor_block(self) -> str:
        """Renders an authoritative, unalterable XML context block containing numeric anchors."""
        if not self._anchors:
            return ""

        lines = ["<mechanical-invariants>"]
        if "tickets" in self._anchors:
            lines.append(f"  ACTIVE_TICKETS: {', '.join(str(t) for t in self._anchors['tickets'])}")
        if "price_levels" in self._anchors:
            levels_str = ", ".join(f"{k}={v}" for k, v in self._anchors["price_levels"].items())
            lines.append(f"  PRICE_CONSTRAINTS: {levels_str}")
        if "lots" in self._anchors:
            lines.append(f"  POSITION_SIZING: {', '.join(str(l) + ' lots' for l in self._anchors['lots'])}")
        if "risk_percentages" in self._anchors:
            lines.append(f"  RISK_BOUNDS: {', '.join(str(r) + '%' for r in self._anchors['risk_percentages'])}")
        lines.append("</mechanical-invariants>")
        return "\n".join(lines)

    def clear(self) -> None:
        self._anchors.clear()
