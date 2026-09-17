"""
Provenance Tagger & Ledger: Tracks numeric provenance of tool outputs
and cross-verifies figures cited by LLM agents.
Source: Vibe-Trading src/agent/grounding/
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("TradingAgent.ProvenanceTagger")


@dataclass(frozen=True)
class ObservedFact:
    """Single numeric fact extracted from tool output."""
    field: str
    value: float
    tool_name: str
    timestamp: datetime


class ProvenanceLedger:
    """
    Append-only registry of numeric facts produced by tool executions.
    Can verify whether cited prices/numbers in LLM reasoning were empirically observed.
    """

    def __init__(self):
        self._facts: List[ObservedFact] = []

    def register_from_tool_output(self, tool_name: str, result: Any) -> int:
        """Parse numeric values from tool result and register as observed facts."""
        numerics = self._extract_numerics(result)
        count = 0
        now = datetime.now(timezone.utc)
        for key, val in numerics.items():
            self._facts.append(
                ObservedFact(field=key, value=val, tool_name=tool_name, timestamp=now)
            )
            count += 1
        return count

    def register_fact(self, field_name: str, value: float, tool_name: str = "manual") -> None:
        """Manually register a single observed fact."""
        self._facts.append(
            ObservedFact(
                field=field_name,
                value=float(value),
                tool_name=tool_name,
                timestamp=datetime.now(timezone.utc),
            )
        )

    def verify_citation(
        self, claimed_value: float, field_hint: str = "", tolerance: float = 1e-4
    ) -> Optional[ObservedFact]:
        """Find nearest matching observed fact within relative tolerance."""
        best: Optional[ObservedFact] = None
        best_dist = float("inf")

        for fact in self._facts:
            if field_hint and field_hint.lower() not in fact.field.lower():
                continue
            dist = abs(fact.value - claimed_value)
            denom = abs(fact.value) if abs(fact.value) > 1e-8 else 1.0
            rel_dist = dist / denom

            if rel_dist <= tolerance and dist < best_dist:
                best = fact
                best_dist = dist

        return best

    def verify_text_citations(
        self, text: str, tolerance: float = 1e-3
    ) -> Tuple[int, int, List[float]]:
        """
        Scan text for numbers and verify against ledger facts.
        Returns: (verified_count, unverified_count, unverified_numbers)
        """
        if not text:
            return 0, 0, []

        tokens = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
        verified = 0
        unverified = 0
        unverified_nums: List[float] = []

        for token in tokens:
            try:
                num = float(token)
            except ValueError:
                continue

            # Ignore small structural integers (e.g. 1, 2, 3, 14, 20)
            if num in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 14.0, 20.0, 50.0, 100.0, 200.0):
                continue

            match = self.verify_citation(num, tolerance=tolerance)
            if match:
                verified += 1
            else:
                unverified += 1
                unverified_nums.append(num)

        return verified, unverified, unverified_nums

    def _extract_numerics(self, obj: Any, prefix: str = "") -> Dict[str, float]:
        """Recursively extract float values from nested dict/list/primitives."""
        result: Dict[str, float] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                result.update(self._extract_numerics(v, f"{prefix}{k}."))
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                result.update(self._extract_numerics(v, f"{prefix}[{i}]."))
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            result[prefix.rstrip(".")] = float(obj)
        return result

    @property
    def facts(self) -> List[ObservedFact]:
        return list(self._facts)
