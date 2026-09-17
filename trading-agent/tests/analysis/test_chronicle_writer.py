import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from analysis.memory.chronicle_writer import ChronicleWriter
from database.models import NewsItem, FundamentalBrief, MarketChronicle


class TestChronicleWriter:

    @pytest.mark.asyncio
    async def test_maybe_record_news_event_breaking(self):
        writer = ChronicleWriter({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Mock no existing chronicles in 7 days
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        news = NewsItem(
            id=101,
            title="President announces 50% tariffs on Canada auto imports",
            summary="Immediate executive order signed amid trade tensions.",
            currency_tags="USD,CAD",
            impact="BREAKING",
            fetched_at=datetime.now(timezone.utc)
        )

        entry = await writer.maybe_record_news_event(mock_session, news)

        assert entry is not None
        assert entry.category == "policy_change"
        assert entry.severity == "critical"
        assert "50% tariffs" in entry.headline
        assert entry.is_ongoing is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_record_regime_shift(self):
        writer = ChronicleWriter({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        prev_brief = FundamentalBrief(
            id=1,
            structured_json='{"macro_regime": "risk_on"}',
            risk_sentiment="bullish",
            confidence=0.8,
            generated_at=datetime.now(timezone.utc)
        )
        curr_brief = FundamentalBrief(
            id=2,
            structured_json='{"macro_regime": "risk_off"}',
            risk_sentiment="bearish",
            confidence=0.85,
            generated_at=datetime.now(timezone.utc)
        )

        entry = await writer.maybe_record_regime_shift(mock_session, curr_brief, prev_brief)

        assert entry is not None
        assert entry.category == "regime_shift"
        assert "RISK_ON -> RISK_OFF" in entry.headline
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chronicle_context(self):
        writer = ChronicleWriter({})
        mock_session = AsyncMock()

        chronicle = MarketChronicle(
            id=1,
            event_date=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
            category="policy_change",
            headline="US Threatens 50% Tariffs on Canada",
            narrative="Canada pledges retaliation.",
            currencies_affected="USD,CAD",
            severity="critical",
            is_ongoing=True
        )

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [chronicle]
        mock_session.execute = AsyncMock(return_value=mock_result)

        ctx = await writer.get_chronicle_context(mock_session, days_back=30)

        assert "PERSISTENT MARKET CHRONICLE" in ctx
        assert "US Threatens 50% Tariffs on Canada" in ctx
        assert "POLICY_CHANGE" in ctx
        assert "ONGOING" in ctx
