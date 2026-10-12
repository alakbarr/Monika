# ==============================================================================
# File: tests/risk/test_flash_crash_risk_gate.py
# ==============================================================================

import pytest
from datetime import datetime, timezone, timedelta

from risk.risk_gate import RiskGate
from risk.position_sizing import SizingResult
from scheduler.flash_crash_detector import FlashCrashDetector


@pytest.mark.asyncio
async def test_risk_gate_blocks_flash_crash_symbol(db_session):
    """Memastikan Risk Gate menolak order jika simbol diblokir oleh FlashCrashDetector."""
    settings = {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
                "flash_crash": {"enabled": True},
            }
        }
    }

    detector = FlashCrashDetector(settings)
    # Set XAUUSD into blocked cooldown
    detector._blocked_symbols["XAUUSD"] = datetime.now(timezone.utc) + timedelta(minutes=25)

    risk_gate = RiskGate(settings, flash_crash_detector=detector)

    sizing = SizingResult(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=10.0,
        sl_distance_pips=100.0,
        pip_value_per_lot=1.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
    )

    verdict = await risk_gate.evaluate(
        session=db_session,
        symbol="XAUUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
    )

    assert verdict.approved is False
    assert "flash_crash_cooldown" in verdict.checks_failed
