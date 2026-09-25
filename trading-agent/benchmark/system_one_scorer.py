"""
Deterministic scorer for System One models — evaluates accuracy, latency, calibration, and schema adherence.
Zero LLM Judge cost — 100% reproducible and fast.
"""

from typing import Any, Dict, List, Optional
from benchmark.config import (
    S1_WEIGHT_ACCURACY,
    S1_WEIGHT_LATENCY,
    S1_WEIGHT_CALIBRATION,
    S1_WEIGHT_SCHEMA,
    S1_LATENCY_TARGET_MS,
    S1_LATENCY_CEILING_MS,
)


def _score_accuracy(output: Dict[str, Any], expected: Dict[str, Any], questions: Optional[List[Dict[str, Any]]]) -> float:
    """Calculates accuracy (0.0 - 10.0) based on exact/directional matches against expected answers."""
    if not output or not expected:
        return 0.0

    matches = 0
    total_checks = 0

    for key, exp_val in expected.items():
        if key.endswith("_confidence_min") or key.endswith("_tolerance"):
            continue

        total_checks += 1
        out_val = output.get(key)
        if out_val is None:
            continue

        # Exact match (bool, str enum, int score)
        if out_val == exp_val:
            matches += 1
        elif isinstance(exp_val, str) and isinstance(out_val, str) and exp_val.lower() == out_val.lower():
            matches += 1
        elif isinstance(exp_val, (int, float)) and isinstance(out_val, (int, float)):
            tol = expected.get(f"{key}_tolerance", 0.0)
            if abs(out_val - exp_val) <= tol:
                matches += 1

    return round((matches / total_checks) * 10.0, 2) if total_checks > 0 else 0.0


def _score_latency(latency_s: float, target_ms: float = S1_LATENCY_TARGET_MS, ceiling_ms: float = S1_LATENCY_CEILING_MS) -> float:
    """
    Evaluates sub-second latency performance (0.0 - 10.0).
    <= target_ms -> 10.0
    >= ceiling_ms -> 0.0
    Linear decay between target and ceiling.
    """
    latency_ms = latency_s * 1000.0
    if latency_ms <= target_ms:
        return 10.0
    if latency_ms >= ceiling_ms:
        return 0.0
    decay_range = ceiling_ms - target_ms
    score = 10.0 * (1.0 - (latency_ms - target_ms) / decay_range)
    return round(max(0.0, min(10.0, score)), 2)


def _score_calibration(output: Dict[str, Any], expected: Dict[str, Any]) -> float:
    """
    Evaluates confidence calibration (0.0 - 10.0).
    Rewards high confidence when correct, penalizes overconfidence on incorrect predictions.
    """
    if not output or not expected:
        return 0.0

    brier_terms = []
    for key, exp_val in expected.items():
        if key.endswith("_confidence_min"):
            base_key = key.replace("_confidence_min", "")
            out_conf = output.get(f"{base_key}_confidence", output.get("confidence", 1.0))
            try:
                out_conf = float(out_conf)
            except (ValueError, TypeError):
                out_conf = 0.5
            out_conf = max(0.0, min(1.0, out_conf))

            # Did the model match the expected target?
            is_correct = (output.get(base_key) == expected.get(base_key))
            outcome = 1.0 if is_correct else 0.0
            brier_terms.append((out_conf - outcome) ** 2)

    if not brier_terms:
        return 10.0  # No explicit calibration requirements

    mean_brier = sum(brier_terms) / len(brier_terms)
    # Brier score ranges from 0.0 (perfect) to 1.0 (completely miscalibrated)
    cal_score = max(0.0, (1.0 - mean_brier) * 10.0)
    return round(cal_score, 2)


def _score_schema(output: Dict[str, Any], questions: Optional[List[Dict[str, Any]]]) -> float:
    """Evaluates strict adherence to structured types and zero prose leakage (0.0 - 10.0)."""
    if not isinstance(output, dict) or not output:
        return 0.0

    score = 10.0
    # Deduct for missing questions
    if questions:
        for q in questions:
            q_name = q.get("name") if isinstance(q, dict) else str(q)
            if q_name and q_name not in output:
                score -= 2.5

    # Check for unwanted raw text dumps / prose leakage
    raw_text = str(output)
    if "```" in raw_text or "Here is the analysis" in raw_text:
        score -= 3.0

    return max(0.0, round(score, 2))


def score_system_one(
    output: Dict[str, Any],
    expected: Dict[str, Any],
    latency_s: float,
    questions: Optional[List[Dict[str, Any]]] = None,
    target_latency_ms: float = S1_LATENCY_TARGET_MS,
) -> Dict[str, Any]:
    """
    Complete composite evaluation for System One decision-making outputs.
    """
    acc = _score_accuracy(output, expected, questions)
    lat = _score_latency(latency_s, target_ms=target_latency_ms)
    cal = _score_calibration(output, expected)
    sch = _score_schema(output, questions)

    overall = (
        S1_WEIGHT_ACCURACY * acc
        + S1_WEIGHT_LATENCY * lat
        + S1_WEIGHT_CALIBRATION * cal
        + S1_WEIGHT_SCHEMA * sch
    )

    return {
        "accuracy_score": acc,
        "latency_score": lat,
        "calibration_score": cal,
        "schema_score": sch,
        "overall_score": round(overall, 2),
        "latency_ms": round(latency_s * 1000.0, 1),
        "target_latency_ms": target_latency_ms,
    }
