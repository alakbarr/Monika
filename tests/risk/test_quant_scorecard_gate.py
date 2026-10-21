"""Phase 1: quantitative proposals must carry an explicit, valid scorecard.

The previous implementation accepted any quantitative signal whose confidence was
>= 0.3. That backdoor is removed: a quantitative analysis is only tradable when it
carries a ``quant_scorecard`` that satisfies the canonical risk contract.
"""

from types import SimpleNamespace

import pytest

from monika.core.risk.quant_scorecard import (
    attach_quant_scorecard,
    build_quant_scorecard,
    extract_quant_scorecard,
    validate_quant_scorecard,
)
from monika.domain.risk.risk_gate import RiskGate

MIN_CONFIDENCE = 0.60
MIN_RR = 1.5


def _settings() -> dict:
    return {
        "trading": {
            "auto_execute_min_confluence": 7,
            "auto_execute_min_confidence": MIN_CONFIDENCE,
            "risk": {"min_rr_ratio": MIN_RR},
        }
    }


def _quant_analysis(**overrides):
    analysis = SimpleNamespace(
        symbol="EURUSD",
        decision="buy",
        decision_source="quant_alpha_x",
        source_strategy_id="alpha_x",
        confidence=0.72,
        confluence_factors_json=None,
    )
    for key, value in overrides.items():
        setattr(analysis, key, value)
    return analysis


def _valid_scorecard(**overrides) -> dict:
    scorecard = build_quant_scorecard(
        strategy_id="alpha_x",
        direction="buy",
        confidence=0.72,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    scorecard.update(overrides)
    return scorecard


class TestQuantScorecardBuilder:
    def test_builds_valid_scorecard_from_geometry(self):
        scorecard = _valid_scorecard()
        assert scorecard["valid"] is True
        assert scorecard["direction"] == "buy"
        assert scorecard["rr_ratio"] == pytest.approx(2.0)
        assert scorecard["strategy_id"] == "alpha_x"

    def test_incomplete_geometry_is_invalid(self):
        scorecard = build_quant_scorecard(
            strategy_id="alpha_x",
            direction="buy",
            confidence=0.72,
            entry_price=1.1000,
            stop_loss=None,
            take_profit=1.1100,
        )
        assert scorecard["valid"] is False
        assert scorecard["rr_ratio"] is None

    def test_non_finite_confidence_is_invalid(self):
        scorecard = build_quant_scorecard(
            strategy_id="alpha_x",
            direction="buy",
            confidence=float("nan"),
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
        )
        assert scorecard["valid"] is False
        assert scorecard["confidence"] is None

    def test_attach_and_extract_round_trip(self):
        analysis = _quant_analysis()
        attach_quant_scorecard(analysis, _valid_scorecard())
        extracted = extract_quant_scorecard(analysis)
        assert extracted is not None
        assert extracted["strategy_id"] == "alpha_x"

    def test_extract_returns_none_without_scorecard(self):
        assert extract_quant_scorecard(_quant_analysis()) is None
        assert extract_quant_scorecard(None) is None


class TestQuantScorecardValidation:
    def test_valid_scorecard_passes(self):
        ok, reason = validate_quant_scorecard(_valid_scorecard(), min_confidence=MIN_CONFIDENCE, min_rr_ratio=MIN_RR)
        assert ok is True
        assert "quant_scorecard_ok" in reason

    def test_confidence_below_floor_is_rejected(self):
        scorecard = _valid_scorecard(confidence=0.45)
        ok, reason = validate_quant_scorecard(scorecard, min_confidence=MIN_CONFIDENCE, min_rr_ratio=MIN_RR)
        assert ok is False
        assert "0.45" in reason

    def test_rr_below_floor_is_rejected(self):
        scorecard = _valid_scorecard(rr_ratio=1.2)
        ok, reason = validate_quant_scorecard(scorecard, min_confidence=MIN_CONFIDENCE, min_rr_ratio=MIN_RR)
        assert ok is False
        assert "R:R" in reason

    def test_invalid_flag_is_rejected(self):
        scorecard = _valid_scorecard(valid=False)
        ok, _ = validate_quant_scorecard(scorecard, min_confidence=MIN_CONFIDENCE, min_rr_ratio=MIN_RR)
        assert ok is False

    def test_missing_scorecard_is_rejected(self):
        ok, reason = validate_quant_scorecard(None, min_confidence=MIN_CONFIDENCE, min_rr_ratio=MIN_RR)
        assert ok is False
        assert "missing" in reason


@pytest.mark.asyncio
class TestRiskGateQuantQualityGate:
    async def test_quant_signal_without_scorecard_is_rejected(self):
        gate = RiskGate(_settings())
        passed, reason = await gate._check_analysis_quality_scores(_quant_analysis())
        assert passed is False
        assert "quant_scorecard" in reason

    async def test_quant_signal_with_valid_scorecard_is_accepted(self):
        gate = RiskGate(_settings())
        analysis = _quant_analysis()
        attach_quant_scorecard(analysis, _valid_scorecard())
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is True
        assert "quant_scorecard_ok" in reason

    async def test_legacy_confidence_backdoor_is_closed(self):
        """confidence >= 0.3 must no longer be sufficient without a scorecard."""
        gate = RiskGate(_settings())
        analysis = _quant_analysis(confidence=0.31)
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is False
        assert "quant_scorecard" in reason

    async def test_low_confidence_with_scorecard_is_rejected(self):
        gate = RiskGate(_settings())
        analysis = _quant_analysis(confidence=0.45)
        attach_quant_scorecard(analysis, _valid_scorecard(confidence=0.45))
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is False
        assert "0.45" in reason

    async def test_direction_mismatch_is_rejected(self):
        gate = RiskGate(_settings())
        analysis = _quant_analysis(decision="sell")
        attach_quant_scorecard(analysis, _valid_scorecard())
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is False
        assert "does not match" in reason


@pytest.mark.asyncio
class TestLLMSourcesKeepTheirOwnScorecard:
    """A strategy id on an LLM analysis must not downgrade the LLM scorecard rules."""

    async def test_llm_analysis_with_playbook_id_uses_the_llm_scorecard(self):
        gate = RiskGate(_settings())
        analysis = SimpleNamespace(
            symbol="EURUSD",
            decision="buy",
            decision_source="llm_stage2",
            source_strategy_id="playbook_x",
            strategy_id=None,
            confidence=0.75,
            confluence_score=9,
            priced_in_score=3,
        )
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is True
        assert "quality_scores_ok" in reason

    async def test_concordant_signal_uses_the_llm_scorecard(self):
        gate = RiskGate(_settings())
        analysis = SimpleNamespace(
            symbol="EURUSD",
            decision="buy",
            decision_source="concordant",
            source_strategy_id="alpha_x",
            strategy_id=None,
            confidence=0.75,
            confluence_score=9,
            priced_in_score=3,
        )
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is True
        assert "quality_scores_ok" in reason

    async def test_concordant_signal_still_needs_a_valid_confluence_score(self):
        gate = RiskGate(_settings())
        analysis = SimpleNamespace(
            symbol="EURUSD",
            decision="buy",
            decision_source="concordant",
            source_strategy_id="alpha_x",
            strategy_id=None,
            confidence=0.75,
            confluence_score=5,
            priced_in_score=3,
        )
        passed, reason = await gate._check_analysis_quality_scores(analysis)
        assert passed is False
        assert "confluence_score" in reason
