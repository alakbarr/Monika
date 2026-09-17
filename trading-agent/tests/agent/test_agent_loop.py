# ==============================================================================
# File: tests/agent/test_agent_loop.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent.agent_loop import SystemAgentLoop


def test_system_agent_loop_normalize_symbol():
    loop = SystemAgentLoop()
    assert loop.normalize_symbol("xauusd") == "XAUUSD"
    assert loop.normalize_symbol("EUR/USD") == "EURUSD"
    assert loop.normalize_symbol("  btc/usd  ") == "BTCUSD"
    assert loop.normalize_symbol("") == ""


@pytest.mark.asyncio
async def test_system_agent_loop_empty_symbol():
    loop = SystemAgentLoop()
    res = await loop.execute_ad_hoc_analysis("")
    assert res["success"] is False
    assert "tidak valid" in res["error"]


@pytest.mark.asyncio
async def test_system_agent_loop_execute_ad_hoc_mock_graph():
    loop = SystemAgentLoop()

    mock_final_state = {
        "asset_analyses": {
            "XAUUSD": {
                "decision": "buy",
                "confidence": 0.85,
                "entry_price": 2050.0,
                "stop_loss": 2040.0,
                "take_profit": 2075.0,
                "confluence_score": 5,
                "rationale": "Bullish order block confirmed at H1 with strong liquidity sweep.",
            }
        },
        "debate_states": {
            "XAUUSD": {
                "bull_case": "Strong momentum and DXY weakness supporting gold push higher.",
                "bear_case": "Resistance at 2080 could stall movement.",
                "divergence_score": 0.35,
            }
        },
        "investment_verdicts": {
            "XAUUSD": {"action": "buy"}
        },
    }

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)

    progress_log = []
    async def track_progress(msg: str):
        progress_log.append(msg)

    with patch("agent.agent_loop.build_trading_graph", return_value=mock_graph) as mock_builder:
        res = await loop.execute_ad_hoc_analysis("XAUUSD", progress_callback=track_progress)

        assert res["success"] is True
        assert res["symbol"] == "XAUUSD"
        assert res["decision"] == "BUY"
        assert res["confidence"] == 0.85
        assert res["confluence_score"] == 5
        assert res["entry_price"] == 2050.0
        assert res["stop_loss"] == 2040.0
        assert res["take_profit"] == 2075.0
        assert res["risk_reward_ratio"] == 2.5  # (2075 - 2050) / (2050 - 2040) = 25 / 10 = 2.5
        assert "HASIL ANALISIS AD-HOC: XAUUSD" in res["formatted_summary"]
        assert "Bullish order block" in res["formatted_summary"]

        mock_builder.assert_called_once_with(db_url=None)
        assert mock_graph.ainvoke.called
        assert len(progress_log) >= 2


@pytest.mark.asyncio
async def test_system_agent_loop_error_handling():
    loop = SystemAgentLoop()
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Data pipeline offline"))

    with patch("agent.agent_loop.build_trading_graph", return_value=mock_graph):
        res = await loop.execute_ad_hoc_analysis("EURUSD")
        assert res["success"] is False
        assert res["symbol"] == "EURUSD"
        assert "Data pipeline offline" in res["error"]
        assert "mengalami kendala" in res["formatted_summary"]


@pytest.mark.asyncio
async def test_adhoc_scheduler_proxy_get_symbol_paper_stats():
    from agent.agent_loop import AdHocSchedulerProxy
    from database.models import PaperTradeRecord

    proxy = AdHocSchedulerProxy(settings={}, symbols=["XAUUSD"])

    # 1. No session test
    stats_no_session = await proxy._get_symbol_paper_stats(None, "XAUUSD")
    assert stats_no_session == {"sufficient": False, "trades": 0, "win_rate": 50.0, "blocked": False}

    # 2. Insufficient trades (< 5)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    records_few = [
        PaperTradeRecord(symbol="XAUUSD", status="closed", exit_reason="tp_hit")
        for _ in range(3)
    ]
    mock_result.scalars.return_value.all.return_value = records_few
    mock_session.execute = AsyncMock(return_value=mock_result)

    stats_few = await proxy._get_symbol_paper_stats(mock_session, "XAUUSD")
    assert stats_few["sufficient"] is False
    assert stats_few["trades"] == 3
    assert stats_few["blocked"] is False

    # 3. Sufficient trades, poor win rate (10 trades, 2 wins = 20% < 35% -> blocked)
    records_blocked = [
        PaperTradeRecord(symbol="XAUUSD", status="closed", exit_reason="tp_hit" if i < 2 else "sl_hit")
        for i in range(10)
    ]
    mock_result.scalars.return_value.all.return_value = records_blocked
    stats_blocked = await proxy._get_symbol_paper_stats(mock_session, "XAUUSD")
    assert stats_blocked["sufficient"] is True
    assert stats_blocked["trades"] == 10
    assert stats_blocked["win_rate"] == 20.0
    assert stats_blocked["blocked"] is True

    # 4. Good win rate (10 trades, 7 wins = 70% >= 35% -> not blocked)
    records_good = [
        PaperTradeRecord(symbol="XAUUSD", status="closed", exit_reason="tp_hit" if i < 7 else "sl_hit")
        for i in range(10)
    ]
    mock_result.scalars.return_value.all.return_value = records_good
    stats_good = await proxy._get_symbol_paper_stats(mock_session, "XAUUSD")
    assert stats_good["sufficient"] is True
    assert stats_good["trades"] == 10
    assert stats_good["win_rate"] == 70.0
    assert stats_good["blocked"] is False


@pytest.mark.asyncio
async def test_paper_tracker_get_statistics_accepts_symbol():
    from utils.analytics.paper_tracker import PaperTracker

    tracker = PaperTracker()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    # Calling with symbol parameter must succeed without TypeError
    stats = await tracker.get_statistics(mock_session, symbol="EURUSD")
    assert isinstance(stats, dict)
    assert stats["total_trades"] == 0
    assert stats["win_rate_pct"] == 0

