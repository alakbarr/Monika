# ==============================================================================
# File: tests/analysis/test_telegram_tools_integration.py
# ==============================================================================

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.tools.tool_executor import ToolExecutor
from analysis.tools.tools_definitions import TELEGRAM_TOOLS, ALL_TOOLS
from database.models import (
    PaperTradeRecord, Position, TradeTrigger, AssetAnalysis,
    RiskState, FundamentalBrief, ActivityLog, TokenUsageLog,
    PriceOHLCV, SystemConfig
)

class TestTelegramToolsIntegration:

    @pytest.mark.asyncio
    async def test_telegram_tools_presence(self):
        """Pastikan semua tool baru terdaftar di TELEGRAM_TOOLS dan ALL_TOOLS."""
        tool_names = {t["name"] for t in TELEGRAM_TOOLS}
        expected = {
            "get_paper_trading_performance",
            "get_trade_history",
            "get_active_triggers",
            "get_system_health",
            "get_edge_tracker_status",
            "get_calibration_status",
            "get_token_usage_and_costs",
            "get_trade_details",
            "get_market_correlations",
            "get_open_positions",
            "get_account_info",
            "get_bond_yield_spreads",
            "get_multi_timeframe_summary",
            "get_chart",
            "get_spread_snapshot",
            "get_structure_breaks",
            "get_daily_range_context",
            "get_optimal_intraday_levels",
            "get_market_regime",
            "get_volatility_regime",
            "get_fxssi_sentiment",
            "get_structured_sentiment",
        }
        for name in expected:
            assert name in tool_names, f"Tool {name} missing from TELEGRAM_TOOLS"

    @pytest.mark.asyncio
    async def test_get_paper_trading_performance(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={"paper_trading": {"enabled": True}})

        with patch("utils.analytics.paper_tracker.PaperTracker.get_statistics", new_callable=AsyncMock) as mock_stats, \
             patch("utils.analytics.paper_tracker.PaperTracker.simulate_equity_curve", new_callable=AsyncMock) as mock_curve, \
             patch("utils.analytics.paper_tracker.PaperTracker.get_suspended_symbols", new_callable=AsyncMock) as mock_susp:
            
            mock_stats.return_value = {
                "total_trades": 25,
                "wins": 15,
                "losses": 10,
                "win_rate_pct": 60.0,
                "total_pnl_pct": 12.5,
                "avg_pnl_pct": 0.5,
                "expectancy_per_trade_R": 0.45,
                "has_positive_edge": True,
                "by_symbol": {"XAUUSD": {"trades": 10, "win_rate": 70.0}},
            }
            mock_curve.return_value = {
                "starting_equity": 10000.0,
                "final_equity": 11250.0,
                "total_return_pct": 12.5,
                "max_drawdown_pct": 3.2,
            }
            mock_susp.return_value = []

            res = await executor._tool_get_paper_trading_performance({"days_back": 30})
            assert res["total_trades"] == 25
            assert res["win_rate_pct"] == 60.0
            assert res["has_positive_edge"] is True
            assert res["simulated_equity"]["final_equity"] == 11250.0

    @pytest.mark.asyncio
    async def test_get_trade_history(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        trade1 = PaperTradeRecord(
            id=1, symbol="EURUSD", direction="buy", entry_price=1.0850,
            exit_price=1.0900, stop_loss=1.0800, take_profit=1.0900,
            status="closed", exit_reason="tp_hit", pnl_pct=0.46,
            holding_hours=4.5, opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc)
        )

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [trade1]
        mock_session.execute = AsyncMock(return_value=mock_result)

        res = await executor._tool_get_trade_history({"status": "closed", "mode": "paper"})
        assert res["count"] == 1
        assert res["trades"][0]["symbol"] == "EURUSD"
        assert res["trades"][0]["exit_reason"] == "tp_hit"

    @pytest.mark.asyncio
    async def test_get_active_triggers(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        trigger = TradeTrigger(
            id=10, asset_analysis_id=5, trigger_type="price_level",
            status="pending", condition_json=json.dumps({"price": 2650.0}),
            created_at=datetime.now(timezone.utc)
        )
        analysis = AssetAnalysis(
            id=5, symbol="XAUUSD", decision="wait", confidence=0.75,
            invalidation_price=2630.0
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [(trigger, analysis)]
        
        mock_bar_res = MagicMock()
        mock_bar = PriceOHLCV(symbol="XAUUSD", close=2645.0, timestamp=datetime.now(timezone.utc))
        mock_bar_res.scalar_one_or_none.return_value = mock_bar

        mock_session.execute = AsyncMock(side_effect=[mock_result, mock_bar_res])

        res = await executor._tool_get_active_triggers({"symbol": "XAUUSD"})
        assert res["count"] == 1
        assert res["triggers"][0]["symbol"] == "XAUUSD"
        assert res["triggers"][0]["current_price"] == 2645.0
        assert res["triggers"][0]["price_distance"] == 5.0

    @pytest.mark.asyncio
    async def test_get_system_health(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={"paper_trading": {"enabled": True}})

        risk = RiskState(date=datetime.now(timezone.utc), daily_pnl=1.2, current_drawdown=0.5, trading_paused=False)
        brief = FundamentalBrief(generated_at=datetime.now(timezone.utc))
        
        m_risk = MagicMock()
        m_risk.scalar_one_or_none.return_value = risk
        
        m_brief = MagicMock()
        m_brief.scalar_one_or_none.return_value = brief
        
        m_err = MagicMock()
        m_err.scalars().all.return_value = []
        
        m_cfg = MagicMock()
        m_cfg.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[m_risk, m_brief, m_err, m_cfg])

        res = await executor._tool_get_system_health({})
        assert res["status"] == "HEALTHY"
        assert res["trading_paused"] is False
        assert res["mode"] == "paper"

    @pytest.mark.asyncio
    async def test_get_open_positions_dual_mode(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        live_pos = Position(
            id=1, symbol="EURUSD", direction="buy", volume=0.1,
            entry_price=1.0800, sl=1.0750, tp=1.0900, status="open",
            mt5_ticket=1001, opened_at=datetime.now(timezone.utc), pnl=50.0
        )
        paper_pos = PaperTradeRecord(
            id=2, symbol="XAUUSD", direction="sell", entry_price=2650.0,
            stop_loss=2670.0, take_profit=2600.0, status="open",
            opened_at=datetime.now(timezone.utc)
        )
        bar = PriceOHLCV(symbol="XAUUSD", close=2640.0, timestamp=datetime.now(timezone.utc))

        m_live = MagicMock()
        m_live.scalars().all.return_value = [live_pos]

        m_paper = MagicMock()
        m_paper.scalars().all.return_value = [paper_pos]

        m_bar = MagicMock()
        m_bar.scalar_one_or_none.return_value = bar

        mock_session.execute = AsyncMock(side_effect=[m_live, m_paper, m_bar])

        res = await executor._tool_get_open_positions({"mode": "all"})
        assert res["count"] == 2
        assert res["positions"][0]["type"] == "live"
        assert res["positions"][1]["type"] == "paper"
        # Sell from 2650 to 2640 is positive floating profit
        assert res["positions"][1]["floating_pnl_pct"] > 0

    @pytest.mark.asyncio
    async def test_get_chart_tool_handler(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        now = datetime.now(timezone.utc)
        candles = [
            PriceOHLCV(
                symbol="EURUSD", timeframe="H4",
                open=1.0800 + i * 0.0005, high=1.0850 + i * 0.0005,
                low=1.0780 + i * 0.0005, close=1.0820 + i * 0.0005,
                volume=1000.0 + i * 10,
                timestamp=now - timedelta(hours=4 * (20 - i))
            )
            for i in range(20)
        ]

        m_res = MagicMock()
        m_res.scalars().all.return_value = candles
        mock_session.execute = AsyncMock(return_value=m_res)

        import sys, io
        mock_cg = MagicMock()
        mock_cg.generate_candlestick_chart.return_value = io.BytesIO(b"fake_png_bytes")
        with patch.dict(sys.modules, {"utils.chart_generator": mock_cg}):
            res = await executor.execute("get_chart", {"symbol": "EURUSD", "timeframe": "H4", "candles": 20})
        assert "chart_id" in res
        assert res["symbol"] == "EURUSD"
        assert res["candles_rendered"] == 20
        assert res["chart_id"] in executor._pending_charts

    @pytest.mark.asyncio
    async def test_get_spread_snapshot_tool_handler(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={"trading": {"asset_universe": ["EURUSD", "XAUUSD"]}})

        m_bar = MagicMock()
        m_bar.scalar_one_or_none.return_value = PriceOHLCV(symbol="EURUSD", close=1.0850, timestamp=datetime.now(timezone.utc))
        mock_session.execute = AsyncMock(return_value=m_bar)

        res = await executor.execute("get_spread_snapshot", {"symbols": ["EURUSD", "XAUUSD"]})
        assert "spreads" in res
        assert "EURUSD" in res["spreads"]
        assert "XAUUSD" in res["spreads"]
        assert res["spreads"]["EURUSD"]["current_spread_pips"] == 1.0
        assert res["spreads"]["XAUUSD"]["current_spread_pips"] == 2.5
