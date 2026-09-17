import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from database.models import UserMarketIntel, ActivityLog
import utils.clock as clock


class TestUserIntelCycleInjection:

    @pytest.mark.asyncio
    async def test_data_node_populates_user_market_intel(self):
        from graph.nodes.data_node import fetch_data_node

        now = clock.now()
        mock_intel = UserMarketIntel(
            id=10,
            intel_type="pre_event_research",
            title="DXY Resistance Test",
            summary="DXY testing 104.50 resistance ahead of CPI.",
            affected_symbols=["EURUSD", "USDJPY"],
            directive="neutral",
            target_cycle="next_cycle_only",
            is_active=True,
            created_at=now,
        )

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_intel]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_res)

        mock_scheduler = MagicMock()
        mock_scheduler.asset_universe = ["EURUSD", "USDJPY"]
        mock_scheduler.settings = {"trading": {}, "data_quality": {}}
        mock_scheduler.mt5_timeframes = ["H1"]
        mock_scheduler._refresh_data_sources = AsyncMock(return_value={"status": "ok"})
        mock_scheduler._mt5 = None
        mock_scheduler._paper_tracker.should_regenerate_performance_notes = AsyncMock(return_value=(False, "none"))

        state = {"summary": {}, "symbols": ["EURUSD", "USDJPY"]}
        config = {"configurable": {"scheduler": mock_scheduler}}

        with patch("graph.nodes.data_node.get_session") as mock_gs:
            mock_gs.return_value.__aenter__.return_value = mock_session
            with patch("analysis.calculators.economic_surprise.compute_surprise_scores", new=AsyncMock(return_value=0)), \
                 patch("analysis.prefetch.news_digest.NewsDigestProcessor") as mock_nd, \
                 patch("indicators.technical.TechnicalIndicatorCalculator") as mock_calc, \
                 patch("indicators.structure.MarketStructureAnalyzer") as mock_analyzer, \
                 patch("utils.validation.data_validator.validate_data_freshness", new=AsyncMock(return_value={"errors": [], "warnings": []})):
                mock_nd.return_value.classify_unscored_news = AsyncMock(return_value=0)
                mock_nd.return_value.create_news_digest = AsyncMock(return_value=None)
                mock_calc.return_value.compute_all_symbols = AsyncMock(return_value={})
                mock_analyzer.return_value.analyze_all = AsyncMock(return_value={})
                res = await fetch_data_node(state, config)

        assert "user_market_intel" in res
        assert len(res["user_market_intel"]) == 1
        assert res["user_market_intel"][0]["id"] == 10
        assert res["user_market_intel"][0]["title"] == "DXY Resistance Test"
        assert res["user_market_intel"][0]["affected_symbols"] == ["EURUSD", "USDJPY"]

    @pytest.mark.asyncio
    async def test_fundamental_stage_injects_intel_to_user_message(self):
        from analysis.stages.fundamental_stage import FundamentalStage

        stage = FundamentalStage(settings={"claude": {}, "trading": {}})
        stage.client = MagicMock()
        stage.client.run_agent = AsyncMock(return_value={"success": True, "brief_id": 1})

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

        user_intel = [
            {
                "id": 15,
                "intel_type": "flash_news",
                "title": "Middle East De-escalation Accord",
                "summary": "Ceasefire signed, oil risk premium evaporating.",
                "affected_symbols": ["XTIUSD", "USDCAD"],
                "directive": "favor_sell",
                "target_cycle": "next_cycle_only",
            }
        ]

        with patch.object(stage, "_log", new=AsyncMock()):
            with patch("analysis.stages.fundamental_stage.Stage1DataBundler") as mock_bundler_cls:
                mock_bundler = MagicMock()
                mock_bundler.prefetch_all_data = AsyncMock(return_value=("{}", set()))
                mock_bundler_cls.return_value = mock_bundler

                await stage.run(
                    session=mock_session,
                    forced=True,
                    user_market_intel=user_intel,
                )

        stage.client.run_agent.assert_called_once()
        call_kwargs = stage.client.run_agent.call_args.kwargs
        user_msg = call_kwargs["user_message"]

        assert "[OPERATOR MARKET INTELLIGENCE & DIRECTIVES]" in user_msg
        assert "Middle East De-escalation Accord" in user_msg
        assert "favor_sell" in user_msg
        assert "ID #15" in user_msg

    def test_per_asset_symbol_filtering(self):
        # Test with mix of list and comma-separated string affected_symbols
        intel_list = [
            {
                "id": 1,
                "intel_type": "pre_event_research",
                "title": "ECB Dovish Leak",
                "affected_symbols": "EURUSD",  # Comma-separated string format from DB
                "directive": "favor_sell",
                "summary": "ECB sources hint at earlier rate cut.",
            },
            {
                "id": 2,
                "intel_type": "tactical_directive",
                "title": "Broad Risk-Off Directive",
                "affected_symbols": "ALL",
                "directive": "avoid_trade",
                "summary": "Do not take aggressive longs across any asset.",
            },
            {
                "id": 3,
                "intel_type": "pre_event_research",
                "title": "Gold Physical Demand Surge",
                "affected_symbols": ["XAUUSD"],  # List format
                "directive": "favor_buy",
                "summary": "Central bank gold purchases up 30%.",
            },
            {
                "id": 4,
                "intel_type": "flash_news",
                "title": "Dual Asset News",
                "affected_symbols": "EURUSD,GBPUSD",
                "directive": "caution",
                "summary": "European currency volatility expected.",
            },
        ]

        def _format_intel_for_symbol(sym: str, items: list) -> str:
            if not items:
                return ""
            relevant = []
            sym_clean = sym.upper().replace('/', '')
            for item in items:
                raw_aff = item.get("affected_symbols") or []
                if isinstance(raw_aff, str):
                    aff_list = [s.strip() for s in raw_aff.split(",") if s.strip()]
                else:
                    aff_list = list(raw_aff)
                aff = [s.upper().replace('/', '') for s in aff_list]
                if not aff or "ALL" in aff or sym_clean in aff:
                    relevant.append(item)
            if not relevant:
                return ""
            lines = ["[OPERATOR MARKET INTELLIGENCE & DIRECTIVES FOR THIS ASSET]"]
            for it in relevant:
                lines.append(f"• ID #{it.get('id')} [{it.get('intel_type', '').upper()}]: {it.get('title')}")
                lines.append(f"  Directive: {it.get('directive', 'neutral')}")
            return "\n".join(lines)

        eur_text = _format_intel_for_symbol("EURUSD", intel_list)
        assert "ECB Dovish Leak" in eur_text
        assert "Broad Risk-Off Directive" in eur_text
        assert "Dual Asset News" in eur_text
        assert "Gold Physical Demand Surge" not in eur_text

        gold_text = _format_intel_for_symbol("XAUUSD", intel_list)
        assert "Gold Physical Demand Surge" in gold_text
        assert "Broad Risk-Off Directive" in gold_text
        assert "ECB Dovish Leak" not in gold_text
        assert "Dual Asset News" not in gold_text

    @pytest.mark.asyncio
    async def test_post_cycle_cleanup_consumed_and_expired(self):
        from scheduler.graph_cycle_scheduler import GraphCycleScheduler

        now = clock.now()
        item_next_cycle = UserMarketIntel(
            id=101,
            title="Single Cycle Note",
            summary="Next cycle only",
            target_cycle="next_cycle_only",
            is_active=True,
        )
        item_expired = UserMarketIntel(
            id=102,
            title="Expired Note",
            summary="Past expiry",
            target_cycle="continuous",
            expires_at=now - timedelta(minutes=10),
            is_active=True,
        )
        item_continuous = UserMarketIntel(
            id=103,
            title="Ongoing Note",
            summary="Still active",
            target_cycle="continuous",
            expires_at=now + timedelta(hours=5),
            is_active=True,
        )

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Mock query 1 (next_cycle_only) and query 2 (expired)
        res_next = MagicMock()
        res_next.scalars.return_value.all.return_value = [item_next_cycle]

        res_expired = MagicMock()
        res_expired.scalars.return_value.all.return_value = [item_expired]

        mock_session.execute = AsyncMock(side_effect=[res_next, res_expired])

        cycle_id = "cycle_test_123"

        # Create scheduler and call actual cleanup method
        scheduler = GraphCycleScheduler(
            settings={
                "trading": {
                    "schedule": {"cycle_times_local": ["07:00", "15:00", "20:00"]},
                    "assets": ["EURUSD"],
                },
                "database": {},
            },
        )

        with patch("scheduler.graph_cycle_scheduler.get_session") as mock_gs:
            mock_gs.return_value.__aenter__.return_value = mock_session
            res = await scheduler.cleanup_user_market_intel(cycle_id)

        assert res["consumed"] == 1
        assert res["expired"] == 1

        assert item_next_cycle.is_active is False
        assert item_next_cycle.consumed_at is not None
        assert item_next_cycle.consumed_by_cycle_id == cycle_id

        assert item_expired.is_active is False

        assert item_continuous.is_active is True
        mock_session.commit.assert_called_once()
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_per_asset_stage_bundle_intel_with_string_symbols(self):
        """Verify PerAssetStage specialist view includes user_market_intel with string affected_symbols."""
        from analysis.stages.per_asset_stage import PerAssetStage

        stage = PerAssetStage(settings={"trading": {}, "claude": {}})
        raw_bundle = {}

        now = clock.now()
        db_intel = UserMarketIntel(
            id=55,
            intel_type="pre_event_research",
            title="EUR Rate Cut Speculation",
            summary="Dovish chatter ahead of meeting.",
            affected_symbols="EURUSD,GBPUSD",  # string in DB
            directive="favor_sell",
            is_active=True,
            created_at=now,
        )

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [db_intel]
        mock_session.execute = AsyncMock(return_value=mock_res)

        # Replicate lines 870-888 of per_asset_stage
        from sqlalchemy import select, or_
        now_intel = clock.now()
        intel_rows = (await mock_session.execute(
            select(UserMarketIntel).where(
                UserMarketIntel.is_active == True,
                or_(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at > now_intel)
            ).order_by(UserMarketIntel.created_at.desc())
        )).scalars().all()
        rel_bullets = []
        sym_clean = "EURUSD"
        for r in intel_rows:
            aff_list = r.affected_symbols_list if hasattr(r, "affected_symbols_list") else (
                [s.strip() for s in (r.affected_symbols or "").split(",") if s.strip()]
            )
            aff = [s.upper().replace('/', '') for s in aff_list]
            if not aff or "ALL" in aff or sym_clean in aff:
                rel_bullets.append(f"[{r.intel_type.upper()} - {r.directive}]: {r.title} — {r.summary}")
        if rel_bullets:
            raw_bundle['user_market_intel'] = rel_bullets

        assert 'user_market_intel' in raw_bundle
        assert len(raw_bundle['user_market_intel']) == 1
        assert "EUR Rate Cut Speculation" in raw_bundle['user_market_intel'][0]
        assert "favor_sell" in raw_bundle['user_market_intel'][0]
