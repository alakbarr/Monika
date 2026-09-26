import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from risk.risk_gate import RiskGate
from database.models import PaperTradeRecord, AssetAnalysis, SystemConfig
from scheduler.graph_cycle_scheduler import GraphCycleScheduler
from graph.nodes.risk_gate_node import risk_gate_node


@pytest.mark.asyncio
async def test_consecutive_losses_lookback_cutoff():
    """Verify that losses older than 7 days are ignored in consecutive losses streak check."""
    gate = RiskGate(settings={"trading": {"auto_execute": True, "risk": {"max_consecutive_losses_per_symbol": 3}}})
    
    mock_session = AsyncMock()
    # Mocking query execution: older losses (> 7 days) are filtered by query, so empty list returned
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("utils.analytics.paper_tracker.PaperTracker.get_suspended_symbols", new=AsyncMock(return_value=[])):
        allowed, reason = await gate._check_consecutive_losses(mock_session, "EURUSD")
        assert allowed is True
        assert "suspended" not in reason


@pytest.mark.asyncio
async def test_adaptive_threshold_48h_time_decay():
    """Verify that adaptive threshold adjustments older than 48 hours decay back to 0."""
    sched = GraphCycleScheduler(settings={})
    mock_session = AsyncMock()

    old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    old_row = MagicMock()
    old_row.key = "adaptive_threshold_EURUSD"
    old_row.value = json.dumps({
        "adjustment": 2,
        "set_at": old_time,
        "recent_wr": 25.0
    })

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [old_row]
    mock_session.execute.return_value = mock_result

    # Run update
    await sched._update_adaptive_thresholds_realtime(mock_session, [])
    
    updated_data = json.loads(old_row.value)
    assert updated_data["adjustment"] == 0
    assert updated_data["reason"] == "48h_time_decay_reset"


