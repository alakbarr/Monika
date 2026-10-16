"""Unit tests for ActiveCalendarPoller."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from tests.conftest import create_mock_async_session
from monika.application.scheduler.active_calendar_poller import ActiveCalendarPoller


class TestActiveCalendarPoller:
    @pytest.mark.asyncio
    async def test_generate_pseudo_news_suppresses_breaking_when_post_release_analyzer_active(self):
        """Verify pseudo-news gets impact='HIGH' and does not trigger news_watcher when post_release_analyzer is active."""
        poller = ActiveCalendarPoller(settings={})
        mock_nw = MagicMock()
        mock_nw.run_once = AsyncMock()
        poller._news_watcher = mock_nw
        poller._post_release_analyzer = MagicMock()

        mock_session = create_mock_async_session()
        added_items = []
        mock_session.add = MagicMock(side_effect=lambda item: added_items.append(item))

        events = [
            {"event_name": "US CPI YoY", "actual": "3.2%", "forecast": "3.0%", "previous": "2.9%", "currency": "USD"}
        ]

        await poller._generate_pseudo_news(mock_session, events)

        assert len(added_items) == 1
        news_item = added_items[0]
        assert news_item.impact == "HIGH"  # Not BREAKING
        assert "US CPI YoY" in news_item.title
        # NewsWatcher should NOT be triggered
        mock_nw.run_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_pseudo_news_fallback_when_post_release_analyzer_none(self):
        """Verify fallback behavior sets impact='BREAKING' and triggers news_watcher when post_release_analyzer is None."""
        poller = ActiveCalendarPoller(settings={})
        mock_nw = MagicMock()
        mock_nw.run_once = AsyncMock()
        poller._news_watcher = mock_nw
        poller._post_release_analyzer = None

        mock_session = create_mock_async_session()
        added_items = []
        mock_session.add = MagicMock(side_effect=lambda item: added_items.append(item))

        events = [
            {
                "event_name": "US Non-Farm Payrolls",
                "actual": "250K",
                "forecast": "180K",
                "previous": "150K",
                "currency": "USD",
            }
        ]

        await poller._generate_pseudo_news(mock_session, events)

        assert len(added_items) == 1
        news_item = added_items[0]
        assert news_item.impact == "BREAKING"
        # Wait a tiny moment for background task
        assert len(poller._background_tasks) >= 1 or mock_nw.run_once.called
