"""
Harness Proposer for Monika (Task-Level Recursion - Phase 1: Propose).

Generates structured candidate modifications to the active harness tree
tailored to specific market conditions or regime shifts, strictly respecting
all safety invariants and size limits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from monika.domain.harness.models import HarnessDiff, HarnessViolationError, SurfaceSpec
from monika.application.analysis.harness.surface import MONIKA_SURFACE, validate_tree_invariants
from monika.application.analysis.harness.tree import HarnessTree

logger = logging.getLogger("TradingAgent.HarnessProposer")


@dataclass(frozen=True)
class CandidateProposal:
    """A proposed candidate variation of the harness tree."""

    candidate_id: str
    dimension: str  # e.g., "volatility_defense", "regime_adaptation", "entry_precision"
    rationale: str
    tree: HarnessTree
    diff: HarnessDiff


class HarnessProposer:
    """
    Proposes candidate adjustments to mutable harness components
    based on current market regime and historical domain evidence.
    """

    def __init__(self, spec: SurfaceSpec = MONIKA_SURFACE):
        self.spec = spec

    def propose_candidates(
        self,
        base_tree: HarnessTree,
        domain: str,
        regime_context: Mapping[str, Any],
        historical_lessons: str = "",
        k_candidates: int = 2,
    ) -> Sequence[CandidateProposal]:
        """
        Synthesizes k candidate harness trees from the base tree.
        Ensures all proposed trees pass full invariant validation.
        """
        proposals: list[CandidateProposal] = []
        domain_clean = domain.lower().replace("/", "_").replace(" ", "_")

        # Candidate 1: Targeted Domain Skill / Playbook Enhancement
        try:
            cand1_dict = dict(base_tree.to_dict())
            skill_path = f"skills/trading/playbooks/{domain_clean}.md"
            cand1_skill_content = (
                f"---\n"
                f"name: {domain_clean}\n"
                f"description: Empirical playbook for {domain} market regime\n"
                f"---\n\n"
                f"# Playbook: {domain}\n\n"
                f"## Market Cue\n"
                f"Applies when market regime is identified as {domain}.\n\n"
                f"## Procedural Execution Rules\n"
                f"1. Wait for multi-timeframe structural confluence before trade proposal.\n"
                f"2. Confirm liquidity sweep on lower timeframe.\n"
                f"3. Strictly maintain minimum 1:2 Risk-to-Reward ratio.\n\n"
                f"## Empirical Context\n"
                f"{historical_lessons.strip() or 'No prior recorded failures.'}\n"
            )
            cand1_dict[skill_path] = cand1_skill_content
            cand1_tree = HarnessTree.from_dict(cand1_dict, self.spec)
            diff1 = base_tree.diff(cand1_tree)
            proposals.append(
                CandidateProposal(
                    candidate_id="cand_1",
                    dimension="domain_playbook",
                    rationale=f"Synthesize dedicated procedural playbook for {domain}",
                    tree=cand1_tree,
                    diff=diff1,
                )
            )
        except HarnessViolationError as exc:
            logger.warning(f"[HarnessProposer] Candidate 1 rejected by invariants: {exc}")

        # Candidate 2: Analytical Guardrail / Grounding Tightening
        if k_candidates >= 2:
            try:
                cand2_dict = dict(base_tree.to_dict())
                base_guardrails = cand2_dict.get("guardrails.md", "")
                regime_note = (
                    f"\n- Specific Guard for [{domain}]: Demand minimum 2-candle absorption "
                    f"confirmation on M15 before formulating directional bias.\n"
                )
                cand2_dict["guardrails.md"] = base_guardrails.strip() + regime_note
                cand2_tree = HarnessTree.from_dict(cand2_dict, self.spec)
                diff2 = base_tree.diff(cand2_tree)
                proposals.append(
                    CandidateProposal(
                        candidate_id="cand_2",
                        dimension="guardrail_tightening",
                        rationale=f"Add M15 absorption confirmation guardrail for {domain}",
                        tree=cand2_tree,
                        diff=diff2,
                    )
                )
            except HarnessViolationError as exc:
                logger.warning(f"[HarnessProposer] Candidate 2 rejected by invariants: {exc}")

        return proposals
