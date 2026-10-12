# ==============================================================================
# File: tests/test_debate_concurrency.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graph.nodes.debate_node import debate_node
from database.models import AssetAnalysis


@pytest.mark.asyncio
async def test_debate_parallel_execution():
    """Verify that multi-asset debate runs concurrently with Semaphore(3)."""
    concurrent_active = 0
    max_concurrent = 0

    async def mock_advocacy(*args, **kwargs):
        nonlocal concurrent_active, max_concurrent
        concurrent_active += 1
        max_concurrent = max(max_concurrent, concurrent_active)
        await asyncio.sleep(0.05)
        concurrent_active -= 1
        return {"claim": "bullish", "strength_score": 7}

    async def mock_dissent(*args, **kwargs):
        return {"dissent": "none", "risk_severity": 3}

    async def mock_eval(*args, **kwargs):
        return {"final_decision": "buy", "reason": "strong confluence", "risk_multiplier": 1.0}

    state = {
        "summary": {},
        "actionable_trades": [
            ("EURUSD", {"analysis_id": 1, "decision": "buy", "confidence": 0.8}),
            ("GBPUSD", {"analysis_id": 2, "decision": "buy", "confidence": 0.75}),
            ("AUDUSD", {"analysis_id": 3, "decision": "buy", "confidence": 0.7}),
            ("USDJPY", {"analysis_id": 4, "decision": "sell", "confidence": 0.85}),
        ],
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "user_market_intel": [],
    }

    config = {
        "configurable": {
            "scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True, "deterministic_risk_gate": True}})
        }
    }

    class MockAnalysis:
        def __init__(self, aid, sym, dec):
            self.id = aid
            self.symbol = sym
            self.decision = dec
            self.rationale = "Test rationale"
            self.confidence = 0.8
            self.confluence_score = 4
            self.confluence_factors_json = '["trend", "fvg"]'
            self.entry_zone = '{"price": 1.1000}'
            self.stop_loss = 1.0950
            self.take_profit = 1.1100
            self.invalidation = "1.0940"
            self.price_at_analysis = 1.1000
            self.priced_in_score = 10
            self.risk_multiplier = 1.0
            self.context_snapshot_id = None
            self.ssvp_cds_score_at_analysis = None
            self.debate_bull_thesis = None
            self.debate_bear_dissent = None
            self.debate_verdict = None
            self.debate_reason = None
            self.decision_source = None
            self.was_debate_modified = False

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, model, aid):
            syms = {1: "EURUSD", 2: "GBPUSD", 3: "AUDUSD", 4: "USDJPY"}
            decs = {1: "buy", 2: "buy", 3: "buy", 4: "sell"}
            return MockAnalysis(aid, syms[aid], decs[aid])
        async def execute(self, *args, **kwargs):
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            m.scalar_one_or_none.return_value = None
            return m
        async def commit(self):
            pass

    with patch("graph.nodes.debate_node.get_session", side_effect=MockSession):
        with patch("graph.nodes.debate_node.generate_bull_advocacy", side_effect=mock_advocacy):
            with patch("graph.nodes.debate_node.generate_bear_dissent", side_effect=mock_dissent):
                with patch("graph.nodes.debate_node.evaluate_debate", side_effect=mock_eval):
                    with patch("graph.nodes.debate_node.build_fact_sheet", return_value={"symbol": "TEST"}):
                        res = await debate_node(state, config)

    assert len(res["actionable_trades"]) > 0
    # Concurrency must be > 1 because 4 items run through Semaphore(3)
    assert max_concurrent >= 2, f"Expected concurrency >= 2, got {max_concurrent}"
    assert max_concurrent <= 3, f"Concurrency must not exceed Semaphore limit 3, got {max_concurrent}"
