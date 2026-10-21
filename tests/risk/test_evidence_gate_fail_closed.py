"""Phase 1: the strategy evidence gate must fail closed.

Previously the gate returned True when the analysis was missing or the evidence
store could not be reached, which silently allowed unproven strategies to trade.
"""

from types import SimpleNamespace

import pytest

from monika.domain.risk.risk_gate import RiskGate


class _EligibleStore:
    def validate_strategy_for_trade(self, strategy_id: str, regime: str = "UNKNOWN"):
        return True, "Approved by Evidence Gate"

    def is_strategy_eligible_to_trade(self, strategy_id: str, min_breakeven_bps: float = 3.0):
        return True, "Approved by Evidence Gate"


class _IneligibleStore:
    def validate_strategy_for_trade(self, strategy_id: str, regime: str = "UNKNOWN"):
        return False, "No verified backtest evidence on file for alpha_x"

    def is_strategy_eligible_to_trade(self, strategy_id: str, min_breakeven_bps: float = 3.0):
        return False, "No verified backtest evidence on file for alpha_x"


def _analysis():
    return SimpleNamespace(
        symbol="EURUSD",
        source_strategy_id="alpha_x",
        strategy_id=None,
        market_regime_at_analysis=None,
        market_regime="ranging",
    )


@pytest.mark.asyncio
class TestEvidenceGateFailsClosed:
    async def test_missing_analysis_is_rejected(self, monkeypatch):
        monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: _EligibleStore())
        gate = RiskGate({"trading": {"risk": {}}})
        passed, reason = await gate._check_evidence_gate(None, "EURUSD", analysis=None)
        assert passed is False
        assert "fail-closed" in reason

    async def test_unavailable_evidence_store_is_rejected(self, monkeypatch):
        monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: None)
        gate = RiskGate({"trading": {"risk": {}}})
        passed, reason = await gate._check_evidence_gate(None, "EURUSD", analysis=_analysis())
        assert passed is False
        assert "evidence store unavailable" in reason

    async def test_unproven_strategy_is_rejected(self, monkeypatch):
        monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: _IneligibleStore())
        gate = RiskGate({"trading": {"risk": {}}})
        passed, reason = await gate._check_evidence_gate(None, "EURUSD", analysis=_analysis())
        assert passed is False
        assert "EvidenceStore rejected trade" in reason

    async def test_proven_strategy_is_accepted(self, monkeypatch):
        monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: _EligibleStore())
        gate = RiskGate({"trading": {"risk": {}}})
        passed, reason = await gate._check_evidence_gate(None, "EURUSD", analysis=_analysis())
        assert passed is True
        assert "passed regime evidence" in reason

    async def test_backtest_mode_still_skips_the_gate(self, monkeypatch):
        monkeypatch.setattr("monika.domain.risk.ports.get_default_evidence_store", lambda: None)
        gate = RiskGate({"trading": {"risk": {}}})
        passed, reason = await gate._check_evidence_gate(None, "EURUSD", analysis=None, is_backtest=True)
        assert passed is True
        assert "backtest" in reason
