"""
Contrastive Selector for Monika (Task-Level Recursion - Phase 3: Contrastive Selection).

Selects the optimal harness through anonymized, bias-free behavioral comparison
and extracts structured causal lessons (Cue, Lesson, Evidence) from empirical contrasts.
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from monika.application.analysis.harness.prober import ProbeResult
from monika.application.analysis.harness.tree import HarnessTree

logger = logging.getLogger("TradingAgent.ContrastiveSelector")


@dataclass(frozen=True)
class ContrastiveSelection:
    """The result of contrastive evaluation across probed candidate harnesses."""

    chosen_candidate_id: str
    chosen_label: str  # anonymized label (A, B, C...)
    chosen_tree: HarnessTree
    chosen_is_base: bool
    composite_score: float
    why: str
    experience_cue: str
    experience_lesson: str
    evidence: Mapping[str, Any]
    dropped_candidates: Sequence[str] = field(default_factory=tuple)


class ContrastiveSelector:
    """
    Evaluates candidate probe results contrastively, selects the best performer,
    and extracts empirical lessons for persistent memory.
    """

    def __init__(self, min_improvement_margin: float = 0.03):
        # Must beat the base tree by at least 3% to be adopted
        self.min_improvement_margin = min_improvement_margin

    def select(
        self,
        domain: str,
        probe_results: Sequence[ProbeResult],
        regime_context: Mapping[str, Any],
    ) -> ContrastiveSelection:
        """
        Anonymizes candidates, selects the winning harness, and formulates causal lessons.
        """
        valid_results = [r for r in probe_results if r.delivered_cleanly]
        dropped = [r.candidate_id for r in probe_results if not r.delivered_cleanly]

        if not valid_results:
            raise ValueError("All candidate harness probes failed or were dropped.")

        # 1. Deterministic anonymization (prevents positional bias)
        seed_str = f"{domain}_{len(probe_results)}_{'_'.join(r.candidate_id for r in probe_results)}"
        seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
        shuffled = list(valid_results)
        random.Random(seed).shuffle(shuffled)

        anon_map = {chr(ord("A") + i): res for i, res in enumerate(shuffled)}

        # Find base result
        base_result = next((r for r in valid_results if r.candidate_id == "base"), None)
        base_score = base_result.metrics.composite_score if base_result else 0.0

        # Rank candidates by composite score
        ranked_anon = sorted(
            anon_map.items(),
            key=lambda item: item[1].metrics.composite_score,
            reverse=True,
        )

        top_label, top_result = ranked_anon[0]
        top_score = top_result.metrics.composite_score

        # 2. Check if top candidate sufficiently outperforms base
        if top_result.candidate_id != "base":
            if (top_score - base_score) < self.min_improvement_margin:
                # Fall back to base to avoid churn/overfitting
                chosen_res = base_result if base_result is not None else top_result
                chosen_is_base = True
                chosen_label = next(
                    (lbl for lbl, res in anon_map.items() if res.candidate_id == "base"),
                    top_label,
                )
                why = (
                    f"Candidate '{top_result.candidate_id}' score ({top_score:.3f}) did not exceed "
                    f"base score ({base_score:.3f}) by required margin ({self.min_improvement_margin:.3f}). "
                    f"Retained stable base harness."
                )
            else:
                chosen_res = top_result
                chosen_is_base = False
                chosen_label = top_label
                why = (
                    f"Candidate '{top_result.candidate_id}' outperformed base with score "
                    f"{top_score:.3f} vs base {base_score:.3f} (+{(top_score - base_score):.3f})."
                )
        else:
            chosen_res = top_result
            chosen_is_base = True
            chosen_label = top_label
            why = f"Base harness demonstrated optimal stability and score ({base_score:.3f})."

        # 3. Extract contrastive lesson
        cue = (
            f"Asset & Regime: {domain} | "
            f"Volatility state: {regime_context.get('volatility_state', 'NORMAL')} | "
            f"Confluence: {regime_context.get('confluence_level', 'STANDARD')}"
        )

        lesson = (
            f"In domain '{domain}', {why} "
            f"Grounding score reached {chosen_res.metrics.grounding_score:.2f} "
            f"with estimated drawdown risk constrained to {chosen_res.metrics.max_drawdown_risk:.2%}."
        )

        evidence = {
            "chosen_candidate": chosen_res.candidate_id,
            "composite_score": chosen_res.metrics.composite_score,
            "grounding_score": chosen_res.metrics.grounding_score,
            "win_rate_estimate": chosen_res.metrics.win_rate_estimate,
            "drawdown_risk": chosen_res.metrics.max_drawdown_risk,
            "base_score": base_score,
            "competitors_evaluated": len(anon_map),
        }

        return ContrastiveSelection(
            chosen_candidate_id=chosen_res.candidate_id,
            chosen_label=chosen_label,
            chosen_tree=chosen_res.tree,
            chosen_is_base=chosen_is_base,
            composite_score=chosen_res.metrics.composite_score,
            why=why,
            experience_cue=cue,
            experience_lesson=lesson,
            evidence=evidence,
            dropped_candidates=tuple(dropped),
        )
