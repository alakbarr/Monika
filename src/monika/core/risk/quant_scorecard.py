"""Explicit, persisted scorecard for quantitative (non-LLM) trade proposals.

The LLM path has ``confluence_score`` and ``priced_in_score``. Quantitative
strategies do not, so they must carry an equally explicit scorecard before the
RiskGate may approve an execution. The scorecard is stored inside the existing
``AssetAnalysis.confluence_factors_json`` column to avoid an unnecessary schema
migration; the value is a JSON object with a single ``quant_scorecard`` key.
"""

from __future__ import annotations

import json
import math
from typing import Any

QUANT_SCORECARD_KEY = "quant_scorecard"
QUANT_SCORECARD_VERSION = 1

_QUANT_DECISION_SOURCES = ("edge_registry",)


def is_quantitative_source(decision_source: str | None) -> bool:
    """Return True when a decision source is a quantitative (non-LLM) proposal.

    The LLM path carries its own scorecard (``confluence_score`` +
    ``priced_in_score``); quantitative proposals must instead carry an explicit
    ``quant_scorecard``. Detection is based on the decision source only — a
    strategy id on an LLM analysis (playbook id, concordant quant leg) must not
    downgrade the LLM scorecard requirements.
    """
    source = str(decision_source or "").strip().lower()
    if not source:
        return False
    return source in _QUANT_DECISION_SOURCES or source.startswith("quant_")


def is_concordant_source(decision_source: str | None) -> bool:
    """Return True for the concordant source (LLM and quant agreed)."""
    return str(decision_source or "").strip().lower() == "concordant"


def evaluate_analysis_scorecard(
    *,
    decision_source: str | None,
    quant_scorecard: dict[str, Any] | None,
    confluence_score: Any = None,
    priced_in_score: Any = None,
    min_confidence: float,
    min_rr_ratio: float,
    min_confluence: int,
) -> tuple[bool, str]:
    """Single source of truth for the analysis scorecard requirement.

    * Quantitative sources must carry an explicit, valid ``quant_scorecard``.
    * LLM sources must carry the equivalent LLM scorecard (confluence + priced-in).
    * Concordant sources accept either one, because the analysis may originate
      from the LLM leg or from the quant leg (edge-registry analyses are
      relabelled ``concordant`` by the arbitration node).
    """
    source = str(decision_source or "").strip().lower()
    label = source or "analysis"

    if is_quantitative_source(source):
        ok, reason = validate_quant_scorecard(
            quant_scorecard,
            min_confidence=min_confidence,
            min_rr_ratio=min_rr_ratio,
        )
        return (True, reason) if ok else (False, f"{label}: {reason}")

    llm_scorecard_present = confluence_score is not None and priced_in_score is not None

    if is_concordant_source(source) and not llm_scorecard_present:
        ok, reason = validate_quant_scorecard(
            quant_scorecard,
            min_confidence=min_confidence,
            min_rr_ratio=min_rr_ratio,
        )
        return (True, reason) if ok else (False, f"{label}: {reason}")

    if confluence_score is None:
        return (
            False,
            f"confluence_score is None. Model did not fill required scorecard. Blocking execution.",
        )

    if priced_in_score is None:
        return (
            False,
            f"priced_in_score is None. Priced-in assessment not completed. Blocking execution.",
        )

    if float(priced_in_score) >= 8:
        return (
            False,
            f"priced_in_score={priced_in_score} >= 8. Event fully priced in (score >= 8) — "
            "high sell-the-news reversal risk.",
        )

    if float(confluence_score) < int(min_confluence):
        return (
            False,
            f"confluence_score={confluence_score} < {int(min_confluence)} (adaptive policy threshold).",
        )

    return (
        True,
        f"quality_scores_ok(confluence={confluence_score}, priced_in={priced_in_score}, "
        f"threshold={int(min_confluence)})",
    )


_REQUIRED_FIELDS = (
    "strategy_id",
    "direction",
    "confidence",
    "rr_ratio",
    "valid",
    "scorecard_version",
)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except TypeError, ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _risk_reward(entry: Any, stop_loss: Any, take_profit: Any, direction: str | None = None) -> float | None:
    entry_f = _finite_float(entry)
    sl_f = _finite_float(stop_loss)
    tp_f = _finite_float(take_profit)
    if entry_f is None or sl_f is None or tp_f is None:
        return None

    dir_clean = str(direction or "").strip().lower()
    if dir_clean == "buy":
        if not (sl_f < entry_f < tp_f):
            return None
        risk = entry_f - sl_f
        reward = tp_f - entry_f
    elif dir_clean == "sell":
        if not (tp_f < entry_f < sl_f):
            return None
        risk = sl_f - entry_f
        reward = entry_f - tp_f
    else:
        risk = abs(entry_f - sl_f)
        reward = abs(tp_f - entry_f)

    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 6)


