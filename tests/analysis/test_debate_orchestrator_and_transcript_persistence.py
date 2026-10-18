import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.debate.blackboard import DebateBlackboard
from monika.application.analysis.debate.debate_orchestrator import DebateOrchestrator
from monika.application.analysis.debate.deterministic_risk import (
    analyze_risk_conservative,
    make_portfolio_decision_deterministic,
)
from monika.infrastructure.database.models import DebateTranscript
from tests.conftest import create_mock_async_session


def test_debate_blackboard_pip_distance_overlap():
    bb = DebateBlackboard(symbol="EURUSD")
    bb.add_bull_thesis(
        thesis="Bullish support bounce",
        key_levels=[1.08500, 1.09200],
        confidence=0.75,
    )
    # Bear level is 0.2 pips away (within 2 pips tolerance for EURUSD)
    bb.add_bear_thesis(
        thesis="Bearish resistance rejection",
        key_levels=[1.08502, 1.07800],
        confidence=0.70,
    )

    contradictions = bb.extract_sparse_contradictions()
    contested = [c for c in contradictions if c.get("type") == "contested_price_levels"]
    assert len(contested) == 1
    assert 1.08501 in contested[0]["levels"]


def test_deterministic_risk_conservative_unilateral_veto():
    # Scenario: Daily drawdown exceeded -1.5%
    ctx = {
        "actual_risk_state": {
            "daily_pnl_pct": -1.8,
            "open_positions": 1,
            "portfolio_heat_pct": 1.2,
        },
        "confluence_score": 10,
    }
    cons_res = analyze_risk_conservative(ctx)
    assert cons_res["veto_trade"] is True

    # Even if Aggressive and Neutral want to trade aggressively:
    risk_states = {
        "conservative": cons_res,
        "aggressive": {"recommended_multiplier": 1.6, "veto_trade": False},
        "neutral": {"recommended_multiplier": 1.0, "veto_trade": False},
    }
    pm_decision = make_portfolio_decision_deterministic(risk_states)
    assert pm_decision["approval"] is False
    assert pm_decision["recommended_risk_multiplier"] == 0.0
    assert "Conservative persona enforced unilateral veto" in pm_decision["reason"]


@pytest.mark.asyncio
async def test_debate_orchestrator_neutral_context_and_persistence():
    session = create_mock_async_session()
    orchestrator = DebateOrchestrator()

    mock_client = MagicMock()
    del mock_client.classify_json
    mock_client.generate_content = AsyncMock(
        side_effect=[
            # Bull advocacy response
            '{"bull_thesis": "Strong upward momentum", "strength_score": 8, "evidence_cited": ["ATR=1.5"]}',
            # Bear dissent response
            '{"bear_dissent": "Major supply block overhead", "risk_severity": 6, "evidence_cited": ["ATR=1.5"]}',
            # Judge evaluation response
            '{"reason": "Cautious upside", "risk_multiplier": 0.8, "final_decision": "buy", "confidence": 0.72}',
        ]
    )

    with patch("monika.application.analysis.debate.debate_orchestrator.get_client_for_task", return_value=mock_client):
        res = await orchestrator.run_symbol_debate(
            symbol="EURUSD",
            market_data={
                "cycle_id": "deb_cycle_99",
                "vix": 18.5,
            },
            session=session,
        )

        assert res["decision"] == "BUY"
        assert res["confidence"] == 0.72
        assert session.add.called
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, DebateTranscript)
        assert added_obj.symbol == "EURUSD"
        assert added_obj.cycle_id == "deb_cycle_99"
        assert added_obj.final_decision == "buy"
