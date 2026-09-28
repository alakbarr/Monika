# ==============================================================================
# File: analysis/grounding/surgical_redaction.py
# Monika Grounding Architecture: Surgical Redaction & Provenance Repair
# ==============================================================================

"""
Surgical Redaction & Provenance Repair Engine.

Provides fail-safe release guarantees for generated market analyses:
1. redacted_release(): Replaces unverified hallucinated figures with
   '[Omitted: Unverified]' placeholders while preserving narrative integrity.
2. repair_provenance(): Automatically corrects close-range rounding drift
   to the exact empirical ground-truth recorded in the ProvenanceLedger.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple, Union

from analysis.grounding.declared_figures import DeclaredFigure
from analysis.grounding.provenance_tagger import ProvenanceLedger, ObservedFact

logger = logging.getLogger("TradingAgent.Grounding.SurgicalRedaction")


def redacted_release(
    text: str,
    unverified_figures: List[Union[float, DeclaredFigure]],
    placeholder: str = "[Omitted: Unverified]",
) -> str:
    """
    Surgically redacts unverified numeric values from output text.
    Ensures no hallucinated price or metric reaches executive / trading decision.
    """
    if not text or not unverified_figures:
        return text

    target_values: List[float] = []
    for item in unverified_figures:
        if isinstance(item, DeclaredFigure):
            target_values.append(item.value)
        elif isinstance(item, (int, float)):
            target_values.append(float(item))

    # Sort descending by length of string representation to avoid partial replacement of substrings
    target_values = sorted(list(set(target_values)), key=lambda x: len(str(x)), reverse=True)

    redacted_text = text
    for val in target_values:
        # Match literal float or integer representation
        val_str = str(val)
        val_int_str = str(int(val)) if val.is_integer() else None

        # Build regex for bounded numeric match (supporting negative numbers)
        pattern_str = rf"(?<![\w\.\-]){re.escape(val_str)}(?![\w\.\-])"
        redacted_text = re.sub(pattern_str, placeholder, redacted_text)

        if val_int_str:
            pattern_int = rf"(?<![\w\.\-]){re.escape(val_int_str)}(?![\w\.\-])"
            # Avoid replacing tiny integers (e.g. 1, 2) that could be list items
            if int(val) > 10:
                redacted_text = re.sub(pattern_int, placeholder, redacted_text)

    return redacted_text


def repair_provenance(
    text: str,
    ledger: ProvenanceLedger,
    tolerance: float = 0.005,
) -> Tuple[str, int]:
    """
    Scans text for figures that have slight rounding drift from the ledger
    (e.g., agent writes 2650.40 when tick was 2650.42) and repairs them to exact truth.
    Returns: (repaired_text, repair_count)
    """
    if not text or not ledger._facts:
        return text, 0

    tokens = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
    unique_tokens = sorted(list(set(tokens)), key=len, reverse=True)
    repaired_text = text
    repairs_made = 0

    for tok in unique_tokens:
        try:
            num = float(tok)
        except ValueError:
            continue

        # Skip small common integers
        if num in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 14.0, 20.0, 50.0, 100.0, 200.0):
            continue

        match: ObservedFact | None = ledger.verify_citation(num, tolerance=tolerance)
        if match is not None:
            # If there is slight drift but within tolerance, align to truth
            exact_val_str = str(round(match.value, 5))
            if tok != exact_val_str and abs(match.value - num) > 1e-6:
                pattern = rf"(?<![\w\.\-])\b{re.escape(tok)}\b(?![\w\.\-])"
                repaired_text = re.sub(pattern, exact_val_str, repaired_text)
                repairs_made += 1
                logger.debug(f"[RepairProvenance] Repaired drift: {tok} -> {exact_val_str} ({match.field})")

    return repaired_text, repairs_made
