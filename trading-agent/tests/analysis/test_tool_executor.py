import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.tools.tool_executor import ToolExecutor
from database.models import (
    EconomicCalendar, TechnicalIndicator, PriceOHLCV, 
    FundamentalBrief, SystemConfig, AssetAnalysis
)

class TestToolExecutor:

    @pytest.mark.asyncio
    async def test_execute_success(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        executor = ToolExecutor(mock_session)
        
        executor._tool_test_tool = AsyncMock(return_value={"status": "ok"})
        result = await executor.execute("test_tool", {"a": 1})
        
        assert result == {"status": "ok"}
        executor._tool_test_tool.assert_awaited_once_with({"a": 1})

    @pytest.mark.asyncio
    async def test_execute_unknown(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        executor = ToolExecutor(mock_session)
        
        result = await executor.execute("non_existent", {})
        assert "error" in result
        assert result["error_type"] == "UnknownToolError"
        assert "non_existent" in result["error"]

    def test_tool_name_normalization(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        # Prefix duplication
        assert executor._normalize_tool_name("submit_submit_fundamental_brief") == "submit_fundamental_brief"
        assert executor._normalize_tool_name("submit_submit_submit_asset_analysis") == "submit_asset_analysis"
        assert executor._normalize_tool_name("get_get_dxy") == "get_dxy"

        # Namespace prefixes and parentheses
        assert executor._normalize_tool_name("tools.get_market_session") == "get_market_session"
        assert executor._normalize_tool_name("functions.get_dxy()") == "get_dxy"
        assert executor._normalize_tool_name("default.get_vix") == "get_vix"

        # Aliases
        assert executor._normalize_tool_name("submit_fundamental") == "submit_fundamental_brief"
        assert executor._normalize_tool_name("get_calendar") == "get_economic_calendar"
        assert executor._normalize_tool_name("get_open_position") == "get_open_positions"

    @pytest.mark.asyncio
    async def test_execute_with_duplicated_prefix(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)
        executor._tool_submit_fundamental_brief = AsyncMock(return_value={"status": "recorded"})

        result = await executor.execute("submit_submit_fundamental_brief", {"bias": "bullish"})
        assert result == {"status": "recorded"}
        executor._tool_submit_fundamental_brief.assert_awaited_once_with({"bias": "bullish"})
        assert "submit_fundamental_brief" in executor.called_tools

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        executor = ToolExecutor(mock_session)
        
        executor._tool_test_tool = AsyncMock(side_effect=Exception("Test error"))
        result = await executor.execute("test_tool", {})
        
        assert "error" in result
        assert "Test error" in result["error"]
        assert result["tool"] == "test_tool"

    @pytest.mark.asyncio
    async def test_get_market_session(self):
        executor = ToolExecutor(AsyncMock())
        res = await executor._tool_get_market_session({})
        assert "utc_time" in res
        assert "active_sessions" in res
        assert "overlap" in res
        assert "highest_liquidity" in res

    @pytest.mark.asyncio
    async def test_get_economic_calendar(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        executor = ToolExecutor(mock_session)
        
        mock_result = MagicMock()
        ev1 = EconomicCalendar(event_name="NFP", currency="USD", impact="high", actual=None, forecast=None, previous=None, event_time=datetime.now(timezone.utc))
        mock_result.scalars().all.return_value = [ev1]
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        res = await executor._tool_get_economic_calendar({"impact_filter": "high", "currency_filter": "USD,EUR"})
        
        assert res["count"] == 1
        assert "NFP" in res["events"][0]["event_name"]
        assert res["events"][0]["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_submit_fundamental_brief(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        executor = ToolExecutor(mock_session)
        
        executor.called_tools.add("get_dxy")
        executor.called_tools.add("get_vix")
        
        def assign_id(brief):
            brief.id = 55
            
        mock_session.refresh.side_effect = assign_id
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        res = await executor._tool_submit_fundamental_brief({
            "macro_narrative": "test DXY is up, VIX is down",
            "currency_bias": {"USD": "bullish", "EUR": "bearish", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "bearish", "OIL": "bearish", "BTC": "bullish"},
            "key_upcoming_risks": [],
            "risk_sentiment": "risk-on",
            "macro_regime": "mixed",
            "confidence": 0.8,
            "invalidation_conditions": {
                "USD": "dxy drops below 103 level and stays there for more than 2 days",
                "EUR": "ecb cuts rates by 50bps and indicates more cuts are coming",
                "XAU": "yields surge above 4.5% and stay elevated through the week",
                "OIL": "demand drops by 100k bpd according to the next eia report",
                "BTC": "etf outflows > 1B and regulatory scrutiny increases significantly"
            },
            "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.9, "OIL": 0.6, "BTC": 0.75},
            "strongest_counter_thesis": "This is a sufficiently long counter thesis string that will pass the length validation check required by the system.",
            "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
            "key_data_points_used": {
                "dxy_trend_5d": "strengthening +0.8%",
                "vix_close": 15.5,
                "fedwatch_dominant_pct": 85.0
            },
            "priced_in_assessment": {
                "dominant_driver": "Fed rate cut expectations",
                "priced_in_score": 8,
                "sell_the_news_risk": "high",
                "key_unpriced_drivers": ["ECB surprise"],
                "upcoming_event_context": "FOMC in 12h, 87% cut probability.",
                "cot_positioning_percentile": 80,
                "retail_sentiment_percentile": 20
            }
        })
        
        assert res["status"] == "saved"
        assert "valid_until" in res
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], FundamentalBrief)
        assert args[0].content_markdown == "test DXY is up, VIX is down"

    @pytest.mark.asyncio
    async def test_get_technical_indicators_success(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        executor = ToolExecutor(mock_session)
        
        now = datetime.now(timezone.utc)
        mock_ts_result = MagicMock()
        mock_ts_result.scalars().all.return_value = [now]
        
        mock_rows_result = MagicMock()
        ind1 = TechnicalIndicator(indicator_name="RSI", timestamp=now, value_json=json.dumps(60.5))
        mock_rows_result.scalars().all.return_value = [ind1]
        
        mock_session.execute = AsyncMock(side_effect=[mock_ts_result, mock_rows_result])
        
        res = await executor._tool_get_technical_indicators({"symbol": "XAUUSD", "timeframe": "H4"})
        
        assert res["symbol"] == "XAUUSD"
        assert res["indicators"]["RSI"]["value"] == 60.5

    @pytest.mark.asyncio
    @patch('analysis.calculators.confluence_calculator.calculate_confluence', new_callable=AsyncMock)
    async def test_submit_asset_analysis_validation_failure(self, mock_calc_conf):
        mock_calc_conf.return_value = {"computed_score": 0}
        
        mock_session = AsyncMock()
        mock_ts = MagicMock()
        mock_ts.scalar_one_or_none.return_value = datetime.now(timezone.utc)
        def execute_side_effect(*args, **kwargs):
            query = str(args[0]).lower()
            if 'price_ohlcv' in query and 'timestamp' in query:
                return mock_ts
            elif 'technical_indicators' in query and 'timestamp' in query:
                return mock_ts
            empty = MagicMock()
            empty.scalar_one_or_none.return_value = None
            return empty
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        
        executor = ToolExecutor(mock_session)
        res = await executor._tool_submit_asset_analysis({
            "symbol": "XAUUSD",
            "decision": "buy",
            # missing required fields
        })
        
        assert res["status"] == "validation_failed"
        assert len(res["errors"]) > 0

    @pytest.mark.asyncio
    @patch('analysis.calculators.confluence_calculator.calculate_confluence', new_callable=AsyncMock)
    async def test_submit_asset_analysis_success(self, mock_calc_conf):
        mock_calc_conf.return_value = {
            "computed_score": 8,
            "max_score": 14,
            "components": [],
            "issues": []
        }
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        executor = ToolExecutor(mock_session)
        
        mock_brief_result = MagicMock()
        mock_brief_result.scalar_one_or_none.return_value = 11
        
        mock_price = MagicMock()
        mock_price.scalar_one_or_none.return_value.close = 2025.0

        mock_atr = MagicMock()
        mock_atr.scalar_one_or_none.return_value.value_json = '{"atr": 20.0}'

        mock_ts = MagicMock()
        mock_ts.scalar_one_or_none.return_value = datetime.now(timezone.utc)
        
        mock_cfg = MagicMock()
        mock_cfg.scalar_one_or_none.return_value = None

        mock_brief = MagicMock()
        mock_brief.scalar_one_or_none.return_value = 11
        
        mock_fvg = MagicMock()
        mock_fvg.scalars.return_value.all.return_value = []
        mock_ob = MagicMock()
        mock_ob.scalars.return_value.all.return_value = []
        mock_swings = MagicMock()
        mock_swings.scalars.return_value.all.return_value = []

        def execute_side_effect(*args, **kwargs):
            query = str(args[0]).lower()
            if 'max(' in query or 'min(' in query:
                return mock_ts
            elif 'price_ohlcv' in query:
                return mock_price
            elif 'technical_indicators' in query and 'timestamp' in query and 'indicator_name' not in query:
                return mock_ts
            elif 'technical_indicators' in query:
                return mock_atr
            elif 'system_config' in query:
                return mock_cfg
            elif 'fundamental_briefs' in query:
                return mock_brief
            elif 'fvg_zones' in query:
                return mock_fvg
            elif 'order_blocks' in query:
                return mock_ob
            elif 'swing_points' in query:
                return mock_swings
            elif 'sr_zones' in query:
                return mock_swings
            return mock_brief

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        
        def assign_id():
            for obj in mock_session.add.call_args_list:
                if isinstance(obj[0][0], AssetAnalysis):
                    obj[0][0].id = 101

        mock_session.flush.side_effect = assign_id

        res = await executor._tool_submit_asset_analysis({
            "symbol": "XAUUSD",
            "decision": "buy",
            "confidence": 0.9,
            "confluence_score": 8,
            "priced_in_score": 5,
            "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
            "entry_condition": {
                "type": "market",
                "detail": "Enter market price now"
            },
            "stop_loss": 1950.0,
            "take_profit": 2200.0,
            "rationale": "Looks good",
            "invalidation": "Price drops below 1950",
            "invalidation_price": 1950.0,
            "invalidation_direction": "below",
            "reevaluation_trigger": {"type": "price_level", "detail": "Price stalls at 2100", "price": 2100.0, "direction": "below"}
        })
        
        assert res["status"] == "saved"
        assert res["analysis_id"] == 101
        assert res["symbol"] == "XAUUSD"
        assert res["decision"] == "buy"
        
        # Called at least once for analysis
        assert mock_session.add.call_count >= 1

    @pytest.mark.asyncio
    @patch('analysis.calculators.confluence_calculator.calculate_confluence', new_callable=AsyncMock)
    async def test_submit_asset_analysis_session_idempotent_update(self, mock_calc_conf):
        """Test that retrying within the same ToolExecutor instance updates existing analysis."""
        mock_calc_conf.return_value = {"computed_score": 8, "max_score": 14, "components": [], "issues": []}
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        
        mock_ts = MagicMock()
        mock_ts.scalar_one_or_none.return_value = datetime.now(timezone.utc)
        mock_price = MagicMock()
        mock_price.scalar_one_or_none.return_value.close = 2025.0
        mock_atr = MagicMock()
        mock_atr.scalar_one_or_none.return_value.value_json = '{"atr": 20.0}'
        mock_brief = MagicMock()
        mock_brief.scalar_one_or_none.return_value = 11

        def execute_side_effect(*args, **kwargs):
            query = str(args[0]).lower()
            if 'max(' in query or 'min(' in query:
                return mock_ts
            elif 'price_ohlcv' in query:
                return mock_price
            elif 'technical_indicators' in query and 'timestamp' in query and 'indicator_name' not in query:
                return mock_ts
            elif 'technical_indicators' in query:
                return mock_atr
            elif 'fundamental_briefs' in query:
                return mock_brief
            empty = MagicMock()
            empty.scalars.return_value.all.return_value = []
            empty.scalar_one_or_none.return_value = None
            return empty

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        
        saved_obj = None
        def assign_id():
            nonlocal saved_obj
            for obj in mock_session.add.call_args_list:
                if isinstance(obj[0][0], AssetAnalysis):
                    obj[0][0].id = 101
                    saved_obj = obj[0][0]

        mock_session.flush.side_effect = assign_id
        mock_session.get.side_effect = lambda model, pk: saved_obj if pk == 101 else None

        executor = ToolExecutor(mock_session)
        
        payload = {
            "symbol": "XAUUSD",
            "decision": "buy",
            "confidence": 0.8,
            "confluence_score": 8,
            "priced_in_score": 4,
            "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
            "entry_condition": {"type": "market", "detail": "Enter market price now"},
            "stop_loss": 1950.0,
            "take_profit": 2200.0,
            "rationale": "First attempt",
            "invalidation": "Price drops below 1950",
            "invalidation_price": 1950.0,
            "invalidation_direction": "below",
            "reevaluation_trigger": {"type": "price_level", "detail": "Price stalls", "price": 2100.0, "direction": "below"}
        }
        res1 = await executor._tool_submit_asset_analysis(payload)
        assert res1["status"] == "saved"
        assert res1["analysis_id"] == 101
        assert mock_session.add.call_count == 2 # 1 AssetAnalysis + 1 TradeTrigger

        # Second call in SAME session (e.g. retry / fallback model)
        payload["rationale"] = "Updated rationale after tool retry"
        payload["confidence"] = 0.85
        res2 = await executor._tool_submit_asset_analysis(payload)
        assert res2["status"] == "saved"
        assert res2["analysis_id"] == 101
        assert "updated" in res2["message"]
        # No extra add() call for AssetAnalysis on second submit
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    @patch('analysis.calculators.confluence_calculator.calculate_confluence', new_callable=AsyncMock)
    async def test_submit_asset_analysis_cancels_superseded_triggers(self, mock_calc_conf):
        """Test that submitting a new analysis cancels older pending triggers for the same symbol."""
        mock_calc_conf.return_value = {"computed_score": 8, "max_score": 14, "components": [], "issues": []}
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        
        # Mock execution for queries:
        # prev_pending_stmt query returns [10, 11] (two old pending triggers)
        mock_prev_triggers = MagicMock()
        mock_prev_triggers.scalars.return_value.all.return_value = [10, 11]
        
        def execute_side_effect(*args, **kwargs):
            query = str(args[0]).lower()
            if 'trade_triggers' in query and 'select' in query:
                return mock_prev_triggers
            empty = MagicMock()
            empty.scalars.return_value.all.return_value = []
            empty.scalar_one_or_none.return_value = None
            return empty
            
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        
        executor = ToolExecutor(mock_session)
        payload = {
            "symbol": "EURUSD",
            "decision": "wait",
            "confidence": 0.7,
            "confluence_score": 6,
            "priced_in_score": 3,
            "rationale": "Waiting for pullback",
            "invalidation": "Price breaks above 1.0950",
            "reevaluation_trigger": {"type": "price_level", "detail": "Pullback to 1.0850", "price": 1.0850, "direction": "below", "symbol": "EURUSD"}
        }
        res = await executor._tool_submit_asset_analysis(payload)
        assert res["status"] == "saved"
        # execute called: cancel update query executed
        assert mock_session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_price_momentum_success(self):
        """Test price momentum tool with sufficient data and ATR available."""
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        now = datetime.now(timezone.utc)
        from datetime import timedelta

        # 21 bars: oldest close = 2000.0, newest close = 2050.0
        price_bars = []
        for i in range(21):
            bar = MagicMock(spec=PriceOHLCV)
            bar.close = 2000.0 + i * 2.5  # gradual rise
            bar.timestamp = now - timedelta(hours=(20 - i) * 4)
            price_bars.append(bar)

        # ATR mock
        atr_row = MagicMock(spec=TechnicalIndicator)
        atr_row.value_json = json.dumps(25.0)  # ATR = 25.0

        mock_price_result = MagicMock()
        mock_price_result.scalars().all.return_value = list(reversed(price_bars))  # DESC order from DB

        mock_atr_result = MagicMock()
        mock_atr_result.scalar_one_or_none.return_value = atr_row

        mock_session.execute = AsyncMock(side_effect=[mock_price_result, mock_atr_result])

        res = await executor._tool_get_price_momentum({"symbol": "XAUUSD", "timeframe": "H4", "lookback_bars": 20})

        assert res["symbol"] == "XAUUSD"
        assert res["timeframe"] == "H4"
        assert "pct_change" in res
        assert res["direction"] == "bullish"
        assert res["atr_14"] == 25.0
        assert res["run_up_vs_atr"] is not None
        assert res["priced_in_risk_from_momentum"] in ["low", "moderate", "moderate_high", "high"]
        assert "momentum_score_for_priced_in" in res
        assert "interpretation" in res

    @pytest.mark.asyncio
    async def test_get_price_momentum_insufficient_data(self):
        """Test price momentum tool when fewer than 2 bars available."""
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []  # no data

        mock_session.execute = AsyncMock(return_value=mock_result)

        res = await executor._tool_get_price_momentum({"symbol": "EURUSD", "timeframe": "H4"})

        assert "error" in res
        assert "Insufficient" in res["error"]

    @pytest.mark.asyncio
    async def test_get_price_momentum_no_atr(self):
        """Test price momentum tool when ATR unavailable (graceful degradation)."""
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        now = datetime.now(timezone.utc)
        from datetime import timedelta

        price_bars = []
        for i in range(5):
            bar = MagicMock(spec=PriceOHLCV)
            bar.close = 1.10 + i * 0.001
            bar.timestamp = now - timedelta(hours=(4 - i) * 4)
            price_bars.append(bar)

        mock_price_result = MagicMock()
        mock_price_result.scalars().all.return_value = list(reversed(price_bars))

        mock_atr_result = MagicMock()
        mock_atr_result.scalar_one_or_none.return_value = None  # no ATR

        mock_session.execute = AsyncMock(side_effect=[mock_price_result, mock_atr_result])

        res = await executor._tool_get_price_momentum({"symbol": "EURUSD", "timeframe": "H4"})

        assert "error" not in res
        assert res["atr_14"] is None
        assert res["run_up_vs_atr"] is None
        assert res["priced_in_risk_from_momentum"] == "unknown_no_atr"
        assert "interpretation" in res

    @pytest.mark.asyncio
    async def test_submit_fundamental_brief_with_priced_in(self):
        """Test that priced_in_assessment is stored in structured_json."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        executor = ToolExecutor(mock_session)
        
        executor.called_tools.add("get_dxy")
        executor.called_tools.add("get_vix")
    
        def assign_id(brief):
            brief.id = 77

        mock_session.refresh.side_effect = assign_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        priced_in = {
            "dominant_driver": "Fed rate cut expectations",
            "priced_in_score": 8,
            "sell_the_news_risk": "high",
            "key_unpriced_drivers": ["ECB surprise"],
            "upcoming_event_context": "FOMC in 12h, 87% cut probability.",
            "cot_positioning_percentile": 80,
            "retail_sentiment_percentile": 20
        }

        res = await executor._tool_submit_fundamental_brief({
            "macro_narrative": "test narrative with DXY and VIX mentioned",
            "currency_bias": {"USD": "bearish", "EUR": "bullish", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "bullish", "OIL": "bearish", "BTC": "bullish"},
            "key_upcoming_risks": [],
            "risk_sentiment": "risk-on",
            "macro_regime": "mixed",
            "confidence": 0.75,
            "invalidation_conditions": {
                "USD": "dxy drops below 103 level and stays there for more than 2 days",
                "EUR": "ecb cuts rates by 50bps and indicates more cuts are coming",
                "XAU": "yields surge above 4.5% and stay elevated through the week",
                "OIL": "demand drops by 100k bpd according to the next eia report",
                "BTC": "etf outflows > 1B and regulatory scrutiny increases significantly"
            },
            "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.9, "OIL": 0.6, "BTC": 0.75},
            "strongest_counter_thesis": "This is a sufficiently long counter thesis string that will pass the length validation check required by the system.",
            "priced_in_assessment": priced_in,
            "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
            "key_data_points_used": {
                "dxy_trend_5d": "strengthening +0.8%",
                "vix_close": 15.5,
                "fedwatch_dominant_pct": 85.0
            }
        })

        assert res["status"] == "saved"
        assert res["brief_id"] == 77

        # Verify priced_in_assessment stored in structured_json
        args, _ = mock_session.add.call_args
        brief_obj = args[0]
        assert isinstance(brief_obj, FundamentalBrief)
        stored = json.loads(brief_obj.structured_json)
        assert stored["priced_in_assessment"] is not None
        assert stored["priced_in_assessment"]["priced_in_score"] == 8
        assert stored["priced_in_assessment"]["sell_the_news_risk"] == "high"

    @pytest.mark.asyncio
    async def test_submit_fundamental_brief_weak_invalidation_rejected(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)
        executor.called_tools.add("get_dxy")
        executor.called_tools.add("get_vix")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        # OIL non-neutral with generic/short invalidation condition without digits
        payload = {
            "macro_narrative": "test narrative with DXY and VIX mentioned",
            "currency_bias": {"USD": "bullish", "EUR": "bearish", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "bearish", "OIL": "bearish", "BTC": "bullish"},
            "key_upcoming_risks": [],
            "risk_sentiment": "risk-on",
            "macro_regime": "mixed",
            "confidence": 0.8,
            "invalidation_conditions": {
                "USD": "dxy drops below 103 level and stays there for more than 2 days",
                "EUR": "ecb cuts rates by 50bps and indicates more cuts are coming",
                "XAU": "yields surge above 4.5% and stay elevated through the week",
                "OIL": "geopolitical risks ease",  # Too short (<40 chars) and no digits
                "BTC": "etf outflows > 1B and regulatory scrutiny increases significantly"
            },
            "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.9, "OIL": 0.6, "BTC": 0.75},
            "strongest_counter_thesis": "This is a sufficiently long counter thesis string that will pass the length validation check required by the system.",
            "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
            "key_data_points_used": {
                "dxy_trend_5d": "strengthening +0.8%",
                "vix_close": 15.5,
                "fedwatch_dominant_pct": 85.0
            },
            "priced_in_assessment": {
                "dominant_driver": "Fed rate cut expectations",
                "priced_in_score": 5,
                "sell_the_news_risk": "low",
                "cot_positioning_percentile": 50,
                "retail_sentiment_percentile": 50
            }
        }

        res = await executor._tool_submit_fundamental_brief(payload)
        assert res["status"] == "rejected"
        assert any("WEAK_INVALIDATION" in err for err in res["errors"])
        assert any("OIL" in err for err in res["errors"])

    @pytest.mark.asyncio
    async def test_check_anchoring_and_require_justification(self):
        from datetime import datetime, timedelta
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        # Mock 4 distinct cycle briefs in DB (spaced 1 hour apart)
        base_time = datetime(2026, 8, 25, 12, 0, 0)
        mock_briefs = []
        for i in range(4):
            mb = MagicMock()
            mb.generated_at = base_time - timedelta(hours=i * 6)
            mb.currency_bias = {"BTC": "bullish", "USD": "bearish", "EUR": "neutral"}
            mb.structured_json = None
            mock_briefs.append(mb)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_briefs
        mock_session.execute = AsyncMock(return_value=mock_result)

        # 1. Test rejected when justification is missing or short or no digits
        errors = await executor._check_anchoring_and_require_justification(
            current_bias={"BTC": "bullish", "USD": "bearish"},
            justification_map={"BTC": "bullish continuation", "USD": ""}  # Short, no digits
        )
        assert len(errors) == 2
        assert any("BTC" in e and "ANCHORING_RISK" in e for e in errors)
        assert any("USD" in e and "ANCHORING_RISK" in e for e in errors)
        assert any("bias_continuity_justification" in e for e in errors)

        # 2. Test accepted when justification is >=40 chars and contains numeric data
        errors_valid = await executor._check_anchoring_and_require_justification(
            current_bias={"BTC": "bullish", "USD": "bearish"},
            justification_map={
                "BTC": "BTC bullish dipertahankan karena ETF inflows +240M USD pada 2026-08-22 dan funding rate stabil di 0.01%",
                "USD": "USD bearish dipertahankan karena DXY melemah 0.4% ke 102.30 dan US10Y turun 5 bps ke 4.10%"
            }
        )
        assert len(errors_valid) == 0

    @pytest.mark.asyncio
    async def test_check_anchoring_distinct_cycle_deduplication(self):
        """Test that multiple briefs generated in the same 30m window are deduplicated and do not falsely trigger anchoring."""
        from datetime import datetime, timedelta
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)

        # 3 briefs generated in the same 10-minute window, and 1 brief from 6 hours ago (total 2 distinct cycles)
        now = datetime(2026, 8, 25, 2, 45, 0)
        b1 = MagicMock(generated_at=now, currency_bias={"BTC": "bullish"}, structured_json=None)
        b2 = MagicMock(generated_at=now - timedelta(minutes=3), currency_bias={"BTC": "bullish"}, structured_json=None)
        b3 = MagicMock(generated_at=now - timedelta(minutes=7), currency_bias={"BTC": "bullish"}, structured_json=None)
        b4 = MagicMock(generated_at=now - timedelta(hours=6), currency_bias={"BTC": "bullish"}, structured_json=None)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [b1, b2, b3, b4]
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Because there are only 2 distinct cycles (< 4), anchoring check should NOT trigger
        errors = await executor._check_anchoring_and_require_justification(
            current_bias={"BTC": "bullish"},
            justification_map={}
        )
        assert len(errors) == 0


    @pytest.mark.asyncio
    async def test_submit_fundamental_brief_weekend_mode(self):
        """Test that on weekend, crypto priced-in without COT report is accepted."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        executor = ToolExecutor(mock_session)
        executor.called_tools.add("get_dxy")
        executor.called_tools.add("get_vix")
        executor.called_tools.add("get_funding_rate")

        def assign_id(brief):
            brief.id = 88
        mock_session.refresh.side_effect = assign_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Payload during weekend mode (only crypto active, no FX COT)
        with patch("analysis.tools.tool_executor.clock.now") as mock_now:
            from datetime import datetime, timezone
            # Sunday 2026-08-23
            mock_now.return_value = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

            payload = {
                "macro_narrative": "test narrative weekend DXY and VIX mentioned",
                "currency_bias": {"USD": "neutral", "EUR": "neutral", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "neutral", "OIL": "neutral", "BTC": "bullish"},
                "key_upcoming_risks": [],
                "risk_sentiment": "risk-on",
                "macro_regime": "mixed",
                "confidence": 0.8,
                "invalidation_conditions": {
                    "BTC": "etf outflows > 1B and regulatory scrutiny increases significantly"
                },
                "currency_confidence": {"BTC": 0.75},
                "strongest_counter_thesis": "This is a sufficiently long counter thesis string that will pass the length validation check required by the system.",
                "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
                "key_data_points_used": {
                    "dxy_trend_5d": "strengthening +0.8%",
                    "vix_close": 15.5,
                    "fedwatch_dominant_pct": 85.0
                },
                "priced_in_assessment": {
                    "dominant_driver": "BTC weekend risk sentiment & Fed policy",
                    "priced_in_score": 5,
                    "sell_the_news_risk": "low",
                    "funding_rate": 0.01
                }
            }

            res = await executor._tool_submit_fundamental_brief(payload)
            assert res["status"] == "saved"
            assert res["brief_id"] == 88

    @pytest.mark.asyncio
    async def test_tool_executor_symbol_resilience_and_auto_injection(self):
        """Test ToolExecutor symbol binding, auto-injection on missing symbol, and alias resolution."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        
        def assign_id():
            for obj in mock_session.add.call_args_list:
                if isinstance(obj[0][0], AssetAnalysis):
                    obj[0][0].id = 202

        mock_session.flush.side_effect = assign_id
        
        # 1. ToolExecutor bound with symbol="EURUSD"
        executor = ToolExecutor(mock_session, symbol="EURUSD")
        assert executor.symbol == "EURUSD"
        
        # 2. Call submit_asset_analysis WITHOUT symbol key in payload
        payload_no_symbol = {
            "decision": "wait",
            "confidence": 0.5,
            "rationale": "Waiting for pullback to support level",
            "invalidation": "Thesis invalid if price breaks 1.0750",
            "reevaluation_trigger": {"type": "time", "detail": "Wait 4h"}
        }
        res = await executor._tool_submit_asset_analysis(payload_no_symbol)
        assert res["status"] == "saved"
        assert res["symbol"] == "EURUSD"
        assert res["decision"] == "wait"
        
        # 3. Call submit_asset_analysis with alias key 'asset'
        payload_with_alias = {
            "asset": "GBPUSD",
            "decision": "avoid",
            "confidence": 0.5,
            "rationale": "Avoid trading today due to major news event",
            "invalidation": "N/A"
        }
        res_alias = await executor._tool_submit_asset_analysis(payload_with_alias)
        assert res_alias["status"] == "saved"
        assert res_alias["symbol"] == "GBPUSD"
        assert res_alias["decision"] == "avoid"

    @pytest.mark.asyncio
    async def test_validate_fundamental_brief_auto_fill_cot(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session)
        executor.called_tools.add("get_dxy")
        executor.called_tools.add("get_vix")

        # Mock weekday Tuesday
        with patch("analysis.tools.tool_executor.clock.now") as mock_now, \
             patch("analysis.calculators.macro_priced_in_calculator.calculate_macro_priced_in_baseline", new_callable=AsyncMock) as mock_baseline:
            
            from datetime import datetime, timezone
            mock_now.return_value = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
            mock_baseline.return_value = {
                "cot_positioning_percentile": 62.5,
                "total_auto": 4
            }

            # Brief where priced_in_assessment has no cot_positioning_percentile
            inp = {
                "macro_narrative": "DXY is weakening and VIX is low, indicating risk-on sentiment.",
                "currency_bias": {
                    "USD": "bearish", "EUR": "bullish", "GBP": "neutral",
                    "JPY": "neutral", "AUD": "neutral", "XAU": "bullish"
                },
                "invalidation_conditions": {
                    "USD": "Bias USD bearish batal jika DXY D1 close di atas 104.50",
                    "EUR": "Bias EUR bullish batal jika EURUSD D1 close di bawah 1.0750",
                    "XAU": "Bias XAU bullish batal jika XAUUSD D1 close di bawah 2350.00"
                },
                "currency_confidence": {"USD": 0.7, "EUR": 0.65, "XAU": 0.6},
                "strongest_counter_thesis": "Jika NFP melampaui ekspektasi >250k pada rilis Jumat, USD akan rebound tajam.",
                "priced_in_assessment": {
                    "dominant_driver": "Fed 25bps cut expectations",
                    "priced_in_score": 5,
                    "sell_the_news_risk": "medium"
                    # cot_positioning_percentile intentionally omitted
                }
            }

            errors = await executor._validate_fundamental_brief_completeness(inp)
            assert len(errors) == 0
            # Auto-filled from baseline!
            assert inp["priced_in_assessment"]["cot_positioning_percentile"] == 62.5

    @pytest.mark.asyncio
    async def test_tool_get_fundamental_brief_staleness_thresholds(self):
        from datetime import timedelta
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={})

        now = datetime.now(timezone.utc)
        # 1. 6 hours old brief (should NOT trigger CRITICAL or STALE under 12.0/10.0 thresholds)
        brief_6h = FundamentalBrief(
            id=101,
            generated_at=now - timedelta(hours=6),
            valid_until=now + timedelta(hours=6),
            structured_json=json.dumps({"currency_bias": {"USD": "bullish"}})
        )

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = brief_6h
        mock_session.execute = AsyncMock(return_value=mock_res)

        res_6h = await executor._tool_get_fundamental_brief({})
        assert "🚨 CRITICAL" not in res_6h["staleness_warning"]
        assert "MANDATORY WAIT" not in res_6h["staleness_warning"]
        assert "⚠️ STALE" not in res_6h["staleness_warning"]
        assert res_6h["is_stale"] is False

        # 2. 13 hours old brief (exceeds 12.0h critical threshold)
        brief_13h = FundamentalBrief(
            id=102,
            generated_at=now - timedelta(hours=13),
            valid_until=now - timedelta(hours=1),
            structured_json=json.dumps({"currency_bias": {"USD": "bullish"}})
        )
        mock_res.scalar_one_or_none.return_value = brief_13h

        res_13h = await executor._tool_get_fundamental_brief({})
        assert "🚨 CRITICAL" in res_13h["staleness_warning"]
        assert "MANDATORY WAIT" in res_13h["staleness_warning"]
        assert res_13h["is_stale"] is True

        # 3. 10.5 hours old brief under production settings (both execution & analysis = 12.0)
        executor_prod = ToolExecutor(mock_session, settings={
            "data_quality": {
                "max_brief_age_execution_hours": 12.0,
                "max_brief_age_analysis_hours": 12.0,
            }
        })
        brief_10_5h = FundamentalBrief(
            id=103,
            generated_at=now - timedelta(hours=10, minutes=30),
            valid_until=now + timedelta(hours=1, minutes=30),
            structured_json=json.dumps({"currency_bias": {"USD": "bullish"}})
        )
        mock_res.scalar_one_or_none.return_value = brief_10_5h
        res_10_5h = await executor_prod._tool_get_fundamental_brief({})
        assert "⚠️ STALE" in res_10_5h["staleness_warning"]
        assert "🚨 CRITICAL" not in res_10_5h["staleness_warning"]
        assert res_10_5h["is_stale"] is False



