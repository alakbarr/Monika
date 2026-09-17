import pytest
from unittest.mock import MagicMock
from risk.position_sizing import PositionSizer, InstrumentSpec, DEFAULT_INSTRUMENTS

class TestPositionSizing:

    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "risk": {
                    "risk_percent_per_trade": 1.0,
                    "max_lot_size": 10.0,
                    "min_rr_ratio": 2.0,
                    "vix_risk_adjustment": True
                }
            }
        }

    def test_calculate_valid_buy(self, settings):
        sizer = PositionSizer(settings)
        # Entry 2000, SL 1990 -> 1000 pips (XAUUSD pip is 0.01)
        res = sizer.calculate(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0, # 20 distance -> RR 2.0
            account_equity=10000.0
        )
        assert res.is_valid
        assert res.risk_amount_usd == 100.0 # 1% of 10000
        assert res.sl_distance_price == 10.0
        assert res.sl_distance_pips == 1000.0
        # Lots = 100 / (1000 * 1.0) = 0.1
        assert res.recommended_lots == 0.1
        assert res.rr_ratio == 2.0

    def test_calculate_invalid_sell(self, settings):
        sizer = PositionSizer(settings)
        # Sell with SL below entry -> Invalid
        res = sizer.calculate(
            symbol="EURUSD",
            direction="sell",
            entry_price=1.1000,
            stop_loss=1.0900,
            take_profit=1.0800,
            account_equity=10000.0
        )
        assert not res.is_valid
        assert "stop_loss must be above entry_price" in res.rejection_reasons[0]

    def test_calculate_low_rr(self, settings):
        sizer = PositionSizer(settings)
        res = sizer.calculate(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2005.0, # distance 5 -> RR 0.5
            account_equity=10000.0
        )
        assert not res.is_valid
        assert any("R:R ratio" in r for r in res.rejection_reasons)



    def test_vix_adjustment(self, settings):
        sizer = PositionSizer(settings)
        # VIX 30 -> 0.25x risk -> 0.25% instead of 1.0%
        res = sizer.calculate(
            symbol="XAUUSD",
            direction="buy",
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
            account_equity=10000.0,
            vix_level=30.0
        )
        assert res.is_valid
        assert res.risk_percent == 0.25
        assert res.risk_amount_usd == 25.0
        assert res.recommended_lots == 0.02

    def test_mt5_live_spec(self, settings, monkeypatch):
        mock_mt5_client = MagicMock()
        sizer = PositionSizer(settings, mt5_client=mock_mt5_client)
        
        mock_mt5 = MagicMock()
        mock_info = MagicMock()
        mock_info.digits = 5
        mock_info.point = 0.00001
        mock_info.trade_tick_value = 1.0
        mock_info.trade_tick_size = 0.00001
        mock_info.trade_contract_size = 100000
        mock_info.volume_min = 0.01
        mock_info.volume_max = 100.0
        mock_info.volume_step = 0.01
        mock_info.trade_stops_level = 10
        mock_mt5.symbol_info.return_value = mock_info
        
        import sys
        sys.modules['MetaTrader5'] = mock_mt5
        
        res = sizer._get_instrument_spec("TESTEURUSD")
        assert res.symbol == "TESTEURUSD"
        assert res.pip_size == 0.0001  # 5-digit quote: point 0.00001 * 10 = 0.0001
        assert res.contract_size == 100000
        assert res._source == "mt5_live"

    def test_round_lots(self):
        assert PositionSizer._round_lots(0.123, 0.01) == 0.12
        assert PositionSizer._round_lots(0.129, 0.01) == 0.12
        assert PositionSizer._round_lots(1.555, 0.1) == 1.5
        assert PositionSizer._round_lots(-0.5, 0.01) == 0.0

    def test_notional_cap_clamping_valid(self, settings):
        sizer = PositionSizer(settings)
        # Very tight stop loss on EURUSD creates huge raw lots that exceed 20x notional cap
        # Equity: 1000, 1% risk = $10. SL: 1 pip (0.0001) -> Raw lots = 10 / (1 * 10) = 1.0 lot ($100k notional > $20k max notional)
        res = sizer.calculate(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1000,
            stop_loss=1.0999,
            take_profit=1.1020,
            account_equity=1000.0,
        )
        assert res.is_valid
        # Capped to 20x equity / (100000 * 1.1000) = 20000 / 110000 = 0.18 lots
        assert res.recommended_lots == 0.18
        assert len(res.rejection_reasons) == 0

    def test_decimal_precision_sl_distance_and_lots(self, settings):
        sizer = PositionSizer(settings)
        # 1.08555 - 1.08525 = 0.00030 exactly (3.0 pips) without binary float epsilon artifacts
        # Equity: 30000. Risk 1% = $300. raw_lots = 300 / (3.0 * $10) = 10.0 lots.
        # But max_lot_size is 10.0 in settings. Let's use risk 0.33% -> $99 / 30 = 3.30 lots.
        # Max notional: 30000 * 20 = 600,000 USD. Notional for 3.30 lots: 3.30 * 100000 * 1.08555 = 358,231 < 600,000.
        res = sizer.calculate(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.08555,
            stop_loss=1.08525,
            take_profit=1.09155,
            account_equity=30000.0,
            risk_percent_override=0.33,
        )
        assert res.is_valid
        assert res.sl_distance_price == 0.00030
        assert res.sl_distance_pips == 3.0
        assert res.recommended_lots == 3.30

    @pytest.mark.asyncio
    async def test_calculate_lot_size_resolves_live_mt5_equity(self, settings):
        from unittest.mock import AsyncMock, MagicMock
        from risk.position_sizing import calculate_lot_size

        mock_mt5 = MagicMock()
        mock_mt5.get_account_info = AsyncMock(return_value={"equity": 76849.91, "balance": 76849.91})
        mock_mt5.get_symbol_spec = AsyncMock(return_value={
            "volume_min": 0.01,
            "volume_step": 0.01,
            "trade_contract_size": 100.0,
            "trade_tick_value": 1.0,
            "digits": 2,
        })

        res = await calculate_lot_size(
            symbol="XAUUSD",
            entry_price=2600.0,
            stop_loss=2590.0,
            take_profit=2620.0,
            risk_pct=0.275,
            vix_level=12.0,
            settings=settings,
            mt5_client=mock_mt5,
        )
        assert res["is_valid"] is True
        # Risk amount based on live equity: 76849.91 * 0.275% = ~$211.34 (not $27.50 hardcoded fallback)
        assert res["risk_amount_usd"] > 200.0
        assert res["recommended_lots"] >= 0.01

    @pytest.mark.asyncio
    async def test_calculate_with_session_mt5_equity_resolution(self, settings):
        from unittest.mock import AsyncMock, MagicMock

        mock_mt5 = MagicMock()
        mock_mt5.get_account_info = AsyncMock(return_value={"equity": 50000.0, "balance": 50000.0})
        mock_mt5.get_symbol_spec = AsyncMock(return_value=None)

        sizer = PositionSizer(settings=settings, mt5_client=mock_mt5)
        res = await sizer.calculate_with_session(
            session=None,
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            vix_level=12.0,
        )
        assert res.is_valid is True
        # 1% of 50000 = $500 risk
        assert res.risk_amount_usd == 500.0



