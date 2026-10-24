# ==============================================================================
# File: tests/test_phase19_remediation.py
# Description: Regression & Unit Tests for Phase 19 Security, Safety & Architecture Fixes
# ==============================================================================

from collections import deque
import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.interfaces.telegram.voice_safety_gate import VoiceSafetyGate
from monika.interfaces.gateway.webhook_ingress import normalize_tradingview_payload
from monika.interfaces.gateway.acp_server import AcpServer
from monika.interfaces.gateway.platforms.discord_adapter import DiscordPlatformAdapter
from monika.interfaces.gateway.platforms.telegram_adapter import TelegramPlatformAdapter
from monika.interfaces.gateway.platforms.slack_adapter import SlackPlatformAdapter
from monika.interfaces.gateway.platforms.webhook_adapter import WebhookPlatformAdapter


def test_voice_safety_gate_strict_fail_closed():
    """Verify VoiceSafetyGate fails closed when volume lot is missing in strict mode."""
    # When strict=True, missing volume MUST produce error and lots=None
    proposal = VoiceSafetyGate.extract_trade_intent("beli XAUUSD", strict=True)
    assert proposal.is_trade_command is True
    assert proposal.symbol == "XAUUSD"
    assert proposal.action == "BUY"
    assert proposal.lots is None
    assert proposal.error is not None
    assert "Volume lot tidak terdeteksi" in proposal.error

    # When strict=True, valid lot is parsed correctly
    valid_prop = VoiceSafetyGate.extract_trade_intent("beli XAUUSD 0.05 lot", strict=True)
    assert valid_prop.is_trade_command is True
    assert valid_prop.symbol == "XAUUSD"
    assert valid_prop.lots == 0.05
    assert valid_prop.error is None


def test_tradingview_webhook_fail_closed():
    """Verify TradingView normalizer fails closed on missing symbol or invalid volume."""
    # 1. Missing symbol raises ValueError
    with pytest.raises(ValueError, match="Missing ticker/symbol"):
        normalize_tradingview_payload({"action": "buy", "volume": "0.1"})

    # 2. Non-positive volume raises ValueError
    with pytest.raises(ValueError, match="Volume order harus berupa angka positif"):
        normalize_tradingview_payload({"ticker": "EURUSD", "action": "buy", "volume": "-0.5"})

    with pytest.raises(ValueError, match="Volume order harus berupa angka positif"):
        normalize_tradingview_payload({"ticker": "EURUSD", "action": "buy", "volume": "0"})


def test_platform_adapters_bounded_deque():
    """Verify platform adapters use bounded deques (maxlen=100) to prevent memory leaks."""
    adapters = [
        DiscordPlatformAdapter(webhook_url="https://mock"),
        TelegramPlatformAdapter(bot_token="mock_token"),
        SlackPlatformAdapter(webhook_url="https://mock"),
        WebhookPlatformAdapter(platform_name="webhook"),
    ]
    for adapter in adapters:
        assert isinstance(adapter.sent_messages, deque)
        assert adapter.sent_messages.maxlen == 100


def test_acp_server_authenticate(monkeypatch):
    """Verify ACP server validates token against configured key."""
    server = AcpServer()
    server.send_response = MagicMock()

    # Set expected token
    monkeypatch.setenv("ACP_AUTH_TOKEN", "super_secret_acp_key")

    # 1. Wrong token -> authenticated: False
    server.handle_message(json.dumps({"id": "1", "method": "authenticate", "params": {"token": "wrong_key"}}))
    server.send_response.assert_called_with("1", result={"authenticated": False})

    # 2. Correct token -> authenticated: True
    server.handle_message(
        json.dumps({"id": "2", "method": "authenticate", "params": {"token": "super_secret_acp_key"}})
    )
    server.send_response.assert_called_with("2", result={"authenticated": True})


@pytest.mark.asyncio
async def test_telegram_callback_admin_guards():
    """Verify critical mutative callbacks are rejected for non-admin users."""
    from monika.interfaces.telegram.handlers.callback_handler import TelegramCallbackHandlerMixin

    class DummyBot(TelegramCallbackHandlerMixin):
        def __init__(self):
            self._is_authorized_val = True
            self._is_admin_val = False
            self.settings = {}
            self.execution_service = None

        def _is_authorized(self, update):
            return self._is_authorized_val

        def _is_admin(self, update):
            return self._is_admin_val

    bot = DummyBot()

    # Non-admin user tries closeall
    mock_query = AsyncMock()
    mock_query.data = "closeall:confirm:nonce123"
    mock_update = MagicMock()
    mock_update.callback_query = mock_query

    await bot._handle_callback(mock_update, MagicMock())
    mock_query.answer.assert_called_with(
        "[AKSES DITOLAK] Likuidasi portofolio hanya diizinkan untuk Admin.", show_alert=True
    )

    # Non-admin user tries killswitch
    mock_query.reset_mock()
    mock_query.data = "killswitch:confirm:nonce123"
    await bot._handle_callback(mock_update, MagicMock())
    mock_query.answer.assert_called_with("[AKSES DITOLAK] Kill Switch only permitted for Admin.", show_alert=True)

    # Non-admin user tries model override
    mock_query.reset_mock()
    mock_query.data = "mdl:s:primary:gpt-5"
    await bot._handle_callback(mock_update, MagicMock())
    mock_query.answer.assert_called_with(
        "[AKSES DITOLAK] Penggantian model hanya diizinkan untuk Admin.", show_alert=True
    )
