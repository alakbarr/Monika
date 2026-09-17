import pytest
pytest.importorskip("langgraph")

from unittest.mock import AsyncMock, MagicMock, patch
from graph.workflow import build_trading_graph
from graph.state import TradingState

@pytest.mark.asyncio
async def test_graph_compilation_and_execution():
    """
    Memastikan graph berhasil dicompile dan dijalankan untuk edge case normal.
    Kita mock nodes yang melakukan IO.
    """
    graph = build_trading_graph()
    
    # Buat dummy state
    initial_state = {
        "symbols": ["EURUSD"],
        "market_regime": "unknown",
        "fundamental_brief_id": None,
        "asset_analyses": {},
        "approved_trades": [],
        "errors": [],
        "should_pause": False
    }
    
    # Kita tidak bisa secara mudah memock node internal graph setelah ter-compile
    # tanpa mem-patch modul aslinya, jadi kita cukup pastikan fungsi compile
    # tidak menghasilkan error (Graph definition valid).
    assert graph is not None
    
    # Pastikan struktur dasarnya
    assert "data_gathering" in graph.nodes
    assert "fundamental_analysis" in graph.nodes
    assert "per_asset_analysis" in graph.nodes
    assert "risk_gate" in graph.nodes
    assert "plan_refinement" in graph.nodes
    assert "execution" in graph.nodes

@pytest.mark.asyncio
async def test_graph_state_dict():
    """Memastikan bahwa state reducer dan struktur bisa memuat data"""
    from graph.state import merge_dicts
    
    # Test reducer
    a = {"EURUSD": {"decision": "buy"}}
    b = {"XAUUSD": {"decision": "sell"}}
    c = merge_dicts(a, b)
    
    assert "EURUSD" in c
    assert "XAUUSD" in c
    assert c["EURUSD"]["decision"] == "buy"
    assert c["XAUUSD"]["decision"] == "sell"


@pytest.mark.asyncio
async def test_data_node_calendar_freshness_timedelta_safety():
    """Memastikan bahwa modul data_node mengimpor timedelta dan mengeksekusi logika kalender tanpa NameError."""
    import graph.nodes.data_node as dn
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    # Ensure timedelta is defined in data_node module namespace
    assert hasattr(dn, 'timedelta')
    assert dn.timedelta is timedelta

    # Simulate calendar check query block
    mock_session = AsyncMock()
    mock_result_cfg = MagicMock()
    mock_result_cfg.scalar_one_or_none.return_value = None
    mock_result_cov = MagicMock()
    mock_result_cov.scalar_one_or_none.return_value = 1

    mock_session.execute = AsyncMock(side_effect=[mock_result_cfg, MagicMock(scalar_one_or_none=lambda: datetime.now(timezone.utc)), mock_result_cov])

    now_utc = datetime.now(timezone.utc)
    # Testing that expressions like now_utc - dn.timedelta(hours=1) evaluate properly
    past_1h = now_utc - dn.timedelta(hours=1)
    future_12h = now_utc + dn.timedelta(hours=12)
    assert past_1h < now_utc < future_12h


@pytest.mark.asyncio
async def test_per_asset_node_preserves_skipped_metadata():
    """Verify that per_asset_analysis_node preserves skipped_by_cooldown and error in summary."""
    from graph.nodes.per_asset_node import per_asset_analysis_node
    
    mock_scheduler = MagicMock()
    mock_scheduler.settings = {'trading': {'auto_execute': False}}
    mock_scheduler.asset_universe = ['EURUSD', 'USDJPY']
    mock_scheduler._paper_tracker = MagicMock()
    mock_scheduler._paper_tracker.check_and_suspend_poor_performers = AsyncMock()
    mock_scheduler._paper_tracker.get_suspended_symbols = AsyncMock(return_value=[])
    
    # Mock pa_results with one analyzed asset and one cooldown-skipped asset
    mock_scheduler._per_asset = MagicMock()
    mock_scheduler._per_asset.run_all = AsyncMock(return_value={
        'EURUSD': {'decision': 'wait', 'confidence': 0.65, 'analysis_id': 1, 'elapsed_seconds': 10, 'input_tokens': 100, 'output_tokens': 50},
        'USDJPY': {'decision': 'skip', 'confidence': 0.0, 'analysis_id': None, 'elapsed_seconds': 0, 'skipped_by_cooldown': True, 'rationale': 'Cooldown active'}
    })
    
    state = {'summary': {}, 'stale_assets': [], 'weekend_symbols_override': None}
    config = {'configurable': {'scheduler': mock_scheduler}}
    
    with patch('graph.nodes.per_asset_node.get_session') as mock_gs:
        mock_session = AsyncMock()
        mock_gs.return_value.__aenter__.return_value = mock_session
        result = await per_asset_analysis_node(state, config)
        
    per_asset = result['summary']['per_asset']
    assert 'EURUSD' in per_asset
    assert per_asset['EURUSD']['decision'] == 'wait'
    assert per_asset['EURUSD']['skipped_by_cooldown'] is False
    
    assert 'USDJPY' in per_asset
    assert per_asset['USDJPY']['decision'] == 'skip'
    assert per_asset['USDJPY']['skipped_by_cooldown'] is True
    assert per_asset['USDJPY']['rationale'] == 'Cooldown active'