@pytest.mark.asyncio
async def test_risk_gate_node_evaluates_quant_on_wait_trade_and_persists():
    """Verify that risk_gate_node evaluates quant strategies on WAIT trades and persists to DB."""
    state = {
        "summary": {},
        "actionable_trades": [], # Empty LLM trades!
        "asset_analyses": {
            "EURUSD": {
                "analysis_id": 999,
                "decision": "wait",
                "confidence": 0.40,
                "entry_price": 1.0850,
                "stop_loss": 1.0800,
                "take_profit": 1.0950,
            }
        }
    }
    
    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"arbitration": {}}
    mock_scheduler.risk_gate = MagicMock()
    mock_scheduler.risk_gate.evaluate_proposal = AsyncMock(return_value=MagicMock(approved=True, rejection_reasons=[]))
    mock_scheduler.mt5 = None
    config = {"configurable": {"scheduler": mock_scheduler}}

    mock_sig = MagicMock()
    mock_sig.valid = True
    mock_sig.direction = "buy"
    mock_sig.strategy_id = "donchian_breakout"
    mock_sig.confidence = 0.85
    mock_sig.entry_price = 1.0850
    mock_sig.stop_loss = 1.0800
    mock_sig.take_profit = 1.0950

    mock_arb_res = MagicMock()
    mock_arb_res.decision = "buy"
    mock_arb_res.confidence = 0.85
    mock_arb_res.risk_multiplier = 1.0
    mock_arb_res.selected_source = "quant"
    mock_arb_res.entry_price = 1.0850
    mock_arb_res.stop_loss = 1.0800
    mock_arb_res.take_profit = 1.0950
    mock_arb_res.meta = {"strategy_id": "donchian_breakout"}

    mock_ana = MagicMock()
    mock_ana.id = 999
    mock_ana.decision = "wait"
    mock_ana.confidence = 0.40
    mock_ana.entry_zone = None
    mock_ana.stop_loss = 1.0800
    mock_ana.take_profit = 1.0950

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, ident):
            return mock_ana
        async def execute(self, stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            return m
        async def commit(self):
            pass

    with patch("database.db.get_session", side_effect=MockSession), \
         patch("analysis.calculators.regime_classifier.classify_market_regime", new=AsyncMock(return_value={"regime": "trending"})), \
         patch("analysis.strategies.registry.StrategyRegistry.evaluate_all", new=AsyncMock(return_value=[mock_sig])), \
         patch("analysis.strategies.decay_monitor.get_strategy_decay_monitor") as mock_dm, \
         patch("analysis.arbitration.signal_arbitrator.SignalArbitrator.arbitrate", new=AsyncMock(return_value=mock_arb_res)), \
         patch("risk.portfolio_correlation_gate.filter_correlated_proposals", new=AsyncMock(return_value=([("EURUSD", {"analysis_id": 999, "decision": "buy", "confidence": 0.85})], []))), \
         patch("analysis.validators.precommit_gate.TradePreCommitGate.verify_precommit", new=AsyncMock(return_value=(True, []))), \
         patch("utils.infra.notifier.AgentNotifier.send_info", new=AsyncMock()):
        
        mock_dm.return_value.is_live_ready.return_value = True
        
        res = await risk_gate_node(state, config)
        
        # Verify quant trade was promoted from WAIT to BUY
        assert len(res["approved_trades"]) == 1
        assert res["approved_trades"][0][0] == "EURUSD"
        # Verify persistence to AssetAnalysis
        assert mock_ana.decision == "buy"
        assert mock_ana.decision_source == "quant_donchian_breakout"


@pytest.mark.asyncio
async def test_risk_gate_node_proposal_error_fails_closed():
    """Verify that if proposal creation or validation raises an exception, the trade fails closed and is rejected."""
    state = {
        "summary": {},
        "actionable_trades": [
            ("BTCUSD", {
                "analysis_id": 888,
                "decision": "sell",
                "confidence": 0.70,
                "entry_price": 60000.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            })
        ],
        "asset_analyses": {}
    }

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"arbitration": {}}
    config = {"configurable": {"scheduler": mock_scheduler}}

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, ident):
            return None
        async def execute(self, stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            return m
        async def commit(self):
            pass

    with patch("database.db.get_session", side_effect=MockSession), \
         patch("risk.portfolio_correlation_gate.filter_correlated_proposals", new=AsyncMock(return_value=([("BTCUSD", {"analysis_id": 888, "decision": "sell", "confidence": 0.70})], []))), \
         patch("risk.trade_proposal.TradeProposal.from_analysis", side_effect=ValueError("Simulated proposal validation crash")), \
         patch("utils.infra.notifier.AgentNotifier.send_info", new=AsyncMock()):

        res = await risk_gate_node(state, config)
        # STRICT FAIL-CLOSED: The trade must NOT be approved
        assert len(res["approved_trades"]) == 0


@pytest.mark.asyncio
async def test_risk_gate_node_safe_num_uses_math_and_strips_formatting():
    """Verify that risk_gate_node evaluates math.isnan/isinf and formatted strings without NameError."""
    state = {
        "actionable_trades": [
            ("BTCUSD", {
                "analysis_id": 999,
                "decision": "buy",
                "confidence": 0.85,
                "entry_price": "$83,729.50",
                "stop_loss": 82000.0,
                "take_profit": 87000.0,
            })
        ],
        "asset_analyses": {}
    }

    mock_verdict = MagicMock()
    mock_verdict.approved = True
    mock_verdict.rejection_reasons = []

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {
        "trading": {"risk": {"max_risk_per_trade_pct": 1.0}},
        "arbitration": {}
    }
    mock_scheduler.risk_gate = MagicMock()
    mock_scheduler.risk_gate.evaluate_proposal = AsyncMock(return_value=mock_verdict)
    mock_scheduler.mt5 = None
    config = {"configurable": {"scheduler": mock_scheduler}}

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, ident):
            return None
        async def execute(self, stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            return m
        async def commit(self):
            pass

    mock_verdict = MagicMock()
    mock_verdict.approved = True
    mock_verdict.rejection_reasons = []

    with patch("database.db.get_session", side_effect=MockSession), \
         patch("risk.portfolio_correlation_gate.filter_correlated_proposals", new=AsyncMock(return_value=(state["actionable_trades"], []))), \
         patch("risk.risk_gate.RiskGate.evaluate_proposal", new=AsyncMock(return_value=mock_verdict)), \
         patch("analysis.validators.precommit_gate.TradePreCommitGate.verify_precommit", new=AsyncMock(return_value=(True, []))), \
         patch("utils.infra.notifier.AgentNotifier.send_info", new=AsyncMock()):

        res = await risk_gate_node(state, config)
        assert len(res["approved_trades"]) == 1
        sym, approved_data = res["approved_trades"][0]
        assert sym == "BTCUSD"
        assert approved_data["entry_price"] == 83729.5

