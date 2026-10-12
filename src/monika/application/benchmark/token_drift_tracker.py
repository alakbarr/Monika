# ==============================================================================
# File: benchmark/token_drift_tracker.py
# Description: Prompt Regression Benchmark & Token Drift Tracker
# ==============================================================================

"""
Prompt Regression Benchmark & Token Drift Tracker.
Monitors prompt token footprints across stages and model revisions to detect:
1. Prompt Bloat (>15% token expansion).
2. Cache Invalidation Regressions (unexpected changes to Surface Node 0 hash).
3. Cost Drift (unplanned API billing escalations).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
import json
import logging

logger = logging.getLogger("TradingAgent.TokenDriftTracker")


@dataclass
class PromptSnapshot:
    """Snapshot of a stage's prompt assembly metadata."""
    stage_name: str
    system_prompt_chars: int
    system_prompt_tokens_est: int
    surface_node_0_hash: str
    user_prompt_chars: int
    user_prompt_tokens_est: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model: str = "unknown"
    role: str = ""

    @classmethod
    def from_prompts(
        cls,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        model: str = "unknown",
        role: str = "",
    ) -> "PromptSnapshot":
        sys_chars = len(system_prompt)
        user_chars = len(user_prompt)
        # Approximate 1 token ~= 4 characters for English / code
        sys_tokens = max(1, sys_chars // 4)
        user_tokens = max(1, user_chars // 4)
        h = hashlib.sha256(system_prompt.strip().encode("utf-8")).hexdigest()[:16]

        return cls(
            stage_name=stage_name,
            system_prompt_chars=sys_chars,
            system_prompt_tokens_est=sys_tokens,
            surface_node_0_hash=h,
            user_prompt_chars=user_chars,
            user_prompt_tokens_est=user_tokens,
            model=model,
            role=role,
        )


@dataclass
class DriftReport:
    """Audit report comparing current prompt footprint against baseline."""
    stage_name: str
    is_drift_detected: bool
    is_cache_invalidated: bool
    token_growth_pct: float
    violations: List[str]
    baseline_tokens: int
    current_tokens: int


class TokenDriftTracker:
    """Tracks prompt token evolution and detects prompt bloat or cache breaks."""

    def __init__(self, max_drift_pct: float = 15.0):
        self.max_drift_pct = max_drift_pct
        self._baselines: Dict[str, PromptSnapshot] = {}
        self._history: Dict[str, List[PromptSnapshot]] = {}

    def set_baseline(self, snapshot: PromptSnapshot) -> None:
        """Establishes golden ground-truth baseline for a stage."""
        self._baselines[snapshot.stage_name] = snapshot
        if snapshot.stage_name not in self._history:
            self._history[snapshot.stage_name] = []
        self._history[snapshot.stage_name].append(snapshot)

    def record_run(self, snapshot: PromptSnapshot) -> DriftReport:
        """Records a new prompt snapshot and checks against baseline."""
        stage = snapshot.stage_name
        if stage not in self._history:
            self._history[stage] = []
        self._history[stage].append(snapshot)

        baseline = self._baselines.get(stage)
        if not baseline:
            # Auto-seed baseline on first observation
            self._baselines[stage] = snapshot
            total_tok = snapshot.system_prompt_tokens_est + snapshot.user_prompt_tokens_est
            return DriftReport(
                stage_name=stage,
                is_drift_detected=False,
                is_cache_invalidated=False,
                token_growth_pct=0.0,
                violations=[],
                baseline_tokens=total_tok,
                current_tokens=total_tok,
            )

        violations = []
        # 1. Prompt Bloat Check
        base_tok = baseline.system_prompt_tokens_est + baseline.user_prompt_tokens_est
        curr_tok = snapshot.system_prompt_tokens_est + snapshot.user_prompt_tokens_est
        growth_pct = ((curr_tok - base_tok) / max(1, base_tok)) * 100.0

        is_bloat = growth_pct > self.max_drift_pct
        if is_bloat:
            violations.append(
                f"Prompt bloat detected in '{stage}': token footprint grew by {growth_pct:.1f}% "
                f"(baseline: {base_tok}, current: {curr_tok}, threshold: +{self.max_drift_pct}%)."
            )

        # 2. Surface Node 0 Cache Key Invalidation Check
        is_cache_invalidated = snapshot.surface_node_0_hash != baseline.surface_node_0_hash
        if is_cache_invalidated:
            violations.append(
                f"Prompt cache invalidation in '{stage}': Surface Node 0 hash changed "
                f"from {baseline.surface_node_0_hash} to {snapshot.surface_node_0_hash}."
            )

        report = DriftReport(
            stage_name=stage,
            is_drift_detected=is_bloat,
            is_cache_invalidated=is_cache_invalidated,
            token_growth_pct=growth_pct,
            violations=violations,
            baseline_tokens=base_tok,
            current_tokens=curr_tok,
        )

        if violations:
            logger.warning(f"[TokenDriftTracker] Drift in '{stage}': {'; '.join(violations)}")

        return report

    def get_summary(self) -> Dict[str, Any]:
        """Returns overall token drift summary across tracked stages."""
        summary = {}
        for stage, baseline in self._baselines.items():
            runs = self._history.get(stage, [])
            latest = runs[-1] if runs else baseline
            summary[stage] = {
                "baseline_tokens": baseline.system_prompt_tokens_est + baseline.user_prompt_tokens_est,
                "latest_tokens": latest.system_prompt_tokens_est + latest.user_prompt_tokens_est,
                "total_runs": len(runs),
                "surface_node_0_hash": latest.surface_node_0_hash,
            }
        return summary
