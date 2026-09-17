# ==============================================================================
# File: tests/scheduler/test_flash_crash_detector.py
# ==============================================================================

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from database.models import PriceOHLCV, TechnicalIndicator, Position, SystemConfig
from scheduler.flash_crash_detector import FlashCrashDetector


@pytest.mark.asyncio
async def test_flash_crash_detection_and_blocking(db_session):
    """Memastikan deteksi lonjakan harga memenuhi dual-threshold memblokir simbol dan memperketat SL."""
    now = datetime.now(timezone.utc)
    settings = {
        "trading": {
            "asset_universe": ["XAUUSD"],
            "risk": {
                "flash_crash": {
                    "enabled": True,
                    "default_atr_multiplier": 3.0,
                    "default_min_pct_move": 1.5,
                    "lookback_minutes": 15,
                    "cooldown_minutes": 30,
                    "symbol_rules": {
                        "XAUUSD": {"atr_multiplier": 3.0, "min_pct_move": 1.5}
                    }
                }
            }
        }
    }

    # 1. Insert ATR H1 = 10.0
    atr_ind = TechnicalIndicator(
        symbol="XAUUSD",
        timeframe="H1",
        indicator_name="ATR_14",
        value_json=json.dumps({"atr": 10.0}),
        timestamp=now - timedelta(minutes=5),
    )
    db_session.add(atr_ind)

    # 2. Insert M15 spike candle (Range = 35.0 > 3.0 * 10.0, Move % = 35/2030 = 1.72% > 1.5%)
    db_session.add(PriceOHLCV(
        symbol="XAUUSD",
        timeframe="M15",
        timestamp=now - timedelta(minutes=5),
        open=2000.0,
        high=2035.0,
        low=2000.0,
        close=2030.0,
        volume=5000,
    ))

    # 3. Insert open buy position
    pos = Position(
        symbol="XAUUSD",
        direction="buy",
        status="open",
        entry_price=2005.0,
        sl=1990.0,
        tp=2050.0,
        volume=0.1,
        mt5_ticket=12345,
    )
    db_session.add(pos)
    await db_session.commit()

    mock_exec = MagicMock()
    mock_exec.modify_position_sl_tp = AsyncMock(return_value={"success": True})
    # Live-quote guard (added in R4) needs an awaitable in-profit quote for BUY
    mock_exec.get_current_price = AsyncMock(return_value=2020.0)
    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()

    detector = FlashCrashDetector(settings, execution_service=mock_exec, notifier=mock_notifier)
    assert detector.is_symbol_blocked("XAUUSD") is False

    alerts = await detector.check(db_session)

    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "XAUUSD"
    assert alerts[0]["range_move"] == 35.0
    assert alerts[0]["multiplier"] == 3.5
    assert detector.is_symbol_blocked("XAUUSD") is True

    # Verifikasi SL diperketat ke breakeven (2005.0) dengan signature tepat
    mock_exec.modify_position_sl_tp.assert_called_once_with(
        ticket=12345, sl=2005.0, tp=2050.0, requested_by="flash_crash_detector"
    )
    mock_notifier.send.assert_called_once()


@pytest.mark.asyncio
async def test_false_positive_prevention_on_normal_crypto_volatility(db_session):
    """Memastikan fluktuasi normal kripto (1% move, 3.1x compressed ATR) TIDAK memicu false positive."""
    now = datetime.now(timezone.utc)
    settings = {
        "trading": {
            "asset_universe": ["BTCUSD"],
            "risk": {
                "flash_crash": {
                    "enabled": True,
                    "lookback_minutes": 15,
                    "symbol_rules": {
                        "BTCUSD": {"atr_multiplier": 6.0, "min_pct_move": 4.0}
                    }
                }
            }
        }
    }

    # Weekend compressed ATR = $250.0
    db_session.add(TechnicalIndicator(
        symbol="BTCUSD",
        timeframe="H1",
        indicator_name="ATR_14",
        value_json=json.dumps({"atr": 250.0}),
        timestamp=now - timedelta(minutes=5),
    ))

    # Move = $779.10 on $78,000 BTC (3.1x ATR, tapi hanya 0.99% move)
    db_session.add(PriceOHLCV(
        symbol="BTCUSD",
        timeframe="M15",
        timestamp=now - timedelta(minutes=5),
        open=78000.0,
        high=78779.1,
        low=78000.0,
        close=78750.0,
        volume=1000,
    ))
    await db_session.commit()

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()

    detector = FlashCrashDetector(settings, notifier=mock_notifier)
    alerts = await detector.check(db_session)

    # Harus diabaikan (TIDAK ADA ALERT & TIDAK DIBLOKIR)
    assert len(alerts) == 0
    assert detector.is_symbol_blocked("BTCUSD") is False
    mock_notifier.send.assert_not_called()


