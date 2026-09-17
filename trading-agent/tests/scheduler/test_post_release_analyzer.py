"""Unit tests for PostReleaseAnalyzer."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from scheduler.post_release_analyzer import PostReleaseAnalyzer, CURRENCY_TO_SYMBOLS


class TestCurrencyMapping:
    def test_usd_maps_all_pairs(self):
        assert len(CURRENCY_TO_SYMBOLS['USD']) == 8
        assert 'XAUUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'BTCUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'EURUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'GBPUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'USDJPY' in CURRENCY_TO_SYMBOLS['USD']
        assert 'AUDUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'XTIUSD' in CURRENCY_TO_SYMBOLS['USD']
        assert 'XBRUSD' in CURRENCY_TO_SYMBOLS['USD']

    def test_eur_maps_eurusd(self):
        assert CURRENCY_TO_SYMBOLS['EUR'] == ['EURUSD']

    def test_cad_maps_oil(self):
        assert 'XTIUSD' in CURRENCY_TO_SYMBOLS['CAD']
        assert 'XBRUSD' in CURRENCY_TO_SYMBOLS['CAD']

    def test_jpy_maps_usdjpy(self):
        assert CURRENCY_TO_SYMBOLS['JPY'] == ['USDJPY']


class TestPostReleaseAnalyzer:
    def setup_method(self):
        self.settings = {
            'trading': {
                'asset_universe': ['XAUUSD', 'EURUSD', 'GBPUSD',
                                   'USDJPY', 'AUDUSD', 'XTIUSD',
                                   'BTCUSD', 'XBRUSD']
            }
        }
        self.analyzer = PostReleaseAnalyzer(self.settings)

    def test_init_defaults(self):
        assert self.analyzer._poll_seconds == 120
        assert self.analyzer._settle_seconds == 900  # 15 min
        assert self.analyzer._max_reruns_per_day == 8
        assert len(self.analyzer._universe) == 8

    def test_event_handled_check(self):
        assert not self.analyzer.is_event_handled(123)
        self.analyzer._processed_events.add(123)
        assert self.analyzer.is_event_handled(123)

    def test_build_surprise_context_above_forecast(self):
        event = MagicMock()
        event.event_name = "Non-Farm Payrolls"
        event.actual = "228K"
        event.forecast = "180K"
        event.previous = "165K"
        context = self.analyzer._build_surprise_context([event])
        assert "POST-RELEASE ANALYSIS" in context
        assert "Non-Farm Payrolls" in context
        assert "Do NOT apply pre-event confidence penalty" in context

    def test_build_surprise_context_numeric_diff(self):
        event = MagicMock()
        event.event_name = "CPI YoY"
        event.actual = "3.8%"
        event.forecast = "3.1%"
        event.previous = "3.0%"
        context = self.analyzer._build_surprise_context([event])
        assert "ABOVE" in context
        assert "CPI YoY" in context

    @pytest.mark.asyncio
    async def test_stop(self):
        self.analyzer._running = True
        await self.analyzer.stop()
        assert not self.analyzer._running

    @pytest.mark.asyncio
    async def test_check_releases_no_events(self):
        from unittest.mock import AsyncMock, patch
        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_res
        
        with patch("database.db.get_session") as mock_get_sess:
            mock_get_sess.return_value.__aenter__.return_value = mock_session
            await self.analyzer._check_releases()

    @pytest.mark.asyncio
    async def test_check_releases_with_handled_events(self):
        from unittest.mock import AsyncMock, patch
        mock_event = MagicMock()
        mock_event.id = 999
        mock_event.currency = "USD"
        mock_event.event_name = "CPI"
        mock_event.actual = "3.2%"
        mock_event.forecast = "3.0%"
        mock_event.previous = "2.9%"
        mock_event.event_time = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_event]
        mock_session.execute.return_value = mock_res

        self.analyzer._settle_seconds = 0
        self.analyzer._run_targeted_reanalysis = AsyncMock()

        with patch("database.db.get_session") as mock_get_sess:
            mock_get_sess.return_value.__aenter__.return_value = mock_session
            await self.analyzer._check_releases()

        assert self.analyzer.is_event_handled(999)
        assert self.analyzer._run_targeted_reanalysis.called
