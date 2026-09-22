"""
File: evals/eval_metrics.py
PR-12: Core Evaluation Metrics & A/B Comparison Engine for Monika.
Calculates directional accuracy, R:R capture, grounding pass rates,
Brier score calibration, and token/cost efficiency deltas.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import math


@dataclass
class DecisionEvaluation:
    scenario_id: str
    symbol: str
    decision: str
    is_valid_direction: bool
    confluence_score: Optional[float] = None
    grounding_passed: bool = True
    grounding_errors: List[str] = field(default_factory=list)
    oracle_passed: bool = True
    oracle_violations: List[str] = field(default_factory=list)
    planned_rr: Optional[float] = None
    realized_rr: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass
class AggregateMetrics:
    total_scenarios: int
    valid_direction_count: int
    directional_accuracy_pct: float
    grounding_pass_rate_pct: float
    oracle_pass_rate_pct: float
    avg_planned_rr: float
    brier_score: float
    total_tokens: int
    total_cost_usd: float
    avg_latency_ms: float


@dataclass
class ABReport:
    name: str
    baseline: AggregateMetrics
    candidate: AggregateMetrics
    delta_accuracy_pct: float
    delta_grounding_pct: float
    delta_oracle_pct: float
    token_savings_pct: float
    cost_savings_pct: float
    latency_change_pct: float
    recommendation: str  # "PROMOTE", "REJECT", "INCONCLUSIVE"
    summary_markdown: str


def compute_brier_score(decisions: List[DecisionEvaluation]) -> float:
    """
    Computes Brier Score: (1/N) * sum((forecast - outcome)^2).
    Lower is better (0.0 = perfect calibration, 1.0 = completely wrong).
    """
    if not decisions:
        return 0.0
    
    total_sq_err = 0.0
    for d in decisions:
        conf = (d.confluence_score / 100.0) if d.confluence_score is not None else 0.5
        conf = max(0.0, min(1.0, conf))
        outcome = 1.0 if d.is_valid_direction and d.oracle_passed else 0.0
        total_sq_err += (conf - outcome) ** 2
        
    return round(total_sq_err / len(decisions), 4)


def aggregate_eval_metrics(decisions: List[DecisionEvaluation]) -> AggregateMetrics:
    """
    Aggregates per-scenario evaluations into a cohesive metrics summary.
    """
    n = len(decisions)
    if n == 0:
        return AggregateMetrics(
            total_scenarios=0,
            valid_direction_count=0,
            directional_accuracy_pct=0.0,
            grounding_pass_rate_pct=0.0,
            oracle_pass_rate_pct=0.0,
            avg_planned_rr=0.0,
            brier_score=0.0,
            total_tokens=0,
            total_cost_usd=0.0,
            avg_latency_ms=0.0,
        )

    valid_dir = sum(1 for d in decisions if d.is_valid_direction)
    ground_pass = sum(1 for d in decisions if d.grounding_passed)
    oracle_pass = sum(1 for d in decisions if d.oracle_passed)

    rr_list = [d.planned_rr for d in decisions if d.planned_rr is not None and d.planned_rr > 0]
    avg_rr = round(sum(rr_list) / len(rr_list), 2) if rr_list else 0.0

    brier = compute_brier_score(decisions)
    tot_tokens = sum(d.input_tokens + d.output_tokens for d in decisions)
    tot_cost = round(sum(d.cost_usd for d in decisions), 6)
    avg_lat = round(sum(d.latency_ms for d in decisions) / n, 1)

    return AggregateMetrics(
        total_scenarios=n,
        valid_direction_count=valid_dir,
        directional_accuracy_pct=round((valid_dir / n) * 100.0, 1),
        grounding_pass_rate_pct=round((ground_pass / n) * 100.0, 1),
        oracle_pass_rate_pct=round((oracle_pass / n) * 100.0, 1),
        avg_planned_rr=avg_rr,
        brier_score=brier,
        total_tokens=tot_tokens,
        total_cost_usd=tot_cost,
        avg_latency_ms=avg_lat,
    )


def compare_ab_evaluations(
    baseline_results: List[DecisionEvaluation],
    candidate_results: List[DecisionEvaluation],
    name: str = "A/B Comparison",
) -> ABReport:
    """
    Compares baseline vs candidate runs and computes relative performance deltas.
    Formulates a clear promotion recommendation.
    """
    base_agg = aggregate_eval_metrics(baseline_results)
    cand_agg = aggregate_eval_metrics(candidate_results)

    delta_acc = round(cand_agg.directional_accuracy_pct - base_agg.directional_accuracy_pct, 1)
    delta_grnd = round(cand_agg.grounding_pass_rate_pct - base_agg.grounding_pass_rate_pct, 1)
    delta_orc = round(cand_agg.oracle_pass_rate_pct - base_agg.oracle_pass_rate_pct, 1)

    # Token & cost savings (% less than baseline)
    tok_save = 0.0
    if base_agg.total_tokens > 0:
        tok_save = round(((base_agg.total_tokens - cand_agg.total_tokens) / base_agg.total_tokens) * 100.0, 1)

    cost_save = 0.0
    if base_agg.total_cost_usd > 0:
        cost_save = round(((base_agg.total_cost_usd - cand_agg.total_cost_usd) / base_agg.total_cost_usd) * 100.0, 1)

    lat_chg = 0.0
    if base_agg.avg_latency_ms > 0:
        lat_chg = round(((cand_agg.avg_latency_ms - base_agg.avg_latency_ms) / base_agg.avg_latency_ms) * 100.0, 1)

    # Recommendation heuristic:
    # PROMOTE if accuracy is not degraded (>= -1%) and (oracle pass improves or token/cost saves >= 10%)
    # REJECT if directional accuracy drops significantly (< -3%) or oracle pass rate drops (< -3%)
    if delta_acc < -3.0 or delta_orc < -3.0 or delta_grnd < -5.0:
        recommendation = "REJECT"
    elif delta_acc >= 0.0 and delta_orc >= 0.0 and (delta_acc > 0 or delta_orc > 0 or tok_save >= 10.0 or cost_save >= 10.0):
        recommendation = "PROMOTE"
    elif delta_acc >= -1.0 and delta_orc >= 0.0 and tok_save >= 15.0:
        recommendation = "PROMOTE"
    else:
        recommendation = "INCONCLUSIVE"

    md = f"""### A/B Evaluation Report: {name}

