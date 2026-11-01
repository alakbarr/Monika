import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.graph.state import TradingState
from monika.application.graph.nodes.debate_node import debate_node
from monika.application.graph.nodes.debate.debate_judge_node import debate_judge_node


@pytest.mark.asyncio
async def test_debate_node_bypass():
    state = TradingState(
        actionable_trades=[("BTCUSD", {"analysis_id": 1})],
        summary={},
        debate_states={},
        risk_debate_states={},
        investment_verdicts={},
        portfolio_decisions={},
    )

    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": False}})}}

    result = await debate_node(state, config)
    assert result == {}


@pytest.mark.asyncio
async def test_debate_node_empty_actionable():
    state = TradingState(
        actionable_trades=[],
        summary={},
        debate_states={},
        risk_debate_states={},
        investment_verdicts={},
        portfolio_decisions={},
    )

    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}

    result = await debate_node(state, config)
    assert result == {}


@pytest.mark.asyncio
async def test_debate_judge_promotes_wait_candidate_with_long_bracket_to_sell():
    """When a WAIT candidate pre-populated with LONG_OPTION_A is promoted to SELL without adjusted_sl/tp,
    debate_judge_node must assign valid SELL geometry (SL > Entry > TP)."""
    mock_ana = MagicMock()
    mock_ana.id = 2501
    mock_ana.decision = "wait"
    mock_ana.confidence = 0.55
    mock_ana.confluence_score = 9
    mock_ana.price_at_analysis = 1.1000
    mock_ana.entry_zone = '{"type": "market", "price": 1.1000}'
    # Pre-populated with LONG_OPTION_A (SL < Entry < TP)
    mock_ana.stop_loss = 1.0950
    mock_ana.take_profit = 1.1080
    mock_ana.risk_multiplier = 1.0
    mock_ana.was_debate_modified = False

    class MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a):
            return mock_ana

        def add(self, *a):
            pass

        async def commit(self):
            pass

    cand = {
        "analysis_id": 2501,
        "decision": "wait",
        "price_at_analysis": 1.1000,
        "bracket_options": {
            "long_option_a": {"entry": 1.1000, "stop_loss": 1.0950, "take_profit": 1.1080},
            "short_option_b": {"entry": 1.1000, "stop_loss": 1.1050, "take_profit": 1.0920},
        },
    }
    state = {
        "actionable_trades": [("EURUSD", cand)],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"thesis": "bull", "strength_score": 6},
                "bear_dissent": {"dissent": "bear", "risk_severity": 8},
                "original_context": {"decision": "wait", "price_at_analysis": 1.1000},
                "fact_sheet": {"symbol": "EURUSD", "atr": 0.0050},
            }
        },
        "investment_verdicts": {},
        "summary": {},
    }
    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}

    with (
        patch("monika.application.graph.nodes.debate.debate_judge_node.get_session", side_effect=MockSession),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.evaluate_debate",
            AsyncMock(return_value={"final_decision": "sell", "reason": "Bear case stronger", "confidence": 0.72}),
        ),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.validate_and_apply_judge_adjustments",
            AsyncMock(return_value=(True, None)),
        ),
    ):
        res = await debate_judge_node(state, config)

    assert mock_ana.decision == "sell"
    assert mock_ana.stop_loss > 1.1000 > mock_ana.take_profit
    assert mock_ana.stop_loss == pytest.approx(1.1050)
    assert mock_ana.take_profit == pytest.approx(1.0920)
    assert len(res["actionable_trades"]) == 1
    assert res["actionable_trades"][0][1]["decision"] == "sell"


@pytest.mark.asyncio
async def test_debate_judge_demotes_rejected_trade_on_wait_or_avoid():
    """When Judge rules 'wait' or 'avoid' on a candidate that was previously 'sell', ana.decision is updated to 'wait'."""
    mock_ana = MagicMock()
    mock_ana.id = 2368
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.70
    mock_ana.confluence_score = 8
    mock_ana.price_at_analysis = 152.50
    mock_ana.entry_zone = '{"type": "market", "price": 152.50}'
    mock_ana.stop_loss = 153.20
    mock_ana.take_profit = 151.30
    mock_ana.risk_multiplier = 1.0

    class MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a):
            return mock_ana

        def add(self, *a):
            pass

        async def commit(self):
            pass

    state = {
        "actionable_trades": [("USDJPY", {"analysis_id": 2368, "decision": "sell"})],
        "debate_states": {
            "USDJPY": {
                "verified_bull_claim": {"thesis": "bull", "strength_score": 7},
                "bear_dissent": {"dissent": "bear", "risk_severity": 8},
                "original_context": {"decision": "sell", "rationale": "test"},
                "fact_sheet": {"symbol": "USDJPY"},
            }
        },
        "investment_verdicts": {},
        "summary": {},
    }
    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}

    with (
        patch("monika.application.graph.nodes.debate.debate_judge_node.get_session", side_effect=MockSession),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.evaluate_debate",
            AsyncMock(return_value={"final_decision": "wait", "reason": "Conflicting yield signals"}),
        ),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.validate_and_apply_judge_adjustments",
            AsyncMock(return_value=(True, None)),
        ),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.DecisionLogger.log_paper_whatif",
            AsyncMock(),
        ),
    ):
        res = await debate_judge_node(state, config)

    assert mock_ana.decision == "wait"
    assert res["actionable_trades"] == []
