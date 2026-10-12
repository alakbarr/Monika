"""
Test suite for TurnMarkerManager, FuzzyCommandRouter, and TradeConfirmManager.
"""

import time
import pytest
from pathlib import Path
from utils.turn_marker import TurnMarker, TurnMarkerManager
from telegram_bot.fuzzy_router import FuzzyCommandRouter, TRADING_COMMAND_REGISTRY
from execution.service.trade_confirm import TradeConfirmManager, PendingTradeAction


def test_turn_marker_lifecycle(tmp_path):
    manager = TurnMarkerManager(marker_dir=tmp_path)
    marker = TurnMarker(
        session_id="sess_123",
        task_type="adhoc_analysis",
        symbol="XAUUSD",
        stage="stage2_debate",
        started_at=time.time()
    )

    manager.record_start(marker)
    interrupted = manager.check_interrupted(max_age_seconds=60.0)
    assert interrupted is not None
    assert interrupted.session_id == "sess_123"
    assert interrupted.symbol == "XAUUSD"

    manager.clear()
    assert manager.check_interrupted() is None


def test_turn_marker_stale_discard(tmp_path):
    manager = TurnMarkerManager(marker_dir=tmp_path)
    marker = TurnMarker(
        session_id="old_sess",
        task_type="recurring_cycle",
        symbol=None,
        stage="init",
        started_at=time.time() - 1000.0  # Old
    )
    manager.record_start(marker)
    # With max_age 100s, this should be discarded
    assert manager.check_interrupted(max_age_seconds=100.0) is None


def test_fuzzy_router_matching():
    router = FuzzyCommandRouter()

    # Tier 0: Exact
    cmd_def, sugg = router.resolve("status")
    assert cmd_def is not None
    assert cmd_def.command == "status"

    # Tier 0: Alias
    cmd_def, sugg = router.resolve("posisi")
    assert cmd_def is not None
    assert cmd_def.command == "positions"

    # Tier 1: Typo distance
    cmd_def, sugg = router.resolve("risks")
    # 'risks' is very close to 'risk' (cutoff >= 0.8)
    assert cmd_def is not None
    assert cmd_def.command == "risk"

    # Suggestions or match for further typo
    cmd_def, sugg = router.resolve("posisiku")
    assert cmd_def is not None or len(sugg) > 0


@pytest.mark.asyncio
async def test_trade_confirm_pop_before_execute():
    manager = TradeConfirmManager()
    action = manager.create_pending_action(
        action_type="close_position",
        description="Close position 123456",
        payload={"ticket": 123456},
        ttl_seconds=10.0
    )
    confirm_id = action.confirm_id

    executed_payloads = []
    async def _mock_handler(payload):
        executed_payloads.append(payload)
        return "SUCCESS"

    # First execution should succeed
    success, msg, res = await manager.execute_confirmed_action(confirm_id, _mock_handler)
    assert success is True
    assert res == "SUCCESS"
    assert len(executed_payloads) == 1

    # Second execution of SAME confirm_id must fail (pop-before-execute guarantee)
    success2, msg2, res2 = await manager.execute_confirmed_action(confirm_id, _mock_handler)
    assert success2 is False
    assert "tidak ditemukan" in msg2
    assert len(executed_payloads) == 1
