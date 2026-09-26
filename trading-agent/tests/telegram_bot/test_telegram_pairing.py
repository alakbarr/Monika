# ==============================================================================
# File: tests/telegram_bot/test_telegram_pairing.py
# ==============================================================================

"""
Unit tests for Paired DM Telegram Gateway Authorization (/pair).
Validates:
1. Stranger exclusion on normal commands while bypassing /pair.
2. In-band OTP generation and console challenge dispatch.
3. Verification of valid OTP and dynamic runtime authorization.
4. Rejection of invalid OTP attempts.
5. Idempotent check for already paired users.
"""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update, User, Message, Chat
from telegram.ext import ContextTypes

from telegram_bot.command_router import CommandRouter, CommandType
from telegram_bot.bot import TelegramBot
from gateway.pairing import PairingManager, get_pairing_manager, reset_pairing_manager


@pytest.fixture
def temp_pairing_mgr():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_file = os.path.join(tmpdir, "test_paired_users.json")
        mgr = PairingManager(store_path=store_file)
        with patch("gateway.pairing._GLOBAL_PAIRING_MANAGER", mgr):
            yield mgr
        reset_pairing_manager()


def make_mock_update(user_id: int, text: str, username: str = "testuser"):
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "Test"
    user.username = username
    update.effective_user = user

    chat = MagicMock(spec=Chat)
    chat.id = user_id
    chat.send_action = AsyncMock()

    msg = MagicMock(spec=Message)
    msg.text = text
    msg.chat = chat
    msg.reply_text = AsyncMock()
    update.message = msg
    return update


def test_command_router_blocks_stranger_on_normal_command(temp_pairing_mgr):
    router = CommandRouter(admin_chat_id=111, allowed_user_ids={111})
    update = make_mock_update(99999, "/status")
    parsed = router.parse(update)
    assert parsed is None


def test_command_router_allows_pair_command_for_stranger(temp_pairing_mgr):
    router = CommandRouter(admin_chat_id=111, allowed_user_ids={111})
    update = make_mock_update(99999, "/pair")
    parsed = router.parse(update)
    assert parsed is not None
    assert parsed.command == "pair"
    assert parsed.command_type == CommandType.DIRECT


@pytest.mark.asyncio
async def test_cmd_pair_lifecycle(temp_pairing_mgr):
    bot = TelegramBot(settings={})
    bot.admin_chat_id = 111
    bot.allowed_user_ids = {111}
    bot._router.admin_chat_id = 111
    bot._router.allowed_user_ids = {111}
    stranger_id = 88888
    username = "stranger_joe"

    # Step 1: User sends /pair without arguments
    update1 = make_mock_update(stranger_id, "/pair", username=username)
    ctx1 = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx1.args = []

    await bot._cmd_pair(update1, ctx1)

    update1.message.reply_text.assert_called_once()
    reply_text1 = update1.message.reply_text.call_args[0][0]
    assert "Pairing Authorization Required" in reply_text1

    # Check pending request in manager
    key = f"telegram:{stranger_id}"
    req = temp_pairing_mgr._pending_requests.get(key)
    assert req is not None

    # Step 2: Attempt with wrong code
    update2 = make_mock_update(stranger_id, "/pair WRONG-CODE", username=username)
    ctx2 = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx2.args = ["WRONG-CODE"]

    await bot._cmd_pair(update2, ctx2)
    reply_text2 = update2.message.reply_text.call_args[0][0]
    assert "Invalid pairing code" in reply_text2
    assert not temp_pairing_mgr.is_user_paired("telegram", str(stranger_id))

    # Step 3: Attempt with correct code (retrieve from in-memory challenge)
    # We reconstruct the raw code or extract it from generate_otp_code mock if needed,
    # but we can test verify_pairing_code directly with a fresh code
    user_msg, raw_code = temp_pairing_mgr.create_pairing_request("telegram", str(stranger_id), username=username)
    
    update3 = make_mock_update(stranger_id, f"/pair {raw_code}", username=username)
    ctx3 = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx3.args = [raw_code]

    await bot._cmd_pair(update3, ctx3)
    reply_text3 = update3.message.reply_text.call_args[0][0]
    assert "Pairing Berhasil" in reply_text3
    assert temp_pairing_mgr.is_user_paired("telegram", str(stranger_id))
    assert bot._router.is_authorized(stranger_id)

    # Step 4: Already paired user runs /pair again
    update4 = make_mock_update(stranger_id, "/pair", username=username)
    ctx4 = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx4.args = []

    await bot._cmd_pair(update4, ctx4)
    reply_text4 = update4.message.reply_text.call_args[0][0]
    assert "sudah terhubung" in reply_text4
