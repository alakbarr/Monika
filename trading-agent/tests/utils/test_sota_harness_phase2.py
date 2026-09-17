import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.memory.session_search import SessionSearchEngine
from utils.llm.spill_subsystem import PostgresSpillSubsystem
from analysis.memory.lesson_consolidator import enforce_declarative_memory_rule
from skills.loader import get_dynamic_micro_skills
from analysis.validators.precommit_gate import TradePreCommitGate


def test_declarative_memory_rule_transformation():
    """Verify imperative memory instructions are converted to declarative facts."""
    imperative_text = """
    ## EURUSD
    - Always check VIX before entering long setups
    - Never enter during London open chop
    - Must wait for H1 BOS confirmation
    - Jangan trade saat spread melebar
    - Standard observation that was already fine
    """
    declarative = enforce_declarative_memory_rule(imperative_text)
    
    assert "Empirical observation: Checking VIX" in declarative
    assert "Empirical risk: Entering during London" in declarative
    assert "Historical precedent: Waiting for H1 BOS" in declarative
    assert "Pengamatan risiko empiris: Entry saat spread" in declarative
    assert "Standard observation that was already fine" in declarative


def test_dynamic_micro_skills_routing():
    """Verify dynamic micro-agent skill routing based on asset class."""
    btc_skills = get_dynamic_micro_skills("BTCUSD")
    gold_skills = get_dynamic_micro_skills("XAUUSD")
    fx_skills = get_dynamic_micro_skills("EURUSD")
    
    assert "crypto_analysis" in btc_skills
    assert "commodity_analysis" not in btc_skills
    
    assert "commodity_analysis" in gold_skills
    assert "crypto_analysis" not in gold_skills
    
    assert "smc_ict_playbook" in fx_skills
    assert "crypto_analysis" not in fx_skills
    assert "commodity_analysis" not in fx_skills


@pytest.mark.asyncio
async def test_hybrid_search_rrf():
    """Verify hybrid search with RRF merges sparse and dense rows correctly."""
    engine = SessionSearchEngine()
    
    mock_session = AsyncMock()
    # Mock return sparse rows and dense embedded rows
    r1 = MagicMock(id=101, symbol="XAUUSD", rationale_summary="Breakout on tariff news", reflection_text="Good follow through", alpha_lesson="Hold winners", decision="BUY", confidence=0.8, confluence_score=9, created_at=None, outcome_pnl_usd=120.0, is_paper_whatif=False, exit_reason="tp_hit")
    r2 = MagicMock(id=102, symbol="XAUUSD", rationale_summary="Range fakeout", reflection_text="Stopped out", alpha_lesson="Avoid low volume", decision="SELL", confidence=0.6, confluence_score=6, created_at=None, outcome_pnl_usd=-50.0, is_paper_whatif=False, exit_reason="sl_hit")
    
    # Give r2 an embedding similar to query
    r1.embedding = [0.1, 0.2, 0.3]
    r2.embedding = [0.9, 0.9, 0.9]
    
    mock_res_sparse = MagicMock()
    mock_res_sparse.scalars.return_value.all.return_value = [r1, r2]
    
    mock_res_dense = MagicMock()
    mock_res_dense.scalars.return_value.all.return_value = [r1, r2]
    
    mock_session.execute.side_effect = [mock_res_sparse, mock_res_dense]
    
    # Query vector close to r2
    results = await engine.hybrid_search("tariff safe haven", symbol="XAUUSD", query_vector=[0.9, 0.9, 0.85], limit=2, session=mock_session)
    assert len(results) == 2
    assert results[0]["symbol"] == "XAUUSD"


@pytest.mark.asyncio
async def test_spill_subsystem_threshold():
    """Verify payloads exceeding threshold are spilled and receipts generated."""
    subsystem = PostgresSpillSubsystem(settings={"context_compaction": {"spill_threshold_tokens": 50}})
    
    mock_session = AsyncMock()
    
    small_text = "short json result"
    res_small = await subsystem.maybe_spill(mock_session, "get_vix", small_text)
    assert res_small == small_text
    
    large_text = "candle data bar close high low volume " * 50
    res_large = await subsystem.maybe_spill(mock_session, "get_price_history", large_text, cycle_id="test_cycle")
    assert "[Observation Receipt: get_price_history" in res_large
    assert "db://spill/" in res_large
    assert mock_session.add.called


@pytest.mark.asyncio
async def test_precommit_gate_geometry_and_staleness():
    """Verify TradePreCommitGate blocks invalid geometry and stale entries."""
    gate = TradePreCommitGate()
    mock_session = AsyncMock()
    
    # Mock no economic calendar events and normal VIX
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    
    # 1. Invalid SL geometry: BUY with SL above entry
    bad_decision = {
        "decision": "buy",
        "entry_price": 100.0,
        "stop_loss": 105.0,  # Invalid: SL > entry
        "take_profit": 115.0,
    }
    passed, failures = await gate.verify_precommit(mock_session, bad_decision, "EURUSD")
    assert not passed
    assert any("Buy SL (105.0) must be strictly below entry" in f for f in failures)
    
    # 2. Valid geometry
    good_decision = {
        "decision": "buy",
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 105.0,
        "atr_14": 2.0
    }
    passed_good, failures_good = await gate.verify_precommit(mock_session, good_decision, "EURUSD")
    assert passed_good
    assert len(failures_good) == 0


@pytest.mark.asyncio
async def test_tool_executor_read_before_act_and_mandatory_tool():
    """Verify ToolExecutor blocks submit_asset_analysis without required data reads & position sizing."""
    from analysis.tools.tool_executor import ToolExecutor
    
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, symbol="EURUSD")
    
    # Attempt 1: submit without reading any market data
    res1 = await executor.execute("submit_asset_analysis", {"symbol": "EURUSD", "decision": "buy"})
    assert res1.get("status") == "blocked"
    assert res1.get("error_type") == "ReadBeforeActViolation"
    
    # Mark data read satisfied
    executor.called_tools.add("get_price_history")
    
    # Attempt 2: submit buy decision without calculating position size
    res2 = await executor.execute("submit_asset_analysis", {"symbol": "EURUSD", "decision": "buy"})
    assert res2.get("status") == "blocked"
    assert res2.get("error_type") == "MandatoryToolViolation"
    assert "MANDATORY TOOL ENFORCEMENT" in res2.get("error")
