import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from analysis.prefetch.digest_slice_generator import DigestSliceGenerator
from database.models import NewsItem, NewsDigestSlice


class TestDigestSliceGenerator:

    @pytest.mark.asyncio
    async def test_generate_slice_with_items(self):
        generator = DigestSliceGenerator({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        item1 = NewsItem(
            id=1,
            title="Fed emergency rate cut 50bps",
            summary="Fed cuts rates in surprise move",
            currency_tags="USD,XAU",
            impact="BREAKING",
            sentiment="BEARISH_USD,BULLISH_XAU,SURPRISE_LARGE",
            fetched_at=datetime.now(timezone.utc)
        )
        item2 = NewsItem(
            id=2,
            title="ECB holds rates steady",
            summary="Lagarde speaks",
            currency_tags="EUR",
            impact="HIGH",
            sentiment="NEUTRAL",
            fetched_at=datetime.now(timezone.utc)
        )

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [item1, item2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        generator._macro_synth.generate = AsyncMock(return_value="USD bias: BEARISH on surprise rate cut.")
        generator._digest_generator.generate = AsyncMock(return_value="EUR bias: NEUTRAL on ECB pause.")

        now_utc = datetime.now(timezone.utc)
        slice_res = await generator.generate_slice(
            mock_session,
            period_start=now_utc - timedelta(hours=2),
            period_end=now_utc,
            trigger="scheduled"
        )

        assert slice_res is not None
        assert slice_res.breaking_count == 1
        assert slice_res.high_count == 1
        assert slice_res.items_processed == 2
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_assemble_12h_digest(self):
        generator = DigestSliceGenerator({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        slice1 = NewsDigestSlice(
            id=1,
            period_start=datetime.now(timezone.utc) - timedelta(hours=4),
            period_end=datetime.now(timezone.utc) - timedelta(hours=2),
            generated_at=datetime.now(timezone.utc),
            items_processed=10,
            breaking_count=1,
            high_count=3,
            currency_sections='{"USD": "USD is bearish", "XAU": "Gold surges"}',
            metadata_json='{"weighted_scores": {"USD": -4, "XAU": 6}, "theme_counts": {"RISK_OFF": 3}}',
            trigger="scheduled"
        )

        def mock_exec_side_effect(*args, **kwargs):
            m_res = MagicMock()
            q_str = str(args[0]).lower()
            if "news_digest_slices" in q_str:
                m_res.scalars().all.return_value = [slice1]
            elif "news_items" in q_str or "count" in q_str:
                m_res.scalar_one_or_none.return_value = 1
            else:
                m_res.scalar_one_or_none.return_value = None
                m_res.scalars().all.return_value = []
            return m_res

        mock_session.execute = AsyncMock(side_effect=mock_exec_side_effect)
        generator._macro_synth.generate = AsyncMock(return_value="Overall Macro Regime: RISK_OFF following rate cut and geopolitical escalation.")

        assembled = await generator.assemble_12h_digest(mock_session, hours_back=12)

        assert assembled is not None
        assert "```digest_metadata" in assembled
        assert "CURRENCY SIGNAL SUMMARY" in assembled
        assert "12-HOUR ROLLING TIMELINE" in assembled
        assert "Window #1:" in assembled
        assert "USD is bearish" in assembled