@pytest.mark.asyncio
async def test_true_flash_crash_on_crypto_triggers_circuit_breaker(db_session):
    """Memastikan true flash crash di kripto (> 6x ATR & > 4.0% move) terdeteksi dan memicu proteksi."""
    now = datetime.now(timezone.utc)
    settings = {
        "trading": {
            "asset_universe": ["BTCUSD"],
            "risk": {
                "flash_crash": {
                    "enabled": True,
                    "cooldown_minutes": 30,
                    "symbol_rules": {
                        "BTCUSD": {"atr_multiplier": 6.0, "min_pct_move": 4.0}
                    }
                }
            }
        }
    }

    db_session.add(TechnicalIndicator(
        symbol="BTCUSD",
        timeframe="H1",
        indicator_name="ATR_14",
        value_json=json.dumps({"atr": 400.0}),
        timestamp=now - timedelta(minutes=5),
    ))

    # Extreme crash move: $4,000 drop in 15m (10x ATR & 5.1% drop)
    db_session.add(PriceOHLCV(
        symbol="BTCUSD",
        timeframe="M15",
        timestamp=now - timedelta(minutes=5),
        open=78000.0,
        high=78000.0,
        low=74000.0,
        close=74100.0,
        volume=8000,
    ))
    await db_session.commit()

    mock_notifier = MagicMock()
    mock_notifier.send = AsyncMock()

    detector = FlashCrashDetector(settings, notifier=mock_notifier)
    alerts = await detector.check(db_session)

    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "BTCUSD"
    assert alerts[0]["range_move"] == 4000.0
    assert alerts[0]["multiplier"] == 10.0
    assert alerts[0]["move_pct"] >= 5.0
    assert detector.is_symbol_blocked("BTCUSD") is True
    mock_notifier.send.assert_called_once()


@pytest.mark.asyncio
async def test_load_persisted_blocks_on_startup(db_session):
    """Memastikan status karantina yang tersimpan di SystemConfig dimuat kembali saat startup."""
    now = datetime.now(timezone.utc)
    blocked_until = now + timedelta(minutes=25)
    
    db_session.add(SystemConfig(
        key="flash_crash_blocked_EURUSD",
        value=blocked_until.isoformat(),
    ))
    await db_session.commit()

    detector = FlashCrashDetector({"trading": {"risk": {"flash_crash": {"enabled": True}}}})
    assert detector.is_symbol_blocked("EURUSD") is False

    await detector.load_persisted_blocks(db_session)
    assert detector.is_symbol_blocked("EURUSD") is True


@pytest.mark.asyncio
async def test_protect_open_positions_tightens_sl_for_profit_buy(db_session):
    """Regression (Round 5 H-1): `entry` tidak terdefinisi membuat proteksi SL breakeven mati total."""
    now = datetime.now(timezone.utc)
    db_session.add(Position(
        symbol="XAUUSD", direction="buy", status="open",
        entry_price=2005.0, sl=1990.0, tp=2050.0, volume=0.1, mt5_ticket=111,
    ))
    await db_session.commit()

    mock_exec = MagicMock()
    mock_exec.modify_position_sl_tp = AsyncMock(return_value={"success": True})
    mock_exec.get_current_price = AsyncMock(return_value=2020.0)  # > entry -> in profit

    detector = FlashCrashDetector({"trading": {"risk": {"flash_crash": {"enabled": True}}}}, execution_service=mock_exec)
    await detector._protect_open_positions(db_session, "XAUUSD", now)

    mock_exec.modify_position_sl_tp.assert_called_once_with(
        ticket=111, sl=2005.0, tp=2050.0, requested_by="flash_crash_detector"
    )


@pytest.mark.asyncio
async def test_protect_open_positions_skips_losing_buy(db_session):
    """BUY losing (current < entry) tidak boleh diperketat ke breakeven."""
    now = datetime.now(timezone.utc)
    db_session.add(Position(
        symbol="XAUUSD", direction="buy", status="open",
        entry_price=2005.0, sl=1990.0, tp=2050.0, volume=0.1, mt5_ticket=222,
    ))
    await db_session.commit()

    mock_exec = MagicMock()
    mock_exec.modify_position_sl_tp = AsyncMock(return_value={"success": True})
    mock_exec.get_current_price = AsyncMock(return_value=1990.0)  # < entry -> losing

    detector = FlashCrashDetector({"trading": {"risk": {"flash_crash": {"enabled": True}}}}, execution_service=mock_exec)
    await detector._protect_open_positions(db_session, "XAUUSD", now)

    mock_exec.modify_position_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_protect_open_positions_skips_position_without_ticket(db_session):
    """Posisi tanpa mt5_ticket dilewati tanpa error."""
    now = datetime.now(timezone.utc)
    db_session.add(Position(
        symbol="XAUUSD", direction="buy", status="open",
        entry_price=2005.0, sl=1990.0, tp=2050.0, volume=0.1, mt5_ticket=None,
    ))
    await db_session.commit()

    mock_exec = MagicMock()
    mock_exec.modify_position_sl_tp = AsyncMock(return_value={"success": True})
    mock_exec.get_current_price = AsyncMock(return_value=2020.0)

    detector = FlashCrashDetector({"trading": {"risk": {"flash_crash": {"enabled": True}}}}, execution_service=mock_exec)
    await detector._protect_open_positions(db_session, "XAUUSD", now)

    mock_exec.modify_position_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_protect_open_positions_sells_tighten_above_entry(db_session):
    """SELL in-profit (current < entry) -> SL diperketat ke entry."""
    now = datetime.now(timezone.utc)
    db_session.add(Position(
        symbol="XAUUSD", direction="sell", status="open",
        entry_price=2005.0, sl=2020.0, tp=1990.0, volume=0.1, mt5_ticket=333,
    ))
    await db_session.commit()

    mock_exec = MagicMock()
    mock_exec.modify_position_sl_tp = AsyncMock(return_value={"success": True})
    mock_exec.get_current_price = AsyncMock(return_value=2000.0)  # < entry -> profit

    detector = FlashCrashDetector({"trading": {"risk": {"flash_crash": {"enabled": True}}}}, execution_service=mock_exec)
    await detector._protect_open_positions(db_session, "XAUUSD", now)

    mock_exec.modify_position_sl_tp.assert_called_once_with(
        ticket=333, sl=2005.0, tp=1990.0, requested_by="flash_crash_detector"
    )
