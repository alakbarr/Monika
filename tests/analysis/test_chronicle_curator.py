from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.memory.chronicle_curator import (
    ActionDecision,
    ChronicleCurator,
    CuratedMilestoneProposal,
    WeeklyConsolidationOutput,
)
from monika.infrastructure.database.models import MarketChronicle
from tests.conftest import create_mock_async_session


class TestChronicleCurator:
    @pytest.mark.asyncio
    async def test_schedule_guard_skips_non_monday_unless_forced(self):
        curator = ChronicleCurator({})
        mock_session = create_mock_async_session()

        # Wednesday (weekday == 2)
        wednesday = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
        assert wednesday.weekday() == 2

        with patch("monika.core.primitives.clock.now", return_value=wednesday):
            result = await curator.consolidate_matured_tactical_events(mock_session, force=False)
            assert result["status"] == "skipped"
            assert "Monday morning" in result["reason"]

    @pytest.mark.asyncio
    async def test_noop_when_no_matured_tactical_events(self):
        curator = ChronicleCurator({})
        mock_session = create_mock_async_session()

        # Monday (weekday == 0)
        monday = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
        assert monday.weekday() == 0

        # Mock query returns empty list
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("monika.core.primitives.clock.now", return_value=monday):
            result = await curator.consolidate_matured_tactical_events(mock_session, force=False)
            assert result["status"] == "noop"
            assert result["matured_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_synthesis_merge_action(self):
        curator = ChronicleCurator({})
        mock_session = create_mock_async_session()
        mock_session.commit = AsyncMock()

        monday = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
        past_date = monday - timedelta(days=35)

        tactical_event = MarketChronicle(
            id=101,
            event_date=past_date,
            category="geopolitical",
            headline="Drone strike near Strait of Hormuz",
            narrative="Oil tanker harassed in Gulf of Oman.",
            currencies_affected="XAUUSD,USD",
            severity="critical",
            source_news_id=999,
            is_ongoing=True,
        )

        permanent_regime = MarketChronicle(
            id=1,
            event_date=past_date - timedelta(days=20),
            category="geopolitical",
            headline="Middle East Conflict & Hormuz Disruption",
            narrative="Ongoing maritime corridor blockades elevating tanker freight rates.",
            currencies_affected="XAUUSD,USD",
            severity="critical",
            source_news_id=None,
            is_ongoing=True,
        )

        # Mock execute queries
        mock_tactical_res = MagicMock()
        mock_tactical_res.scalars().all.return_value = [tactical_event]

        mock_permanent_res = MagicMock()
        mock_permanent_res.scalars().all.return_value = [permanent_regime]

        mock_del_res = MagicMock()
        mock_del_res.rowcount = 1

        mock_session.execute = AsyncMock(side_effect=[mock_tactical_res, mock_permanent_res, mock_del_res])
        mock_session.get = AsyncMock(return_value=permanent_regime)

        # Mock LLM client response
        mock_llm_output = WeeklyConsolidationOutput(
            proposals=[
                CuratedMilestoneProposal(
                    action=ActionDecision.MERGE,
                    target_existing_chronicle_id=1,
                    event_date=past_date.isoformat(),
                    category="geopolitical",
                    headline="Middle East Conflict & Hormuz Disruption (Escalation)",
                    narrative="Ongoing maritime corridor blockades. Drone strikes near Hormuz reinforce safe-haven premium.",
                    currencies_affected="XAUUSD,USD",
                    severity="critical",
                    is_ongoing=True,
                    rationale="Direct extension of Hormuz geopolitical corridor tension.",
                )
            ],
            processed_tactical_ids=[101],
            synthesis_summary="Merged 1 tactical item into existing Hormuz regime.",
        )

        curator._client = MagicMock()
        with (
            patch("monika.core.primitives.clock.now", return_value=monday),
            patch.object(curator, "_run_llm_synthesis", AsyncMock(return_value=mock_llm_output)),
        ):
            result = await curator.consolidate_matured_tactical_events(mock_session, force=False)

            assert result["status"] == "success"
            assert result["stats"]["merged"] == 1
            assert result["stats"]["created"] == 0
            assert result["stats"]["retired"] == 1
            assert "Drone strikes near Hormuz" in permanent_regime.narrative
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_synthesis_create_new_action(self):
        curator = ChronicleCurator({})
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        monday = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
        past_date = monday - timedelta(days=32)

        tactical_event = MarketChronicle(
            id=102,
            event_date=past_date,
            category="policy_change",
            headline="Unexpected emergency rate cut by Swiss National Bank",
            narrative="SNB drops rates by 75bps citing franc strength.",
            currencies_affected="CHF,EUR",
            severity="critical",
            source_news_id=888,
            is_ongoing=False,
        )

        mock_tactical_res = MagicMock()
        mock_tactical_res.scalars().all.return_value = [tactical_event]

        mock_permanent_res = MagicMock()
        mock_permanent_res.scalars().all.return_value = []

        mock_del_res = MagicMock()
        mock_del_res.rowcount = 1

        mock_session.execute = AsyncMock(side_effect=[mock_tactical_res, mock_permanent_res, mock_del_res])

        mock_llm_output = WeeklyConsolidationOutput(
            proposals=[
                CuratedMilestoneProposal(
                    action=ActionDecision.CREATE_NEW,
                    target_existing_chronicle_id=None,
                    event_date=past_date.isoformat(),
                    category="policy_change",
                    headline="SNB Emergency 75bps Rate Cut",
                    narrative="Historic easing cycle initiated by SNB to combat systemic franc appreciation.",
                    currencies_affected="CHF,EUR",
                    severity="critical",
                    is_ongoing=False,
                    rationale="Novel central bank emergency easing with independent macro significance.",
                )
            ],
            processed_tactical_ids=[102],
            synthesis_summary="Created 1 new permanent milestone.",
        )

        curator._client = MagicMock()
        with (
            patch("monika.core.primitives.clock.now", return_value=monday),
            patch.object(curator, "_run_llm_synthesis", AsyncMock(return_value=mock_llm_output)),
        ):
            result = await curator.consolidate_matured_tactical_events(mock_session, force=False)

            assert result["status"] == "success"
            assert result["stats"]["created"] == 1
            assert result["stats"]["merged"] == 0
            assert result["stats"]["retired"] == 1
            mock_session.add.assert_called_once()
            added_milestone = mock_session.add.call_args[0][0]
            assert added_milestone.source_news_id is None
            assert added_milestone.headline == "SNB Emergency 75bps Rate Cut"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deterministic_fallback_synthesis(self):
        curator = ChronicleCurator({})
        curator._client = None  # Force fallback
        mock_session = create_mock_async_session()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        monday = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
        past_date = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

        tactical_event = MarketChronicle(
            id=103,
            event_date=past_date,
            category="geopolitical",
            headline="Diplomatic talks stalled over Black Sea grain corridor",
            narrative="Negotiations fail to reach consensus.",
            currencies_affected="EUR,USD",
            severity="high",
            source_news_id=777,
            is_ongoing=True,
        )

        mock_tactical_res = MagicMock()
        mock_tactical_res.scalars().all.return_value = [tactical_event]

        mock_permanent_res = MagicMock()
        mock_permanent_res.scalars().all.return_value = []

        mock_del_res = MagicMock()
        mock_del_res.rowcount = 1

        mock_session.execute = AsyncMock(side_effect=[mock_tactical_res, mock_permanent_res, mock_del_res])

        with patch("monika.core.primitives.clock.now", return_value=monday):
            result = await curator.consolidate_matured_tactical_events(mock_session, force=True)

            assert result["status"] == "success"
            assert result["stats"]["created"] == 1
            assert result["stats"]["retired"] == 1
            mock_session.add.assert_called_once()
            promoted = mock_session.add.call_args[0][0]
            assert promoted.source_news_id is None
            assert "Macro Synthesis (2026-08)" in promoted.headline
            mock_session.commit.assert_called_once()