| Metric | Baseline | Candidate | Delta |
|---|---|---|---|
| **Directional Accuracy** | {base_agg.directional_accuracy_pct}% | {cand_agg.directional_accuracy_pct}% | {delta_acc:+0.1f}% |
| **Oracle Pass Rate** | {base_agg.oracle_pass_rate_pct}% | {cand_agg.oracle_pass_rate_pct}% | {delta_orc:+0.1f}% |
| **Grounding Pass Rate** | {base_agg.grounding_pass_rate_pct}% | {cand_agg.grounding_pass_rate_pct}% | {delta_grnd:+0.1f}% |
| **Brier Score** | {base_agg.brier_score} | {cand_agg.brier_score} | {round(cand_agg.brier_score - base_agg.brier_score, 4):+0.4f} |
| **Average Planned R:R** | {base_agg.avg_planned_rr} | {cand_agg.avg_planned_rr} | {round(cand_agg.avg_planned_rr - base_agg.avg_planned_rr, 2):+0.2f} |
| **Total Tokens** | {base_agg.total_tokens} | {cand_agg.total_tokens} | {tok_save:+0.1f}% savings |
| **Total Cost** | ${base_agg.total_cost_usd:.4f} | ${cand_agg.total_cost_usd:.4f} | {cost_save:+0.1f}% savings |
| **Avg Latency** | {base_agg.avg_latency_ms}ms | {cand_agg.avg_latency_ms}ms | {lat_chg:+0.1f}% |

**Recommendation**: **{recommendation}**
"""

    return ABReport(
        name=name,
        baseline=base_agg,
        candidate=cand_agg,
        delta_accuracy_pct=delta_acc,
        delta_grounding_pct=delta_grnd,
        delta_oracle_pct=delta_orc,
        token_savings_pct=tok_save,
        cost_savings_pct=cost_save,
        latency_change_pct=lat_chg,
        recommendation=recommendation,
        summary_markdown=md,
    )
