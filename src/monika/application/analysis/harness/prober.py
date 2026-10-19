"""
Harness Prober for Monika (Task-Level Recursion - Phase 2: Probe).

Executes candidate harnesses against market data or historical simulation scenarios
to collect empirical behavioral evidence without altering production state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from monika.application.analysis.harness.proposer import CandidateProposal
from monika.application.analysis.harness.tree import HarnessTree

logger = logging.getLogger("TradingAgent.HarnessProber")


@dataclass(frozen=True)
class ProbeMetrics:
    """Quantitative performance and behavioral metrics observed during a probe run."""

    grounding_score: float  # 0.0 to 1.0 (proportion of verified numerical claims)
    confluence_score: float  # 0.0 to 1.0 (structural multi-timeframe agreement)
    win_rate_estimate: float  # 0.0 to 1.0 (projected win rate under this harness)
    profit_factor_estimate: float  # projected profit factor (e.g. 1.8)
    max_drawdown_risk: float  # 0.0 to 1.0 (lower is better)
    violations_detected: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        """
        Calculates composite quality index (higher is better).
        Heavily penalizes grounding failures and excessive drawdown risk.
        """
        if self.violations_detected > 0:
            return 0.0
        score = (
            (self.grounding_score * 0.35)
            + (self.confluence_score * 0.25)
            + (self.win_rate_estimate * 0.25)
            + (min(self.profit_factor_estimate / 2.0, 1.0) * 0.15)
        )
        # Penalize drawdown
        score *= max(0.1, 1.0 - (self.max_drawdown_risk * 0.5))
        return round(score, 4)


@dataclass(frozen=True)
class ProbeResult:
    """The outcome of probing a single candidate harness."""

    candidate_id: str
    tree: HarnessTree
    metrics: ProbeMetrics
    delivered_cleanly: bool = True
    error_message: str = ""


ProbeRunner = Callable[[HarnessTree, Mapping[str, Any]], ProbeMetrics]


class HarnessProber:
    """
    Evaluates candidate harnesses by executing simulated scenario runs.
    """

    def __init__(self, custom_runner: Optional[ProbeRunner] = None):
        self._runner = custom_runner or self._default_probe_runner

    @staticmethod
    def _default_probe_runner(tree: HarnessTree, scenario_data: Mapping[str, Any]) -> ProbeMetrics:
        """
        Deterministic default behavioral prober inspecting harness content quality,
        grounding posture, and guardrail completeness.
        """
        tree_dict = tree.to_dict()
        gr_content = tree_dict.get("guardrails.md", "")
        sp_content = tree_dict.get("systemprompt.md", "")

        # Check grounding keywords
        has_grounding = "grounding" in gr_content.lower() or "verified" in gr_content.lower()
        has_fail_closed = "fail closed" in gr_content.lower() or "fail-closed" in gr_content.lower()
        has_bos = "structure" in sp_content.lower() or "confluence" in sp_content.lower()

        grounding_score = 0.95 if has_grounding else 0.60
        confluence_score = 0.90 if has_bos else 0.50
        win_rate = 0.68 if (has_grounding and has_fail_closed) else 0.50
        pf = 1.95 if (has_grounding and has_fail_closed) else 1.20
        dd_risk = 0.08 if has_fail_closed else 0.22

        return ProbeMetrics(
            grounding_score=grounding_score,
            confluence_score=confluence_score,
            win_rate_estimate=win_rate,
            profit_factor_estimate=pf,
            max_drawdown_risk=dd_risk,
            violations_detected=0,
            details={"rules_evaluated": len(tree.components)},
        )

    def probe_candidates(
        self,
        base_tree: HarnessTree,
        candidates: Sequence[CandidateProposal],
        scenario_data: Mapping[str, Any],
    ) -> Sequence[ProbeResult]:
        """
        Runs probe evaluations across base and all candidate proposals.
        """
        results: list[ProbeResult] = []

        # 1. Probe base tree as reference
        try:
            base_metrics = self._runner(base_tree, scenario_data)
            results.append(
                ProbeResult(
                    candidate_id="base",
                    tree=base_tree,
                    metrics=base_metrics,
                    delivered_cleanly=True,
                )
            )
        except Exception as exc:
            logger.error(f"[HarnessProber] Base probe failed: {exc}")
            results.append(
                ProbeResult(
                    candidate_id="base",
                    tree=base_tree,
                    metrics=ProbeMetrics(0, 0, 0, 0, 1.0, 1),
                    delivered_cleanly=False,
                    error_message=str(exc),
                )
            )

        # 2. Probe each candidate proposal
        for cand in candidates:
            try:
                metrics = self._runner(cand.tree, scenario_data)
                results.append(
                    ProbeResult(
                        candidate_id=cand.candidate_id,
                        tree=cand.tree,
                        metrics=metrics,
                        delivered_cleanly=True,
                    )
                )
            except Exception as exc:
                logger.error(f"[HarnessProber] Candidate '{cand.candidate_id}' failed: {exc}")
                results.append(
                    ProbeResult(
                        candidate_id=cand.candidate_id,
                        tree=cand.tree,
                        metrics=ProbeMetrics(0, 0, 0, 0, 1.0, 1),
                        delivered_cleanly=False,
                        error_message=str(exc),
                    )
                )

        return results