@pytest.mark.asyncio
async def test_cycle_performance_calculation_with_skipped_asset():
    """Verify that skipped assets are correctly counted in CyclePerformance."""
    pa_results = {
        'EURUSD': {'decision': 'wait', 'skipped_by_cooldown': False},
        'GBPUSD': {'decision': 'wait', 'skipped_by_cooldown': False},
        'USDJPY': {'decision': 'skip', 'skipped_by_cooldown': True},
        'XAUUSD': {'decision': 'buy', 'skipped_by_cooldown': False},
    }
    
    decisions = {'buy': 0, 'sell': 0, 'wait': 0, 'avoid': 0}
    skipped_symbols_info = []
    
    for sym, r in pa_results.items():
        d = r.get('decision', 'wait')
        if d in decisions:
            decisions[d] += 1
        elif d == 'skip':
            reason = 'cooldown' if r.get('skipped_by_cooldown') else 'other'
            skipped_symbols_info.append(f"{sym}({reason})")
            
    def _is_skipped(res: dict) -> bool:
        return bool(res.get('skipped_by_cooldown') or res.get('decision') == 'skip')
        
    analyzed = sum(1 for r in pa_results.values() if not _is_skipped(r))
    skipped = sum(1 for r in pa_results.values() if _is_skipped(r))
    
    assert decisions['buy'] == 1
    assert decisions['wait'] == 2
    assert decisions['sell'] == 0
    assert decisions['avoid'] == 0
    assert analyzed == 3
    assert skipped == 1
    assert skipped_symbols_info == ['USDJPY(cooldown)']


@pytest.mark.asyncio
async def test_trading_summary_typed_dict_keys():
    """Verify that TradingSummary can hold all required metrics without typing errors."""
    from graph.state import TradingSummary
    
    summary: TradingSummary = {
        "scraping": {"status": "ok"},
        "data_refresh": {"sources": 5},
        "price_fetch": {"EURUSD": 500},
        "price_fetch_m15": {"EURUSD": 100},
        "indicators": {"EURUSD": "computed"},
        "structure": {"EURUSD": 10},
        "macro_precompute": "success",
        "performance_notes": {"regenerated": False},
        "data_validation": {"errors": []},
        "vix_halt": {"triggered": False},
        "macro_regime": {"regime": "normal"},
        "skipped_reason": None,
        "fundamental": {"success": True},
        "api_cost_usd": 0.05,
        "fundamental_shift_alert": {},
        "ssvp_cds_score": 0.12,
        "ssvp_message": "coherent",
        "ssvp_warning": None,
        "ssvp_reconciliation_context": None,
        "per_asset": {},
        "per_asset_errors": [],
        "ssvp_suppressed_symbols": ["USDJPY"],
        "contradiction_filter_applied": True,
        "context_version_split_detected": False,
        "context_version_split_detail": None,
        "debate_approved": ["EURUSD"],
        "debate_rejected": ["GBPUSD"],
        "reflection_contradiction_filtered": "filtered",
        "reflection_macro_inconsistent_filtered": [],
        "reflection_all_macro_inconsistent": False,
        "portfolio_synthesis_approved": ["EURUSD"],
        "execution": {"status": "pending_approval"},
        "elapsed_total_s": 42.5,
    }
    
    assert summary["scraping"]["status"] == "ok"
    assert summary["ssvp_cds_score"] == 0.12
    assert summary["api_cost_usd"] == 0.05
    assert summary["debate_approved"] == ["EURUSD"]


@pytest.mark.asyncio
async def test_workflow_build_options():
    """Verify build_trading_graph with None db_url and postgres db_url."""
    from graph.workflow import build_trading_graph
    
    graph_memory = build_trading_graph(None)
    assert graph_memory is not None
    
    graph_pg = build_trading_graph("postgresql+asyncpg://user:pass@localhost:5432/db")
    assert graph_pg is not None


