import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from analysis.tools.tool_executor import ToolExecutor
from database.models import UserMarketIntel, MarketChronicle


class TestMarketIntelligenceTools:

    @pytest.mark.asyncio
    async def test_tool_web_search(self):
        mock_session = AsyncMock()
        executor = ToolExecutor(mock_session, settings={})

        mock_search_res = {
            "query": "FOMC rate cuts",
            "source": "tavily",
            "results": [
                {"title": "FOMC Preview", "url": "https://example.com", "content": "Rate cut expected"}
            ],
            "total_results": 1,
        }

        with patch("data_sources.web_search.get_web_search_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.search = AsyncMock(return_value=mock_search_res)
            mock_get_svc.return_value = mock_svc

            res = await executor._tool_web_search({"query": "FOMC rate cuts", "search_depth": "fast"})

        assert res["status"] == "success"
        assert res["source"] == "tavily"
        assert len(res["results"]) == 1

    @pytest.mark.asyncio
    async def test_tool_save_market_intelligence_basic(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda obj: setattr(obj, 'id', 42))
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        executor = ToolExecutor(mock_session, settings={})

        params = {
            "title": "US Non-Farm Payrolls Whisper",
            "summary": "Consensus 175k, whisper numbers 140k-150k hinting at labor cooling.",
            "intel_type": "pre_event_research",
            "affected_symbols": ["EURUSD", "USDJPY"],
            "directive": "favor_buy",
            "target_cycle": "next_cycle_only",
            "expiry_hours": 6,
        }

        res = await executor._tool_save_market_intelligence(params)

        assert res["status"] == "success"
        assert res["intel_id"] == 42
        assert res["directive"] == "favor_buy"
        assert res["affected_symbols"] == ["EURUSD", "USDJPY"]
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_save_market_intelligence_cross_posts_macro_structural(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda obj: setattr(obj, 'id', 99))
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        executor = ToolExecutor(mock_session, settings={})

        params = {
            "title": "Middle East Strait Closure Escalation",
            "summary": "Key shipping lane blocked, oil freight rates spiking 40%.",
            "intel_type": "macro_structural",
            "affected_symbols": ["XTIUSD", "USDCAD"],
            "directive": "favor_buy",
            "target_cycle": "continuous",
        }

        res = await executor._tool_save_market_intelligence(params)

        assert res["status"] == "success"
        assert res["intel_id"] == 99
        # mock_session.add called 3 times: UserMarketIntel, MarketChronicle, ActivityLog
        assert mock_session.add.call_count == 3
        added_objs = [call[0][0] for call in mock_session.add.call_args_list]
        types = [type(obj) for obj in added_objs]
        assert UserMarketIntel in types
        assert MarketChronicle in types

    @pytest.mark.asyncio
    async def test_tool_list_active_intelligence(self):
        mock_session = AsyncMock()
        now = datetime.now(timezone.utc)
        
        intel_item1 = UserMarketIntel(
            id=1,
            title="Intel 1",
            summary="EUR summary",
            intel_type="pre_event_research",
            affected_symbols=["EURUSD"],
            directive="favor_buy",
            target_cycle="next_cycle_only",
            is_active=True,
            created_at=now,
        )
        intel_item2 = UserMarketIntel(
            id=2,
            title="Intel 2",
            summary="Global macro shock",
            intel_type="macro_structural",
            affected_symbols=["ALL"],
            directive="avoid_trade",
            target_cycle="continuous",
            is_active=True,
            created_at=now,
        )

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [intel_item1, intel_item2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        executor = ToolExecutor(mock_session, settings={})

        # Test listing without symbol filter
        res_all = await executor._tool_list_active_intelligence({})
        assert res_all["status"] == "success"
        assert res_all["count"] == 2

        # Test listing with symbol filter EURUSD (should match intel_item1 and intel_item2 since ALL is included)
        res_eur = await executor._tool_list_active_intelligence({"symbol": "EURUSD"})
        assert res_eur["status"] == "success"
        assert res_eur["count"] == 2

    @pytest.mark.asyncio
    async def test_tool_archive_market_intelligence(self):
        mock_session = AsyncMock()
        intel_item = UserMarketIntel(
            id=7,
            title="To be archived",
            summary="Old intel",
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = intel_item
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        executor = ToolExecutor(mock_session, settings={})
        res = await executor._tool_archive_market_intelligence({"intel_id": 7})

        assert res["status"] == "success"
        assert res["intel_id"] == 7
        assert intel_item.is_active is False
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
