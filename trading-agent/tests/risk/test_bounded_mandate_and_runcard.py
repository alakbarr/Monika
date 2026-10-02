from tests.conftest import create_mock_async_session
# ==============================================================================
# File: tests/risk/test_bounded_mandate_and_runcard.py
# ==============================================================================

import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from risk.approval_hub import ApprovalHub, BoundedMandate
from logging_observability.run_card import RunCardGenerator, generate_run_card, verify_run_card


def test_bounded_mandate_lifecycle_and_validation():
    hub = ApprovalHub()
    # 1. Issue institutional mandate with 30-day TTL
    mandate = hub.issue_mandate(
        operator="risk_officer_alice",
        authorized_symbols=["EURUSD", "GBPUSD", "XAUUSD"],
        max_risk_pct=1.5,
        max_daily_dd_pct=4.0,
        max_open_positions=3,
        max_leverage=30.0,
        ttl_days=30.0,
    )
    assert mandate.mandate_id.startswith("mandate_")
    assert mandate.status == "active"
    assert mandate.verify_integrity()
    assert not mandate.is_expired

    # 2. Compliant trade
    ok, msg = hub.validate_mandate(symbol="XAUUSD", risk_pct=1.0, current_positions=1)
    assert ok is True
    assert "complies with Bounded Mandate" in msg

    # 3. Excessive risk trade
    ok, msg = hub.validate_mandate(symbol="XAUUSD", risk_pct=2.5, current_positions=1)
    assert ok is False
    assert "exceeds mandate limit" in msg

    # 4. Unauthorized symbol
    ok, msg = hub.validate_mandate(symbol="BTCUSD", risk_pct=1.0, current_positions=1)
    assert ok is False
    assert "not authorized under mandate" in msg

    # 5. Position ceiling reached
    ok, msg = hub.validate_mandate(symbol="EURUSD", risk_pct=1.0, current_positions=3)
    assert ok is False
    assert "reach/exceed mandate ceiling" in msg

    # 6. Revocation
    rev_ok, rev_msg = hub.revoke_mandate(mandate.mandate_id, operator="cro_bob", reason="Risk audit hold")
    assert rev_ok is True
    ok, msg = hub.validate_mandate(symbol="EURUSD", risk_pct=1.0, current_positions=1)
    assert ok is False
    assert "revoked" in msg


def test_bounded_mandate_ttl_expiry():
    hub = ApprovalHub()
    now = time.time()
    mandate = hub.issue_mandate(
        operator="admin",
        authorized_symbols=["ALL"],
        max_risk_pct=2.0,
        ttl_days=30.0,
    )

    # Within 30-day window
    ok, _ = hub.validate_mandate(symbol="XAUUSD", risk_pct=1.0, current_positions=0, as_of=now + 86400 * 15)
    assert ok is True

    # Exactly after 30-day TTL (day 31)
    day_31 = now + 86400 * 31
    ok, msg = hub.validate_mandate(symbol="XAUUSD", risk_pct=1.0, current_positions=0, as_of=day_31)
    assert ok is False
    assert "expired" in msg
    assert "30-day TTL exceeded" in msg
    assert mandate.status == "expired"


def test_runcard_generation_and_tamper_detection(tmp_path):
    settings = {
        "trading": {"mode": "paper", "risk": {"risk_percent_per_trade": 1.0}},
        "execution": {"mt5": {"account": "123456", "server": "MetaQuotes-Demo"}},
        "llm": {"provider": "gemini"},
    }
    card_path = str(tmp_path / "run_card.json")
    card = RunCardGenerator.generate(settings=settings, output_path=card_path)

    assert "run_id" in card
    assert "signature" in card
    assert card["git_info"] is not None
    assert card["invariant_checklist"]["hard_login_pinning"] is True
    assert card["invariant_checklist"]["two_phase_commit_disk_sync"] is True
    assert card["invariant_checklist"]["bounded_operator_mandate_ttl"] is True

    # Verify untampered card
    ok, reason = RunCardGenerator.verify(card)
    assert ok is True
    assert "verified successfully" in reason

    # Tamper with configuration fingerprint
    card_tampered = dict(card)
    card_tampered["config_fingerprint"] = dict(card["config_fingerprint"])
    card_tampered["config_fingerprint"]["trading_mode"] = "live"

    ok_tampered, reason_tampered = RunCardGenerator.verify(card_tampered)
    assert ok_tampered is False
    assert "Signature mismatch" in reason_tampered


@pytest.mark.asyncio
async def test_risk_gate_bounded_mandate_integration():
    from risk.risk_gate import RiskGate
    from risk.approval_hub import ApprovalHub
    from risk.position_sizing import SizingResult

    hub = ApprovalHub.get_instance()
    hub._mandates.clear()
    hub._active_mandate_id = None

    # Issue strict mandate for EURUSD only, max 1.0% risk
    hub.issue_mandate(
        operator="risk_lead",
        authorized_symbols=["EURUSD"],
        max_risk_pct=1.0,
        max_open_positions=2,
    )

    gate = RiskGate(settings={"trading": {"risk": {}}})
    session = create_mock_async_session()

    valid_sizing = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        account_equity=10000.0,
        risk_percent=0.8,
        risk_amount_usd=80.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.16,
        recommended_lots=0.16,
        rr_ratio=2.0,
        is_valid=True,
    )

    # 1. Check permitted trade passes bounded_mandate check
    ok, reason = await gate._check_bounded_mandate(session, "EURUSD", valid_sizing)
    assert ok is True
    assert "complies with Bounded Mandate" in reason

    # 2. Check unauthorized symbol is rejected by mandate check
    ok_unauth, reason_unauth = await gate._check_bounded_mandate(session, "GBPUSD", valid_sizing)
    assert ok_unauth is False
    assert "not authorized under mandate" in reason_unauth

    # Clean up singleton state
    hub._mandates.clear()
    hub._active_mandate_id = None
