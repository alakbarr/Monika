# ==============================================================================
# File: tests/gateway/test_phase7_omnichannel_and_hitl.py
# ==============================================================================

import asyncio
import os
import tempfile
import time
import pytest

from gateway.delivery_ledger import DeliveryLedger, DeliveryStatus
from gateway.turn_lease import TurnLeaseManager
from gateway.bot_loop_guard import BotLoopGuard
from gateway.stream_consumer import LiveStreamConsumer, scrub_thinking_tags, ensure_closed_code_fences
from risk.approval_hub import ApprovalHub, ApprovalStatus


def test_delivery_ledger_idempotency_and_deduplication():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ledger.db")
        ledger = DeliveryLedger(db_path=db_path)

        key = ledger.generate_idempotency_key("telegram", "chat_12345", "Trade EURUSD BUY 0.10")
        assert len(key) == 64

        # Register intent 1: Must be new
        is_new, rec = ledger.register_intent(key, "telegram", "chat_12345", {"action": "trade"})
        assert is_new is True
        assert rec.status == DeliveryStatus.PENDING

        # Mark delivered
        ledger.mark_delivered(key)

        # Register intent 2 with same key: Must detect existing DELIVERED and reject duplicate
        is_new_again, existing_rec = ledger.register_intent(key, "telegram", "chat_12345", {"action": "trade"})
        assert is_new_again is False
        assert existing_rec.status == DeliveryStatus.DELIVERED


@pytest.mark.asyncio
async def test_turn_lease_concurrency_fencing():
    mgr = TurnLeaseManager(default_ttl=5.0)
    conv_id = "chat_convo_999"

    # Holder A acquires lease
    acquired = await mgr.acquire_lease(conv_id, holder_id="turn_A")
    assert acquired is True
    assert await mgr.is_lease_active(conv_id) is True

    # Holder B attempts to acquire during A's lease -> Rejected
    acquired_b = await mgr.acquire_lease(conv_id, holder_id="turn_B")
    assert acquired_b is False

    # Holder A renews lease
    renewed = await mgr.renew_lease(conv_id, holder_id="turn_A", extension_seconds=10.0)
    assert renewed is True

    # Holder A releases lease
    released = await mgr.release_lease(conv_id, holder_id="turn_A")
    assert released is True

    # Now Holder B can acquire
    acquired_b_retry = await mgr.acquire_lease(conv_id, holder_id="turn_B")
    assert acquired_b_retry is True
    await mgr.release_lease(conv_id, holder_id="turn_B")


def test_bot_loop_guard():
    guard = BotLoopGuard(window_seconds=3.0, max_messages=4)

    # 1. Normal distinct messages pass
    ok1, _ = guard.check_and_record("telegram", "chat_1", "user_1", "What is the market trend?")
    assert ok1 is True

    ok2, _ = guard.check_and_record("telegram", "chat_1", "user_1", "Show me current open positions.")
    assert ok2 is True

    # 2. Identical rapid repeated messages are blocked
    ok_rep1, _ = guard.check_and_record("telegram", "chat_1", "bot_2", "Ping heartbeat")
    assert ok_rep1 is True

    ok_rep2, _ = guard.check_and_record("telegram", "chat_1", "bot_2", "Ping heartbeat")
    assert ok_rep2 is True

    ok_rep3, reason = guard.check_and_record("telegram", "chat_1", "bot_2", "Ping heartbeat")
    assert ok_rep3 is False
    assert "Bot loop detected" in reason

    # 3. Echo headers blocked
    ok_echo, echo_reason = guard.check_and_record("slack", "chan_general", "bot_x", "Hello [monika_echo] response")
    assert ok_echo is False
    assert "echo header" in echo_reason.lower()


@pytest.mark.asyncio
async def test_approval_hub_workflow():
    hub = ApprovalHub(default_ttl=10.0)

    # Level 1: Auto-approved
    req_l1 = hub.request_approval(
        action_type="OPEN_TRADE_STANDARD",
        level=1,
        description="Standard EURUSD BUY 0.05",
        details={"symbol": "EURUSD", "lots": 0.05},
    )
    assert req_l1.status == ApprovalStatus.APPROVED

    # Level 2: Requires HITL confirmation
    req_l2 = hub.request_approval(
        action_type="EXECUTE_TERMINAL_CMD",
        level=2,
        description="Execute database cleanup script",
        details={"command": "python scripts/db_vacuum.py"},
    )
    assert req_l2.status == ApprovalStatus.PENDING

    # Test Markdown formatting and Telegram inline buttons
    card_md = hub.format_card_markdown(req_l2.token)
    assert "HITL GATE" in card_md
    assert req_l2.token in card_md

    keyboard = hub.format_telegram_inline_keyboard(req_l2.token)
    assert len(keyboard) == 1
    assert keyboard[0][0]["callback_data"] == f"appr_yes:{req_l2.token}"

    # Asynchronously await decision and approve in background
    async def approve_delayed():
        await asyncio.sleep(0.05)
        hub.decide(req_l2.token, approved=True, user_id="admin_user_01", reason="Manually verified.")

    asyncio.create_task(approve_delayed())
    approved, msg = await hub.await_decision(req_l2.token)
    assert approved is True
    assert "Manually verified" in msg
    assert req_l2.decided_by == "admin_user_01"


def test_stream_consumer_think_scrubbing_and_fence_balancing():
    raw_response = "<think>Analyzing market fundamentals and SMA cross...</think>Current EURUSD price is 1.0850 with bullish momentum."
    cleaned, thoughts = scrub_thinking_tags(raw_response)

    assert "<think>" not in cleaned
    assert "Analyzing market fundamentals" in thoughts
    assert cleaned == "Current EURUSD price is 1.0850 with bullish momentum."

    # Test code fence balancing
    unclosed_code = "Here is the calculation:\n```python\nx = 10\ny = 20"
    balanced = ensure_closed_code_fences(unclosed_code)
    assert balanced.endswith("\n```")
