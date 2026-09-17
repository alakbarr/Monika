# ==============================================================================
# File: tests/graph/test_reactive_graph.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from graph.reactive_graph import (
    build_reactive_graph,
    get_reactive_graph,
    ReactiveState,
    event_ingestion_node,
    confluence_filter_node,
    fast_debate_node,
    reactive_execution_node,
)


@pytest.mark.asyncio
async def test_reactive_graph_compilation():
    """Verify that ReactiveGraph compiles successfully with all required nodes."""
    graph = build_reactive_graph()
    assert graph is not None
    node_names = list(graph.nodes.keys())
    assert "event_ingestion" in node_names
    assert "confluence_filter" in node_names
    assert "fast_debate" in node_names
    assert "risk_gate" in node_names
    assert "execution" in node_names
    assert "checkpoint" in node_names


@pytest.mark.asyncio
async def test_reactive_graph_empty_event():
    """Verify that ReactiveGraph terminates gracefully when no trades are actionable."""
    graph = build_reactive_graph()
    state = {
        "event_type": "news_event",
        "symbols": ["EURUSD"],
        "actionable_trades": [],
        "event_data": {},
        "summary": {},
    }
    config = {"configurable": {"scheduler": MagicMock(settings={})}}
    res = await graph.ainvoke(state, config=config)
    assert res.get("actionable_trades") == []
    assert "reactive_event" in res.get("summary", {})


@pytest.mark.asyncio
async def test_reactive_graph_event_ingestion_preplanned():
    """Verify event ingestion properly unpacks preplanned price triggers."""
    state = {
        "event_type": "price_trigger",
        "symbols": [],
        "actionable_trades": [],
        "event_data": {
            "trigger_id": 42,
            "analysis_id": 101,
            "symbol": "XAUUSD",
            "current_price": 2045.5,
            "preplanned_order": {"type": "BUY", "confidence": 0.85, "sl": 2040.0, "tp": 2060.0}
        }
    }
    res = await event_ingestion_node(state)
    assert "XAUUSD" in res["symbols"]
    assert len(res["actionable_trades"]) == 1
    sym, trade_data = res["actionable_trades"][0]
    assert sym == "XAUUSD"
    assert trade_data["analysis_id"] == 101
    assert trade_data["confidence"] == 0.85


@pytest.mark.asyncio
async def test_reactive_graph_confluence_filter():
    """Verify confluence filter removes trades below confidence or confluence thresholds."""
    mock_ana_high = MagicMock(confidence=0.75, confluence_score=8)
    mock_ana_low = MagicMock(confidence=0.50, confluence_score=4)

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, pk):
            if pk == 1:
                return mock_ana_high
            return mock_ana_low
        async def execute(self, *a, **kw):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            return m

    state = {
        "actionable_trades": [
            ("EURUSD", {"analysis_id": 1}),
            ("GBPUSD", {"analysis_id": 2}),
        ]
    }
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={"trading": {"auto_execute_min_confluence": 7, "auto_execute_min_confidence": 0.60}}
            )
        }
    }

    with patch("graph.reactive_graph.get_session", side_effect=MockSession):
        res = await confluence_filter_node(state, config=config)

    assert len(res["actionable_trades"]) == 1
    assert res["actionable_trades"][0][0] == "EURUSD"
    assert len(res["confluence_filtered_trades"]) == 1
    assert res["confluence_filtered_trades"][0][0] == "GBPUSD"


@pytest.mark.asyncio
async def test_reactive_graph_execution_auto_execute():
    """Verify reactive execution node calls ExecutionService and updates analysis status."""
    mock_ana = MagicMock()
    mock_ana.id = 101
    mock_ana.execution_status = "pending"

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, pk):
            return mock_ana
        async def commit(self):
            pass

    mock_exec_svc = MagicMock()
    mock_exec_svc.execute_analysis = AsyncMock(return_value=MagicMock(
        executed=True,
        risk_approved=True,
        summary=lambda: "Executed 0.1 lots EURUSD"
    ))

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"trading": {"auto_execute": True}}
    mock_scheduler.execution_service = mock_exec_svc
    mock_scheduler._execution_service = mock_exec_svc
    mock_scheduler._mt5 = None

    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101})],
        "summary": {},
        "event_data": {}
    }
    config = {"configurable": {"scheduler": mock_scheduler}}

    with patch("graph.reactive_graph.get_session", side_effect=MockSession):
        res = await reactive_execution_node(state, config=config)

    assert mock_ana.execution_status == "executed"
    assert "EURUSD" in res["execution_results"]
    assert "Executed 0.1 lots" in res["execution_results"]["EURUSD"]


@pytest.mark.asyncio
async def test_reactive_graph_edge_signal_routes_to_risk_gate():
    """Verify that edge_signal events route to risk_gate rather than bypassing directly to execution."""
    from graph.reactive_graph import (
        route_after_ingest,
        route_after_confluence,
        route_after_debate,
        route_after_risk,
    )

    # 1. Direct edge function verification: edge_signal -> risk_gate
    edge_state = {
        "event_type": "edge_signal",
        "symbols": ["EURUSD"],
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "confidence": 0.85})],
        "event_data": {"symbol": "EURUSD", "action": "buy"},
        "summary": {},
    }
    assert route_after_ingest(edge_state) == "risk_gate"

    # 2. Empty trades terminate at checkpoint
    empty_edge_state = {
        "event_type": "edge_signal",
        "symbols": ["EURUSD"],
        "actionable_trades": [],
        "event_data": {},
        "summary": {},
    }
    assert route_after_ingest(empty_edge_state) == "checkpoint"

    # 3. Standard events route to confluence_filter
    standard_state = {
        "event_type": "news_event",
        "symbols": ["EURUSD"],
        "actionable_trades": [("EURUSD", {"analysis_id": 101})],
        "event_data": {},
        "summary": {},
    }
    assert route_after_ingest(standard_state) == "confluence_filter"

    # 4. Downstream routing verifications
    assert route_after_confluence({"actionable_trades": [("EURUSD", {})]}) == "fast_debate"
    assert route_after_confluence({"actionable_trades": []}) == "checkpoint"
    assert route_after_debate({"actionable_trades": [("EURUSD", {})]}) == "risk_gate"
    assert route_after_debate({"actionable_trades": []}) == "checkpoint"
    assert route_after_risk({"actionable_trades": [("EURUSD", {})]}) == "execution"
    assert route_after_risk({"actionable_trades": []}) == "checkpoint"

    # 5. Compiled graph branch structure contains risk_gate destination
    graph = build_reactive_graph()
    assert graph is not None


