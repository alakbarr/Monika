import pytest
import tempfile
import os
import shutil

from analysis.memory.playbook_linter import PlaybookLinter, PlaybookLintResult
from analysis.memory.playbook_ledger import PlaybookLedger
from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager, PlaybookStatus
from analysis.stages.per_asset.specialist_council import (
    SpecialistCouncil, SpecialistRole, TradeAction, SpecialistVote
)


@pytest.fixture
def temp_playbooks_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# --- PlaybookLinter Tests ---

def test_playbook_linter_valid():
    valid_content = """---
symbol: EURUSD
regime: TRENDING_UP
timeframe: H4
min_rr: 2.0
win_rate: 0.65
---

# Trigger Conditions
- Price closes above H4 swing high with volume expansion > 1.2x 20-period average.
- 20 EMA is above 50 EMA on H4.

# Invalidation & Stop Loss
- Hard Stop Loss placed 1.5x ATR below entry candle low.
- Invalidation if candle closes back inside the previous consolidation range.
"""
    linter = PlaybookLinter(min_rr_threshold=1.5)
    result = linter.lint(valid_content)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.metadata["symbol"] == "EURUSD"
    assert result.metadata["min_rr"] == 2.0


def test_playbook_linter_invalid_rr_and_missing_sections():
    bad_content = """---
symbol: GBPUSD
regime: RANGING
timeframe: H1
min_rr: 0.8
---

Just buy when RSI is low.
"""
    linter = PlaybookLinter(min_rr_threshold=1.5)
    result = linter.lint(bad_content)
    assert result.is_valid is False
    assert any("min_rr" in err for err in result.errors)
    assert any("Missing required structural section" in err for err in result.errors)


def test_playbook_linter_narrative_incident_log_guard():
    incident_content = """---
symbol: USDJPY
regime: BREAKOUT
timeframe: M15
min_rr: 2.0
---

# Trigger Rules
On Tuesday we lost money because CPI spiked before our order filled.
I should have waited for the candle close.

# Invalidation Rules
Stop loss at swing low.
"""
    linter = PlaybookLinter(min_rr_threshold=1.5)
    result = linter.lint(incident_content)
    assert result.is_valid is False
    assert any("Narrative anti-pattern detected" in err for err in result.errors)


# --- PlaybookLifecycleManager Tests ---

def test_playbook_lifecycle_promotion_and_rollback(temp_playbooks_dir):
    ledger = PlaybookLedger(playbooks_dir=temp_playbooks_dir)
    lifecycle = PlaybookLifecycleManager(playbooks_dir=temp_playbooks_dir, ledger=ledger)

    name = "EURUSD_breakout"
    # Seed versions in ledger
    v1_hash = ledger.record_mutation(name, "version 1 content", action="create")
    v2_hash = ledger.record_mutation(name, "version 2 content", action="update")

    # Register as candidate
    meta = lifecycle.register_playbook(name)
    assert meta.status == PlaybookStatus.CANDIDATE

    # Record 5 winning trades to trigger promotion
    for _ in range(5):
        res = lifecycle.record_trade_outcome(name, won=True, pnl=150.0, r_multiple=2.0)

    assert res["status"] == PlaybookStatus.ACTIVE.value
    assert lifecycle.get_status(name) == PlaybookStatus.ACTIVE

    # Now record 3 consecutive losses to trigger demotion and auto-rollback
    for i in range(3):
        res = lifecycle.record_trade_outcome(name, won=False, pnl=-100.0, r_multiple=-1.0)

    assert res["status"] == PlaybookStatus.STALE.value
    assert res["rolled_back"] is True
    assert lifecycle.get_status(name) == PlaybookStatus.STALE


# --- SpecialistCouncil Tests ---

def test_specialist_council_deliberation():
    council = SpecialistCouncil()

    bundle_data = {
        "get_macro_bias_score": 0.6,  # Bullish
        "market_regime": "TRENDING_BULLISH",  # Bullish
        "retail_sentiment": {"long_percentage": 20.0},  # Contrarian Bullish
        "estimated_rr": 2.2,
        "spread_pips": 1.1,
    }

    verdict = council.evaluate(
        symbol="EURUSD",
        regime="TRENDING",
        bundle_data=bundle_data
    )

    assert verdict.action == TradeAction.BUY
    assert verdict.is_approved is True
    assert verdict.consensus_score >= 0.6
    assert len(verdict.negative_constraints_applied) > 0
    assert verdict.execution_parameters.get("order_type") == "MARKET"


def test_specialist_council_risk_arbitrator_veto():
    council = SpecialistCouncil()

    # Sub-optimal R:R triggers Risk Arbitrator veto
    bundle_data = {
        "get_macro_bias_score": 0.8,
        "market_regime": "TRENDING_BULLISH",
        "retail_sentiment": {"long_percentage": 25.0},
        "estimated_rr": 1.1,  # Below 1.5 threshold
        "spread_pips": 1.0,
    }

    verdict = council.evaluate(
        symbol="GBPUSD",
        regime="TRENDING",
        bundle_data=bundle_data
    )

    assert verdict.action == TradeAction.HOLD
    assert verdict.is_approved is False
    assert "VETO by Risk Arbitrator" in verdict.rationale
    assert verdict.specialist_votes["risk_arbitrator"].veto is True