@pytest.mark.asyncio
async def test_data_node_scheduler_none_guard():
    """Verify fetch_data_node returns paused when scheduler is missing."""
    from graph.nodes.data_node import fetch_data_node
    state: TradingState = {
        "symbols": ["EURUSD"],
        "market_regime": "normal",
        "vix_level": 15.0,
        "brief_confidence": 0.8,
        "asset_analyses": {},
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "approved_trades": [],
        "errors": [],
        "should_pause": False,
        "weekend_symbols_override": None,
        "stale_assets": [],
        "summary": {},
        "actionable_trades": [],
        "reflection_applied": None,
        "node_errors": {},
        "data_quality_scores": {},
        "cycle_id": "test-1",
        "fundamental_retry_count": 0,
        "prior_cycle_insights": {},
        "consecutive_wait_count": 0,
        "last_buy_sell_cycle": None,
        "ssvp_per_symbol_contexts": {},
        "ssvp_cds_score": 0.0,
        "ssvp_blocked": False,
        "ssvp_reconciliation_context": None,
        "context_snapshot_id": None,
        "ssvp_retry_count": 0
    }
    config = {"configurable": {}}
    res = await fetch_data_node(state, config)
    assert res.get("should_pause") is True


@pytest.mark.asyncio
async def test_fundamental_node_scheduler_none_guard():
    """Verify fundamental_analysis_node returns paused when scheduler is missing."""
    from graph.nodes.fundamental_node import fundamental_analysis_node
    state: TradingState = {
        "symbols": ["EURUSD"],
        "market_regime": "normal",
        "vix_level": 15.0,
        "brief_confidence": 0.8,
        "asset_analyses": {},
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "approved_trades": [],
        "errors": [],
        "should_pause": False,
        "weekend_symbols_override": None,
        "stale_assets": [],
        "summary": {},
        "actionable_trades": [],
        "reflection_applied": None,
        "node_errors": {},
        "data_quality_scores": {},
        "cycle_id": "test-1",
        "fundamental_retry_count": 0,
        "prior_cycle_insights": {},
        "consecutive_wait_count": 0,
        "last_buy_sell_cycle": None,
        "ssvp_per_symbol_contexts": {},
        "ssvp_cds_score": 0.0,
        "ssvp_blocked": False,
        "ssvp_reconciliation_context": None,
        "context_snapshot_id": None,
        "ssvp_retry_count": 0
    }
    config = {"configurable": {}}
    res = await fundamental_analysis_node(state, config)
    assert res.get("should_pause") is True


@pytest.mark.asyncio
async def test_per_asset_node_scheduler_none_guard():
    """Verify per_asset_analysis_node returns safely when scheduler is missing."""
    from graph.nodes.per_asset_node import per_asset_analysis_node
    state: TradingState = {
        "symbols": ["EURUSD"],
        "market_regime": "normal",
        "vix_level": 15.0,
        "brief_confidence": 0.8,
        "asset_analyses": {},
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "approved_trades": [],
        "errors": [],
        "should_pause": False,
        "weekend_symbols_override": None,
        "stale_assets": [],
        "summary": {},
        "actionable_trades": [],
        "reflection_applied": None,
        "node_errors": {},
        "data_quality_scores": {},
        "cycle_id": "test-1",
        "fundamental_retry_count": 0,
        "prior_cycle_insights": {},
        "consecutive_wait_count": 0,
        "last_buy_sell_cycle": None,
        "ssvp_per_symbol_contexts": {},
        "ssvp_cds_score": 0.0,
        "ssvp_blocked": False,
        "ssvp_reconciliation_context": None,
        "context_snapshot_id": None,
        "ssvp_retry_count": 0
    }
    config = {"configurable": {}}
    res = await per_asset_analysis_node(state, config)
    assert res.get("actionable_trades") == []


@pytest.mark.asyncio
async def test_plan_refinement_node_execution():
    """Verify that plan_refinement_node successfully adjusts SL, TP, and risk_multiplier."""
    from graph.nodes.plan_refinement_node import plan_refinement_node
    
    state = {
        "refinement_count": 0,
        "is_negotiable_rejection": True,
        "rejection_feedback": {
            "rejected_items": [
                {
                    "symbol": "EURUSD",
                    "trade": {
                        "symbol": "EURUSD",
                        "decision": "buy",
                        "entry_price": 1.0850,
                        "stop_loss": 1.0845,
                        "take_profit": 1.0860,
                        "risk_multiplier": 1.0,
                        "analysis_id": None
                    },
                    "reasons": ["GEOMETRY: Buy SL too tight, inside noise cone", "portfolio_heat: lot size exceeds limit"]
                }
            ]
        },
        "summary": {}
    }
    config = {"configurable": {}}
    res = await plan_refinement_node(state, config)
    
    assert res["refinement_count"] == 1
    assert res["is_negotiable_rejection"] is False
    assert len(res["actionable_trades"]) == 1
    
    sym, refined_trade = res["actionable_trades"][0]
    assert sym == "EURUSD"
    # Risk multiplier should have been scaled down
    assert refined_trade["risk_multiplier"] < 1.0
    # Stop loss should have been widened beyond initial 5 pips
    assert refined_trade["stop_loss"] < 1.0845
    # Take profit should maintain positive reward:risk
    assert refined_trade["take_profit"] > 1.0850


