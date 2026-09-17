import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from scheduler.digest_slice_scheduler import DigestSliceScheduler
from database.models import NewsDigestSlice


class TestDigestSliceScheduler:

    @pytest.mark.asyncio
    async def test_run_once_trigger_scheduled(self):
        scheduler = DigestSliceScheduler({"news_classification": {"slice_schedule": {"interval_minutes": 120}}})
        mock_session = AsyncMock()

        # Mock no slice in last 30 min
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_slice = NewsDigestSlice(id=1, breaking_count=0, high_count=2, items_processed=5)
        scheduler.slice_generator.generate_slice = AsyncMock(return_value=mock_slice)

        res = await scheduler.run_once(mock_session, trigger="scheduled")

        assert res is not None
        assert res.id == 1
        scheduler.slice_generator.generate_slice.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_once_skips_if_recent_exists(self):
        scheduler = DigestSliceScheduler({})
        mock_session = AsyncMock()

        # Mock 1 slice in last 30 min
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        scheduler.slice_generator.generate_slice = AsyncMock()

        res = await scheduler.run_once(mock_session, trigger="scheduled")

        assert res is None
        scheduler.slice_generator.generate_slice.assert_not_called()
