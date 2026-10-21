"""Phase 1: strategy promotion must come from the evidence store, never from code.

The hardcoded ``PROMOTED_EMPIRICAL_STRATEGIES`` whitelist used to grant a strategy
the right to override the LLM and to be reported as VALIDATED. Promotion is now
decided exclusively by the strategy evidence store.
"""

from pathlib import Path

import pytest

from monika.application.analysis.strategies.base_strategy import (
    PROMOTED_EMPIRICAL_STRATEGIES as BASE_PROMOTED,
    StrategyTier,
)
from monika.application.analysis.strategies.registry import (
    PROMOTED_EMPIRICAL_STRATEGIES,
    StrategyRegistry,
)

ARBITRATOR_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "monika"
    / "application"
    / "analysis"
    / "arbitration"
    / "signal_arbitrator.py"
)


class _EvidenceStore:
    def __init__(self, eligible: set[str]):
        self.eligible = eligible

    def is_strategy_eligible_to_trade(self, strategy_id: str, min_breakeven_bps: float = 3.0):
        if strategy_id in self.eligible:
            return True, "Approved by Evidence Gate"
        return False, f"No verified backtest evidence on file for {strategy_id}"

    def validate_strategy_for_trade(self, strategy_id: str, regime: str = "UNKNOWN"):
        return self.is_strategy_eligible_to_trade(strategy_id)


def test_no_hardcoded_promotion_whitelist_remains():
    assert PROMOTED_EMPIRICAL_STRATEGIES == set()
    assert BASE_PROMOTED == set()
    assert not hasattr(StrategyRegistry, "PROMOTED_EMPIRICAL_STRATEGIES")


def test_arbitrator_has_no_promotion_whitelist_reference():
    source = ARBITRATOR_SOURCE.read_text(encoding="utf-8")
    assert "PROMOTED_EMPIRICAL_STRATEGIES" not in source
    assert "has_decisive_conviction" not in source


def test_tier_is_experimental_without_evidence(monkeypatch):
    monkeypatch.setattr(
        "monika.domain.risk.ports.get_default_evidence_store",
        lambda: _EvidenceStore(set()),
    )
    assert StrategyRegistry.get_tier("tokyo_open_sweep") == StrategyTier.EXPERIMENTAL


def test_tier_is_validated_with_evidence(monkeypatch):
    monkeypatch.setattr(
        "monika.domain.risk.ports.get_default_evidence_store",
        lambda: _EvidenceStore({"tokyo_open_sweep"}),
    )
    assert StrategyRegistry.get_tier("tokyo_open_sweep") == StrategyTier.VALIDATED
    assert StrategyRegistry.get_tier("smt_divergence") == StrategyTier.EXPERIMENTAL


def test_quarantine_has_priority_over_evidence(monkeypatch):
    monkeypatch.setattr(
        "monika.domain.risk.ports.get_default_evidence_store",
        lambda: _EvidenceStore({"smc_fvg"}),
    )
    assert StrategyRegistry.get_tier("smc_fvg") == StrategyTier.QUARANTINED


def test_missing_evidence_store_fails_closed(monkeypatch):
    monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: None)
    assert StrategyRegistry.get_tier("tokyo_open_sweep") == StrategyTier.EXPERIMENTAL
