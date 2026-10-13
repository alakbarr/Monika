# ==============================================================================
# File: tests/test_phase1_critical_fixes.py
# Description: Regression & Unit Tests for Phase 1 Critical Security & UI/UX Bugfixes
# ==============================================================================

import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, Request

from telegram_bot.voice_safety_gate import VoiceSafetyGate
from logging_observability.dashboard.rbac import require_role, Role
from telegram_bot.chat_agent import ChatAgent


def test_voice_safety_gate_lot_parsing_does_not_capture_price():
    """Verify price levels are NEVER parsed as lot sizes in voice commands."""
    transcript = "beli XAUUSD di 2350 sl 2340 tp 2370"
    proposal = VoiceSafetyGate.extract_trade_intent(transcript)
    assert proposal.is_trade_command is True
    assert proposal.symbol == "XAUUSD"
    assert proposal.action == "BUY"
    assert proposal.lots == 0.01  # Safe fallback, NOT 2350.0!
    assert proposal.stop_loss == 2340.0
    assert proposal.take_profit == 2370.0


def test_voice_safety_gate_valid_lot_parsing():
    """Verify explicit lot/volume keywords are correctly parsed and bounded."""
    # Pattern 1: <number> lot
    prop1 = VoiceSafetyGate.extract_trade_intent("beli XAUUSD 0.25 lot")
    assert prop1.lots == 0.25

    # Pattern 2: volume <number>
    prop2 = VoiceSafetyGate.extract_trade_intent("jual EURUSD volume 1.5")
    assert prop2.lots == 1.5

    # Pattern 3: comma decimal "0,5 lot"
    prop3 = VoiceSafetyGate.extract_trade_intent("beli GBPUSD 0,5 lot")
    assert prop3.lots == 0.5

    # Pattern 4: absurd values (>100 lots) are rejected to safe fallback
    prop4 = VoiceSafetyGate.extract_trade_intent("beli XAUUSD 500 lot")
    assert prop4.lots == 0.01


@pytest.mark.asyncio
async def test_rbac_fails_closed_when_request_missing():
    """Verify require_role raises 403 instead of bypassing when Request is missing."""
    @require_role(Role.OPERATOR)
    async def dummy_endpoint():
        return {"ok": True}

    with pytest.raises(HTTPException) as exc_info:
        await dummy_endpoint()
    assert exc_info.value.status_code == 403
    assert "Request context missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rbac_enforces_role_hierarchy():
    """Verify require_role correctly blocks VIEWER from OPERATOR endpoint."""
    @require_role(Role.OPERATOR)
    async def restricted_action(request: Request):
        return {"action": "executed"}

    # Mock viewer request
    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_request.state.role = Role.VIEWER
    mock_request.state.is_localhost = False

    with pytest.raises(HTTPException) as exc_info:
        await restricted_action(request=mock_request)
    assert exc_info.value.status_code == 403
    assert "Action requires 'operator' role" in exc_info.value.detail

    # Mock operator request
    mock_request.state.role = Role.OPERATOR
    res = await restricted_action(request=mock_request)
    assert res == {"action": "executed"}


def test_chat_agent_last_streamed_tracking():
    """Verify ChatAgent tracks streaming state correctly."""
    mock_settings = {"telegram": {"admin_id": 123}}
    agent = ChatAgent(user_id=123, settings=mock_settings)
    assert agent.was_last_turn_streamed is False
