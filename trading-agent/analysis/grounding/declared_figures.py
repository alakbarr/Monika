# ==============================================================================
# File: analysis/grounding/declared_figures.py
# Monika Grounding Architecture: Declared Figures Block & Shape Filter
# ==============================================================================

"""
Declared Figures Block & Structural Shape Matcher.

Allows LLM agents to declare numeric commitments with explicit roles:
1. observed: Real-time ticks, highs/lows, ATR, volume profile nodes, ledger-backed.
2. derived: Calculated ratios, z-scores, rolling correlations, VaR, EVT tail shape.
3. proposed: Target entry price, stop-loss, take-profit, position lots.
4. cited: Historical macro figures, rates, dates, economic survey consensus.
5. count: Discrete counts, bar lengths, order quantities.

Replaces brittle regex figure extraction with structural shape matching:
- Ignores calendar dates (YYYY-MM-DD, DD/MM/YYYY)
- Ignores timestamps (HH:MM:SS, HH:MM)
- Ignores ordinals (1st, 2nd, 3rd, 4th)
- Ignores markdown list numbering and table alignments
- Ignores software versions (e.g. 1.0.0)
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field

from analysis.grounding.provenance_tagger import ProvenanceLedger, ObservedFact

logger = logging.getLogger("TradingAgent.Grounding.DeclaredFigures")


class FigureRole(str, Enum):
    OBSERVED = "observed"
    DERIVED = "derived"
    PROPOSED = "proposed"
    CITED = "cited"
    COUNT = "count"


class DeclaredFigure(BaseModel):
    name: str = Field(description="Name or semantic identifier of the figure")
    value: float = Field(description="Numeric value declared by agent")
    role: FigureRole = Field(description="Role classification: observed, derived, proposed, cited, count")
    unit: Optional[str] = Field(default=None, description="Optional unit (USD, pips, %, lots, etc.)")
    source: Optional[str] = Field(default=None, description="Empirical provenance tool or calculation source")
    tolerance: Optional[float] = Field(default=None, description="Custom relative verification tolerance")


class DeclaredFiguresBlock(BaseModel):
    figures: List[DeclaredFigure] = Field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> Optional[DeclaredFiguresBlock]:
        """
        Extracts declared figures block from LLM output.
        Looks for ```figures ... ``` or ```declared_figures ... ``` or json block.
        """
        if not text:
            return None

        # Pattern 1: ```figures ... ```
        pattern = r"```(?:figures|declared_figures)\s*([\s\S]*?)\s*```"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_content = match.group(1).strip()
            try:
                data = json.loads(raw_content)
                if isinstance(data, list):
                    return cls(figures=[DeclaredFigure(**item) for item in data])
                elif isinstance(data, dict) and "figures" in data:
                    return cls(**data)
            except Exception as e:
                logger.debug(f"Failed to parse declared figures json: {e}")

        # Pattern 2: Look for JSON array with role and value keys
        json_blocks = re.findall(r"```(?:json)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```", text)
        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, list) and len(data) > 0 and "role" in data[0] and "value" in data[0]:
                    return cls(figures=[DeclaredFigure(**item) for item in data])
            except Exception:
                continue

        return None


class StructuralShapeFilter:
    """
    Filters out noise numbers that should never be verified as market figures:
    dates, times, ordinals, markdown formatting, HTTP codes, and versions.
    """

    DATE_PATTERNS = [
        re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),     # 2026-09-28
        re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"),     # 28/09/2026
        re.compile(r"\b\d{4}\b"),                             # Standalone year 2024..2030
    ]

    TIME_PATTERNS = [
        re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:UTC|GMT|EST|EDT|WIB))?\b", re.IGNORECASE),
    ]

    ORDINAL_PATTERN = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)
    LIST_NUMBER_PATTERN = re.compile(r"^\s*\d+[\.\)]\s+", re.MULTILINE)
    VERSION_PATTERN = re.compile(r"\bv?\d+\.\d+\.\d+\b")
    TABLE_BORDER_PATTERN = re.compile(r"\|")

    @classmethod
    def is_structural_noise(cls, token: str, full_context: str = "") -> bool:
        """Determines if a matched numeric token is structural noise rather than a market figure."""
        clean = token.strip()
        
        # Standalone common integers
        try:
            val = float(clean)
            if val in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 14.0, 20.0, 50.0, 100.0, 200.0):
                return True
            # Years between 2000 and 2050
            if 2000 <= val <= 2050 and "." not in clean:
                return True
        except ValueError:
            return True

        if cls.ORDINAL_PATTERN.search(clean):
            return True

        return False

    @classmethod
    def clean_text_for_figures(cls, text: str) -> str:
        """Removes dates, times, versions, and markdown tables to leave pure verifiable prose."""
        cleaned = text
        for pat in cls.DATE_PATTERNS:
            cleaned = pat.sub(" [DATE] ", cleaned)
        for pat in cls.TIME_PATTERNS:
            cleaned = pat.sub(" [TIME] ", cleaned)
        cleaned = cls.ORDINAL_PATTERN.sub(" [ORDINAL] ", cleaned)
        cleaned = cls.VERSION_PATTERN.sub(" [VERSION] ", cleaned)
        cleaned = cls.LIST_NUMBER_PATTERN.sub(" ", cleaned)
        return cleaned


class FigureValidationResult(BaseModel):
    figure: DeclaredFigure
    is_verified: bool
    matched_fact: Optional[Dict[str, Any]] = None
    discrepancy_pct: float = 0.0
    reason: str = ""


class GroundingReport(BaseModel):
    total_declared: int = 0
    verified_count: int = 0
    unverified_count: int = 0
    pass_rate: float = 1.0
    results: List[FigureValidationResult] = Field(default_factory=list)
    unverified_figures: List[DeclaredFigure] = Field(default_factory=list)


def verify_declared_figures(
    block: DeclaredFiguresBlock,
    ledger: ProvenanceLedger,
    default_tolerances: Optional[Dict[FigureRole, float]] = None,
) -> GroundingReport:
    """
    Verifies a declared figures block against the empirical ProvenanceLedger.
    Applies role-aware tolerances:
    - OBSERVED: tight tolerance (1e-4)
    - DERIVED: calculation tolerance (0.02 or 2%)
    - PROPOSED: structural bounds check (validates price sanity)
    - CITED: news tolerance (0.05)
    - COUNT: exact match (0.0)
    """
    tolerances = {
        FigureRole.OBSERVED: 1e-4,
        FigureRole.DERIVED: 0.02,
        FigureRole.PROPOSED: 0.05,
        FigureRole.CITED: 0.05,
        FigureRole.COUNT: 1e-5,
    }
    if default_tolerances:
        tolerances.update(default_tolerances)

    results: List[FigureValidationResult] = []
    verified = 0
    unverified = 0
    unverified_figs: List[DeclaredFigure] = []

    for fig in block.figures:
        # Proposed values (e.g. SL/TP) do not need historical observation if they are valid order prices
        if fig.role == FigureRole.PROPOSED:
            # Sane positive price check
            if fig.value > 0:
                results.append(
                    FigureValidationResult(
                        figure=fig,
                        is_verified=True,
                        discrepancy_pct=0.0,
                        reason="Proposed trade level valid positive figure",
                    )
                )
                verified += 1
            else:
                results.append(
                    FigureValidationResult(
                        figure=fig,
                        is_verified=False,
                        discrepancy_pct=1.0,
                        reason="Proposed trade level cannot be zero or negative",
                    )
                )
                unverified += 1
                unverified_figs.append(fig)
            continue

        tol = fig.tolerance if fig.tolerance is not None else tolerances.get(fig.role, 0.01)
        fact = ledger.verify_citation(fig.value, field_hint=fig.name, tolerance=tol)

        if fact is not None:
            denom = abs(fact.value) if abs(fact.value) > 1e-8 else 1.0
            disc = abs(fact.value - fig.value) / denom
            results.append(
                FigureValidationResult(
                    figure=fig,
                    is_verified=True,
                    matched_fact={"field": fact.field, "value": fact.value, "tool": fact.tool_name},
                    discrepancy_pct=round(disc, 6),
                    reason=f"Matched empirical fact from tool {fact.tool_name}",
                )
            )
            verified += 1
        else:
            results.append(
                FigureValidationResult(
                    figure=fig,
                    is_verified=False,
                    discrepancy_pct=1.0,
                    reason=f"No matching empirical observation found in ledger within {tol*100:.2f}% tolerance",
                )
            )
            unverified += 1
            unverified_figs.append(fig)

    total = len(block.figures)
    rate = (verified / total) if total > 0 else 1.0

    return GroundingReport(
        total_declared=total,
        verified_count=verified,
        unverified_count=unverified,
        pass_rate=round(rate, 4),
        results=results,
        unverified_figures=unverified_figs,
    )
