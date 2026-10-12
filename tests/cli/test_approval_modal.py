# ==============================================================================
# File: tests/cli/test_approval_modal.py
# Description: Unit Tests for Textual ApprovalModalScreen (HITL Trade Approval)
# ==============================================================================

import pytest
from cli.overlays.approval_modal import ApprovalModalScreen


def test_approval_modal_initialization():
    """Verify ApprovalModalScreen correctly extracts action metadata and parameters."""
    action = {
        "id": "act_101",
        "description": "Execute BUY on EURUSD 0.50 lots",
        "parameters": {
            "symbol": "EURUSD",
            "direction": "buy",
            "volume": 0.50,
            "entry_price": 1.0850,
            "sl": 1.0820,
            "tp": 1.0910,
            "risk_usd": 150.00,
        },
    }
    screen = ApprovalModalScreen(action)
    assert screen.action_id == "act_101"
    assert "EURUSD" in screen.description
    assert screen.params["symbol"] == "EURUSD"
    assert screen.params["volume"] == 0.50
    assert screen.params["sl"] == 1.0820


def test_approval_modal_empty_parameters():
    """Verify ApprovalModalScreen handles empty/missing parameter dictionaries gracefully."""
    action = {
        "id": "act_999",
        "description": "Generic system command",
    }
    screen = ApprovalModalScreen(action)
    assert screen.action_id == "act_999"
    assert screen.params == {}


def test_approval_modal_dismiss_actions():
    """Verify action methods dismiss screen with expected decision payloads."""
    action = {"id": "act_202", "description": "Close all open positions"}
    screen = ApprovalModalScreen(action)

    dismiss_results = []
    screen.dismiss = lambda result=None: dismiss_results.append(result)

    screen.action_allow_once()
    assert dismiss_results[-1] == "allow_once"

    screen.action_allow_session()
    assert dismiss_results[-1] == "allow_session"

    screen.action_deny()
    assert dismiss_results[-1] == "deny"


def test_approval_modal_button_dispatch():
    """Verify on_button_pressed routes button IDs to corresponding actions."""
    action = {"id": "act_303", "description": "Submit SELL on XAUUSD"}
    screen = ApprovalModalScreen(action)

    dismiss_results = []
    screen.dismiss = lambda result=None: dismiss_results.append(result)

    class DummyButton:
        def __init__(self, btn_id):
            self.id = btn_id

    class DummyEvent:
        def __init__(self, btn_id):
            self.button = DummyButton(btn_id)

    screen.on_button_pressed(DummyEvent("btn_allow_once"))
    assert dismiss_results[-1] == "allow_once"

    screen.on_button_pressed(DummyEvent("btn_allow_session"))
    assert dismiss_results[-1] == "allow_session"

    screen.on_button_pressed(DummyEvent("btn_deny"))
    assert dismiss_results[-1] == "deny"