def build_quant_scorecard(
    *,
    strategy_id: str | None,
    direction: str | None,
    confidence: Any,
    entry_price: Any = None,
    stop_loss: Any = None,
    take_profit: Any = None,
    regime: str | None = None,
    evidence_status: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic scorecard from the strategy's executable signal.

    Invalid or incomplete data is represented by ``valid=False``; callers must
    never treat a malformed scorecard as an approval.
    """
    normalized_direction = str(direction or "").strip().lower()
    confidence_f = _finite_float(confidence)
    rr_ratio = _risk_reward(entry_price, stop_loss, take_profit, direction=normalized_direction)
    valid = bool(
        strategy_id
        and normalized_direction in ("buy", "sell")
        and confidence_f is not None
        and 0.0 <= confidence_f <= 1.0
        and rr_ratio is not None
        and rr_ratio > 0.0
    )
    return {
        "scorecard_version": QUANT_SCORECARD_VERSION,
        "strategy_id": str(strategy_id or ""),
        "direction": normalized_direction,
        "confidence": confidence_f,
        "rr_ratio": rr_ratio,
        "valid": valid,
        "regime": str(regime or "UNKNOWN"),
        "evidence_status": str(evidence_status or "unknown"),
    }


def attach_quant_scorecard(analysis: Any, scorecard: dict[str, Any]) -> None:
    """Persist a scorecard on an ``AssetAnalysis`` using the existing JSON column."""
    if analysis is None:
        raise ValueError("analysis is required to attach a quant scorecard")
    analysis.confluence_factors_json = json.dumps({QUANT_SCORECARD_KEY: scorecard}, sort_keys=True)


def extract_quant_scorecard(analysis: Any) -> dict[str, Any] | None:
    """Return the explicit scorecard, or ``None`` when it is missing/malformed."""
    if analysis is None:
        return None
    raw = getattr(analysis, "confluence_factors_json", None)
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except TypeError, ValueError, json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    scorecard = parsed.get(QUANT_SCORECARD_KEY)
    return scorecard if isinstance(scorecard, dict) else None


def validate_quant_scorecard(
    scorecard: dict[str, Any] | None,
    *,
    min_confidence: float,
    min_rr_ratio: float,
) -> tuple[bool, str]:
    """Validate an explicit quant scorecard against the canonical risk contract."""
    if not isinstance(scorecard, dict):
        return False, "quant_scorecard missing or malformed; execution blocked."

    missing = [key for key in _REQUIRED_FIELDS if key not in scorecard]
    if missing:
        return False, f"quant_scorecard missing required fields: {', '.join(missing)}."

    if scorecard.get("valid") is not True:
        return False, "quant_scorecard is marked invalid; execution blocked."

    if int(scorecard.get("scorecard_version") or 0) != QUANT_SCORECARD_VERSION:
        return False, "quant_scorecard version is unsupported; execution blocked."

    if not str(scorecard.get("strategy_id") or "").strip():
        return False, "quant_scorecard has no strategy_id; execution blocked."

    if str(scorecard.get("direction") or "").lower() not in ("buy", "sell"):
        return False, "quant_scorecard has no actionable direction; execution blocked."

    confidence = _finite_float(scorecard.get("confidence"))
    if confidence is None:
        return False, "quant_scorecard confidence is missing/non-finite; execution blocked."
    if confidence < float(min_confidence):
        return (
            False,
            f"quant_scorecard confidence {confidence:.2f} < {float(min_confidence):.2f}; execution blocked.",
        )

    rr_ratio = _finite_float(scorecard.get("rr_ratio"))
    if rr_ratio is None:
        return False, "quant_scorecard R:R is missing/non-finite; execution blocked."
    if rr_ratio < float(min_rr_ratio):
        return (
            False,
            f"quant_scorecard R:R {rr_ratio:.2f} < {float(min_rr_ratio):.2f}; execution blocked.",
        )

    return True, (
        f"quant_scorecard_ok(strategy={scorecard.get('strategy_id')}, confidence={confidence:.2f}, rr={rr_ratio:.2f})"
    )


__all__ = [
    "QUANT_SCORECARD_KEY",
    "QUANT_SCORECARD_VERSION",
    "attach_quant_scorecard",
    "build_quant_scorecard",
    "evaluate_analysis_scorecard",
    "extract_quant_scorecard",
    "is_concordant_source",
    "is_quantitative_source",
    "validate_quant_scorecard",
]