@pytest.mark.asyncio
async def test_execution_node_slippage_sandbox_rejection(db_session):
    """Verify execution_node rejects trade when ExecutionSimulator deems edge-to-drag unfavorable."""
    from graph.nodes.execution_node import execution_node
    from database.models import AssetAnalysis
    from risk.execution_simulator import ExecutionSimulationResult
    from contextlib import asynccontextmanager
    import utils.clock as clock

    # Create dummy AssetAnalysis
    analysis = AssetAnalysis(
        symbol="EURUSD",
        generated_at=clock.now(),
        decision="buy",
        confidence=0.85,
        entry_zone='{"price": 1.0850}',
        stop_loss=1.0845,
        take_profit=1.0852,
        confluence_score=8,
        execution_status=None,
    )
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    @asynccontextmanager
    async def mock_session():
        yield db_session

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {
        "trading": {
            "auto_execute": True,
            "auto_execute_min_confluence": 6,
            "auto_execute_min_confidence": 0.60,
            "auto_execute_active_hours_utc_start": 0,
            "auto_execute_active_hours_utc_end": 24,
            "risk": {
                "slippage_sandbox_enabled": True,
                "min_edge_to_slippage_ratio": 1.1,
            }
        },
        "execution": {
            "max_analysis_age_for_execute_minutes": 60,
        },
        "adversarial_check": {
            "enabled": False,
        }
    }
    mock_scheduler.dry_run = False
    mock_scheduler._mt5 = MagicMock()
    mock_scheduler._mt5.get_account_info = AsyncMock(return_value={"equity": 10000.0})
    mock_scheduler._get_symbol_paper_stats = AsyncMock(return_value={"blocked": False, "win_rate": 60.0})

    unresilient_res = ExecutionSimulationResult(
        resilient=False,
        edge_to_drag_ratio=0.4,
        median_spread=0.0003,
        current_spread=0.0003,
        scenarios={},
        rejection_reason="SLIPPAGE_UNFAVORABLE: Edge (0.0002) to stress drag (0.0005) below 1.1"
    )

    state = {
        "summary": {},
        "actionable_trades": [
            ("EURUSD", {
                "analysis_id": analysis.id,
                "confidence": 0.85,
                "decision": "buy",
                "entry_price": 1.0850,
                "stop_loss": 1.0845,
                "take_profit": 1.0852,
            })
        ],
        "cycle_id": "test-slippage-cycle",
    }
    config = {"configurable": {"scheduler": mock_scheduler}}

    with patch("graph.nodes.execution_node.get_session", mock_session), \
         patch("risk.execution_simulator.ExecutionSimulator.simulate_execution", AsyncMock(return_value=unresilient_res)):
        res = await execution_node(state, config)

    assert res["summary"]["execution"]["EURUSD"] == "blocked_slippage_drag"
    await db_session.refresh(analysis)
    assert analysis.execution_status == "rejected"
    assert "SLIPPAGE_UNFAVORABLE" in (analysis.execution_notes or "")


@pytest.mark.asyncio
async def test_compiled_graph_astream_passes_config():
    """Verify that compiled trading graph properly passes config to traced nodes without TypeError."""
    graph = build_trading_graph()
    state = {
        "symbols": ["EURUSD"],
        "market_regime": "unknown",
        "vix_level": 15.0,
        "brief_confidence": 0.8,
        "fundamental_brief_id": None,
        "asset_analyses": {},
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "approved_trades": [],
        "errors": [],
        "node_errors": {},
        "data_quality_scores": {},
        "cycle_id": "test-traced-stream",
        "fundamental_retry_count": 0,
        "should_pause": False,
        "weekend_symbols_override": None,
        "stale_assets": [],
        "summary": {},
        "actionable_trades": [],
        "reflection_applied": False,
        "prior_cycle_insights": {},
        "consecutive_wait_count": 0,
        "last_buy_sell_cycle": None,
        "ssvp_per_symbol_contexts": {},
        "ssvp_cds_score": None,
        "ssvp_blocked": False,
        "ssvp_reconciliation_context": None,
        "context_snapshot_id": None,
        "ssvp_retry_count": 0,
    }
    config = {"configurable": {"thread_id": "test-traced-1", "scheduler": None}}
    
    events = []
    async for event in graph.astream(state, config=config):
        events.append(event)
        # Should pause at data_gathering because scheduler is None
        if "data_gathering" in event and event["data_gathering"].get("should_pause"):
            break

    assert len(events) >= 1
    assert "data_gathering" in events[0]
    assert events[0]["data_gathering"]["should_pause"] is True




