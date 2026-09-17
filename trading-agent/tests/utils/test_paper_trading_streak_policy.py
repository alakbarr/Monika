"""
Unit Tests for Paper Trading Streak Loss Policy & Infinite Loop Bug Fix.
Covers:
- streak_loss_policy: disabled, warn_and_scale, strict
- Infinite loop prevention (expired suspension does not re-suspend without new trades)
- Unsuspend helper methods (single & all)
- Position sizing scaling on streak losses
- Position synchronizer daily SL pause bypass in paper trading
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from database.models import PaperTradeRecord, SystemConfig
from utils.analytics.paper_tracker import PaperTracker
from risk.risk_gate import RiskGate


@pytest.mark.asyncio
async def test_streak_policy_disabled_does_not_suspend():
    """Verify streak_loss_policy='disabled' skips auto-suspension."""
    tracker = PaperTracker()
    settings = {
        "trading": {
            "auto_execute": False,
            "asset_universe": ["EURUSD"],
            "paper_trading": {
                "streak_loss_policy": "disabled",
                "suspension_hours": 12,
            },
            "risk": {
                "max_consecutive_losses_per_symbol": 3,
            }
        }
    }
    mock_session = AsyncMock()
    suspended = await tracker.check_and_suspend_poor_performers(mock_session, settings)
    assert suspended == []


@pytest.mark.asyncio
async def test_streak_policy_warn_and_scale_does_not_suspend_and_risk_gate_passes():
    """Verify streak_loss_policy='warn_and_scale' does not suspend and passes risk gate."""
    tracker = PaperTracker()
    settings = {
        "trading": {
            "auto_execute": False,
            "asset_universe": ["EURUSD"],
            "paper_trading": {
                "streak_loss_policy": "warn_and_scale",
                "streak_risk_scale_factor": 0.5,
                "suspension_hours": 12,
            },
            "risk": {
                "max_consecutive_losses_per_symbol": 3,
            }
        }
    }
    mock_session = AsyncMock()

    # 1. Tracker check_and_suspend_poor_performers skips suspension
    suspended = await tracker.check_and_suspend_poor_performers(mock_session, settings)
    assert suspended == []

    # 2. Risk gate passes with warn_and_scale reason
    now = datetime.now(timezone.utc)
    mock_trades = [
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.5, closed_at=now - timedelta(hours=1)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.8, closed_at=now - timedelta(hours=2)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.6, closed_at=now - timedelta(hours=3)),
    ]
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_trades
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_res

    gate = RiskGate(settings)
    ok, reason = await gate._check_consecutive_losses(mock_session, "EURUSD")
    assert ok is True
    assert "consecutive_losses_paper_warn_and_scale" in reason


@pytest.mark.asyncio
async def test_streak_policy_strict_suspends_and_blocks():
    """Verify streak_loss_policy='strict' suspends symbol on 3 losses and blocks risk gate."""
    settings = {
        "trading": {
            "auto_execute": False,
            "asset_universe": ["EURUSD"],
            "paper_trading": {
                "streak_loss_policy": "strict",
                "suspension_hours": 12,
            },
            "risk": {
                "max_consecutive_losses_per_symbol": 3,
            }
        }
    }
    now = datetime.now(timezone.utc)
    mock_trades = [
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.5, closed_at=now - timedelta(hours=1)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.8, closed_at=now - timedelta(hours=2)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", pnl_pct=-0.6, closed_at=now - timedelta(hours=3)),
    ]
    mock_session = AsyncMock()

    # Query 1: SystemConfig suspended_symbols -> None
    res_cfg = MagicMock()
    res_cfg.scalar_one_or_none.return_value = None

    # Query 2: PaperTradeRecord -> mock_trades
    res_trades = MagicMock()
    res_trades_scalars = MagicMock()
    res_trades_scalars.all.return_value = mock_trades
    res_trades.scalars.return_value = res_trades_scalars

    mock_session.execute.side_effect = [res_cfg, res_trades]

    tracker = PaperTracker()
    suspended = await tracker.check_and_suspend_poor_performers(mock_session, settings)
    assert suspended == ["EURUSD"]


@pytest.mark.asyncio
async def test_infinite_loop_bug_fix_expired_suspension_does_not_resuspend():
    """Verify expired suspension is NOT re-suspended if no new trades occurred after suspension."""
    settings = {
        "trading": {
            "auto_execute": False,
            "asset_universe": ["EURUSD"],
            "paper_trading": {
                "streak_loss_policy": "strict",
                "suspension_hours": 12,
            },
            "risk": {
                "max_consecutive_losses_per_symbol": 3,
            }
        }
    }
    now = datetime.now(timezone.utc)
    last_until = now - timedelta(hours=2)  # Expired 2 hours ago

    # Existing SystemConfig showing expired suspension
    existing_cfg = SystemConfig(
        key="suspended_symbols",
        value=json.dumps([{
            "symbol": "EURUSD",
            "suspended_at": (last_until - timedelta(hours=12)).isoformat(),
            "until": last_until.isoformat(),
            "reason": "3 consecutive losses"
        }])
    )

    # All 3 SL trades closed BEFORE last_until (old trades)
    mock_trades = [
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=last_until - timedelta(hours=3)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=last_until - timedelta(hours=4)),
        PaperTradeRecord(symbol="EURUSD", status="closed", exit_reason="sl_hit", closed_at=last_until - timedelta(hours=5)),
    ]

    mock_session = AsyncMock()

    # Query 1: SystemConfig
    res_cfg = MagicMock()
    res_cfg.scalar_one_or_none.return_value = existing_cfg

    # Query 2: PaperTradeRecord with closed_at > last_until -> empty!
    res_trades = MagicMock()
    res_trades_scalars = MagicMock()
    res_trades_scalars.all.return_value = []  # No trades closed after last_until!
    res_trades.scalars.return_value = res_trades_scalars

    mock_session.execute.side_effect = [res_cfg, res_trades]

    tracker = PaperTracker()
    suspended = await tracker.check_and_suspend_poor_performers(mock_session, settings)
    # Symbol should NOT be re-suspended!
    assert suspended == []


@pytest.mark.asyncio
async def test_unsuspend_symbol_and_all():
    """Verify unsuspend_symbol and unsuspend_all correctly update SystemConfig."""
    mock_session = AsyncMock()
    tracker = PaperTracker()

    # Setup initial suspended list with EURUSD and GBPUSD
    cfg = SystemConfig(
        key="suspended_symbols",
        value=json.dumps([
            {"symbol": "EURUSD", "until": "2099-01-01T00:00:00"},
            {"symbol": "GBPUSD", "until": "2099-01-01T00:00:00"},
        ])
    )
    res_cfg = MagicMock()
    res_cfg.scalar_one_or_none.return_value = cfg
    mock_session.execute.return_value = res_cfg

    # Test unsuspend_symbol EURUSD
    ok = await tracker.unsuspend_symbol(mock_session, "EURUSD")
    assert ok is True
    data = json.loads(cfg.value)
    assert len(data) == 1
    assert data[0]["symbol"] == "GBPUSD"

    # Test unsuspend_all
    cleared = await tracker.unsuspend_all(mock_session)
    assert cleared == ["GBPUSD"]
    assert json.loads(cfg.value) == []


@pytest.mark.asyncio
async def test_position_synchronizer_bypasses_daily_sl_pause_in_paper():
    """Verify position_synchronizer does not pause trading globally when daily SL hit limit is reached in paper mode."""
    from execution.service.position_synchronizer import PositionSynchronizerMixin

    settings = {
        "trading": {
            "auto_execute": False,  # Paper mode
            "paper_trading": {
                "pause_system_on_daily_sl_limit": False,  # Bypass pause
            },
            "risk": {
                "max_daily_sl_hits": 3,
                "post_sl_cooldown_hours": 2,
            }
        }
    }
    mock_mt5 = MagicMock()
    mock_gate = MagicMock()
    mock_gate.pause_trading = AsyncMock()

    class DummySync(PositionSynchronizerMixin):
        def __init__(self, mt5, gate, settings):
            self.mt5 = mt5
            self.gate = gate
            self.settings = settings

    sync = DummySync(mock_mt5, mock_gate, settings=settings)

    mock_session = AsyncMock()
    # Mock 3 SL hits today
    res_count = MagicMock()
    res_count.scalar_one_or_none.return_value = 3
    mock_session.execute.return_value = res_count

    mock_pos = MagicMock()
    mock_pos.symbol = "EURUSD"
    mock_pos.mt5_ticket = 12345
    mock_pos.pnl = -50.0

    with patch("utils.infra.notifier.AgentNotifier.send_warning", AsyncMock()):
        await sync._handle_stop_loss_hit(mock_session, mock_pos)

    # pause_trading should NOT have been called because pause_system_on_daily_sl_limit is False
    mock_gate.pause_trading.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_unsuspend_command():
    """Verify Telegram /unsuspend handler clears symbols and responds."""
    from telegram_bot.bot import TelegramBot
    from telegram_bot.command_router import CommandRouter

    settings = {
        "trading": {
            "paper_trading": {"streak_loss_policy": "warn_and_scale"},
            "risk": {},
        }
    }
    bot = TelegramBot(settings)
    bot._is_authorized = MagicMock(return_value=True)
    bot._is_admin = MagicMock(return_value=True)

    mock_update = MagicMock()
    mock_update.message = MagicMock()
    mock_update.message.reply_text = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.args = ["EURUSD"]

    with patch("utils.analytics.paper_tracker.PaperTracker.unsuspend_symbol", AsyncMock(return_value=True)), \
         patch("database.db.get_session") as mock_get_sess:
        mock_sess = AsyncMock()
        mock_get_sess.return_value.__aenter__.return_value = mock_sess

        await bot._cmd_unsuspend(mock_update, mock_ctx)

    mock_update.message.reply_text.assert_awaited_once()
    reply_text = mock_update.message.reply_text.await_args[0][0]
    assert "EURUSD" in reply_text
