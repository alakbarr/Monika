import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from utils.validation.data_validator import validate_data_freshness, check_data_coherence, is_crypto_symbol, is_forex_market_closed
from datetime import datetime, timezone, timedelta

class TestDataValidator:
    @pytest.mark.asyncio
    async def test_validate_fresh_h4_within_8h(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        now = datetime(2026, 8, 25, 0, 0, 43, tzinfo=timezone.utc)  # Tuesday
        
        with patch("utils.clock.now", return_value=now):
            # OHLCV 5.0h old (from 19:00 previous day)
            # 1st call = OHLCV, 2nd call = Indicator, 3rd call = News
            def side_effect(*args, **kwargs):
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = now - timedelta(hours=5.0)
                return mock_result
                
            mock_session.execute.side_effect = side_effect
            
            res = await validate_data_freshness(mock_session, ["XAUUSD"], ["H4"])
            assert res["ready"] is True
            assert len(res["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_stale_h4_over_8h(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        now = datetime(2026, 8, 25, 0, 0, 43, tzinfo=timezone.utc)  # Tuesday
        
        with patch("utils.clock.now", return_value=now):
            def side_effect(*args, **kwargs):
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = now - timedelta(hours=10)  # > 8.0h
                return mock_result
                
            mock_session.execute.side_effect = side_effect
            
            res = await validate_data_freshness(mock_session, ["EURUSD"], ["H4"])
            assert res["ready"] is False
            assert len(res["errors"]) > 0
            assert any("stale" in e for e in res["errors"])

    @pytest.mark.asyncio
    async def test_validate_weekend_forex_vs_crypto(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        # Saturday noon UTC
        weekend_now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        
        with patch("utils.clock.now", return_value=weekend_now):
            # Friday close data (16 hours old on Saturday noon)
            def side_effect(*args, **kwargs):
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = weekend_now - timedelta(hours=16)
                return mock_result
                
            mock_session.execute.side_effect = side_effect
            
            # Forex on weekend: expected/valid (not an error)
            res_forex = await validate_data_freshness(mock_session, ["EURUSD"], ["H4"])
            assert res_forex["ready"] is True
            assert len(res_forex["errors"]) == 0
            
            # Crypto on weekend: 16h is stale because crypto trades 24/7
            res_crypto = await validate_data_freshness(mock_session, ["BTCUSD"], ["H4"])
            assert res_crypto["ready"] is False
            assert len(res_crypto["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_missing(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        now = datetime(2026, 8, 25, 0, 0, 43, tzinfo=timezone.utc)
        
        with patch("utils.clock.now", return_value=now):
            def side_effect(*args, **kwargs):
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                return mock_result
                
            mock_session.execute.side_effect = side_effect
            
            res = await validate_data_freshness(mock_session, ["BTCUSD"], ["H1"])
            assert res["ready"] is False
            assert len(res["errors"]) == 3  # OHLCV, Indicator, News missing

    def test_crypto_symbol_helper(self):
        assert is_crypto_symbol("BTCUSD") is True
        assert is_crypto_symbol("ETHUSD") is True
        assert is_crypto_symbol("EURUSD") is False
        assert is_crypto_symbol("XAUUSD") is False

    def test_forex_market_closed_helper(self):
        # Saturday = closed
        assert is_forex_market_closed(datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)) is True
        # Tuesday = open
        assert is_forex_market_closed(datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)) is False

    @pytest.mark.asyncio
    async def test_check_data_coherence_d1_fresh_at_18_5h(self):
        mock_session = AsyncMock()
        now = datetime(2026, 8, 25, 18, 30, 0, tzinfo=timezone.utc)  # Tuesday evening
        
        # H4 OHLCV (2h old), H4 Ind (2h old), D1 OHLCV (18.5h old), D1 Ind (18.5h old)
        timestamps = [
            now - timedelta(hours=2.0),   # H4 OHLCV
            now - timedelta(hours=2.0),   # H4 Ind
            now - timedelta(hours=18.5),  # D1 OHLCV (18.5h old -> valid under 32h limit!)
            now - timedelta(hours=18.5),  # D1 Ind
        ]
        
        def side_effect(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = timestamps.pop(0) if timestamps else None
            return mock_result
            
        mock_session.execute.side_effect = side_effect
        
        with patch("utils.clock.now", return_value=now):
            res = await check_data_coherence(mock_session, "XBRUSD")
            assert res["coherent"] is True
            assert len(res["issues"]) == 0

    @pytest.mark.asyncio
    async def test_check_data_coherence_d1_stale_over_32h(self):
        mock_session = AsyncMock()
        now = datetime(2026, 8, 25, 18, 30, 0, tzinfo=timezone.utc)
        
        # H4 fresh (2h), D1 stale (35h > 32h)
        timestamps = [
            now - timedelta(hours=2.0),   # H4 OHLCV
            now - timedelta(hours=2.0),   # H4 Ind
            now - timedelta(hours=35.0),  # D1 OHLCV (stale!)
            now - timedelta(hours=35.0),  # D1 Ind
        ]
        
        def side_effect(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = timestamps.pop(0) if timestamps else None
            return mock_result
            
        mock_session.execute.side_effect = side_effect
        
        with patch("utils.clock.now", return_value=now):
            res = await check_data_coherence(mock_session, "XBRUSD")
            assert res["coherent"] is False
            assert any("D1: OHLCV is 35.0h old" in i for i in res["issues"])

    @pytest.mark.asyncio
    async def test_check_data_coherence_indicator_desync(self):
        mock_session = AsyncMock()
        now = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
        
        # H4 OHLCV (1h old), H4 Ind (4h old -> 3h diff > 1h desync)
        timestamps = [
            now - timedelta(hours=1.0),   # H4 OHLCV
            now - timedelta(hours=4.0),   # H4 Ind (desync!)
            now - timedelta(hours=12.0),  # D1 OHLCV
            now - timedelta(hours=12.0),  # D1 Ind
        ]
        
        def side_effect(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = timestamps.pop(0) if timestamps else None
            return mock_result
            
        mock_session.execute.side_effect = side_effect
        
        with patch("utils.clock.now", return_value=now):
            res = await check_data_coherence(mock_session, "EURUSD")
            assert res["coherent"] is False
            assert any("differs from OHLCV" in i for i in res["issues"])

    @pytest.mark.asyncio
    async def test_validate_macro_freshness_monday_morning_and_afternoon(self):
        """Verify Friday close macro data (VIX, DXY, Yields) is valid on Monday morning & afternoon."""
        mock_session = AsyncMock()
        # Monday 07:00 WIB (00:00 UTC) -> Friday midnight UTC is 3.0 days old
        monday_morning = datetime(2026, 8, 31, 0, 3, 52, tzinfo=timezone.utc)
        friday_dt = datetime(2026, 8, 28, 0, 0, 0, tzinfo=timezone.utc)
        
        # 1: OHLCV, 2: Ind, 3: News, 4: Calendar, 5: VIX, 6: Yield, 7: DXY, 8: COT, 9: FedWatch
        execute_side_effects = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(hours=1))),  # OHLCV
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(hours=1))),  # Ind
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(hours=1))),  # News
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(hours=2))),  # Calendar
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                             # VIX (3.0d old)
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                             # Yield (3.0d old)
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                             # DXY (3.0d old)
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(days=3))),   # COT
            MagicMock(scalar_one_or_none=MagicMock(return_value=monday_morning - timedelta(days=1))),   # FedWatch
        ]
        mock_session.execute.side_effect = execute_side_effects

        with patch("utils.clock.now", return_value=monday_morning):
            res = await validate_data_freshness(mock_session, ["EURUSD"], ["H1"])
            assert res["ready"] is True
            assert len(res["warnings"]) == 0
            assert len(res["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_macro_freshness_wednesday_stale_detection(self):
        """Verify Friday close macro data is flagged as stale on Wednesday (> 4.5 days old)."""
        mock_session = AsyncMock()
        wednesday = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
        friday_dt = datetime(2026, 8, 28, 0, 0, 0, tzinfo=timezone.utc)  # 5.5 days old
        
        execute_side_effects = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(hours=1))),  # OHLCV
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(hours=1))),  # Ind
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(hours=1))),  # News
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(hours=2))),  # Calendar
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                       # Stale VIX
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                       # Stale Yield
            MagicMock(scalar_one_or_none=MagicMock(return_value=friday_dt)),                       # Stale DXY
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(days=3))),   # COT
            MagicMock(scalar_one_or_none=MagicMock(return_value=wednesday - timedelta(days=1))),   # FedWatch
        ]
        mock_session.execute.side_effect = execute_side_effects

        with patch("utils.clock.now", return_value=wednesday):
            res = await validate_data_freshness(mock_session, ["EURUSD"], ["H1"])
            warnings_str = " ".join(res["warnings"])
            assert "VIX data is 5.5 days old (stale)" in warnings_str
            assert "Treasury yield data is 5.5 days old (stale)" in warnings_str
            assert "DXY data is 5.5 days old (stale)" in warnings_str


