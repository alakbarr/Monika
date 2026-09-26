# ==============================================================================
# File: tests/gateway/test_phase2_gateways_and_approvals.py
# ==============================================================================

"""
Comprehensive Unit Tests for Phase 2:
  1. Delivery Ledger Flood Control & Deferrals
  2. Cryptographic Approval Transport & Tamper-Proof Binding
  3. Webhook Ingress & Replay Protection
  4. ACP (Agent Client Protocol) Server Enhancements
"""

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import time
import pytest

from gateway.delivery_ledger import DeliveryLedger, DeliveryStatus
from gateway.webhook_ingress import (
    WebhookIngressRouter,
    WebhookIngressStatus,
    WebhookSignatureVerifier,
)
from gateway.acp_server import AcpServer
from risk.approval_transport import (
    ApprovalDecisionPayload,
    ApprovalRequestPayload,
    ApprovalTransport,
    canonical_json,
    compute_sha256_digest,
)
from risk.approval_hub import ApprovalHub, ApprovalStatus


# ==============================================================================
# 1. Delivery Ledger Flood Control Tests
# ==============================================================================

def test_delivery_ledger_flood_wait_extraction():
    ledger = DeliveryLedger(db_path=":memory:")
    
    # Telegram error pattern
    err_tg = "Too Many Requests: retry after 42"
    assert ledger.extract_flood_wait(err_tg) == 42.0

    # Generic HTTP 429 pattern
    err_http = "HTTP 429 Too Many Requests. Rate limited, wait 15 seconds."
    assert ledger.extract_flood_wait(err_http) == 15.0

    # Non-flood error returns None
    err_other = "Connection reset by peer"
    assert ledger.extract_flood_wait(err_other) is None


def test_delivery_ledger_mark_flood_delayed():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        ledger = DeliveryLedger(db_path=db_path)
        key = ledger.generate_idempotency_key("telegram", "chat_123", "Trading Alert")
        is_new, record = ledger.register_intent(
            idempotency_key=key,
            platform="telegram",
            recipient_id="chat_123",
            payload={"text": "Trading Alert"},
        )
        assert is_new is True
        assert record.status == DeliveryStatus.PENDING
        assert record.attempts == 0

        # Mark as flood delayed with 60s wait
        now = time.time()
        ledger.mark_flood_delayed(
            idempotency_key=key,
            wait_seconds=60.0,
        )
        delayed = ledger.get_record(key)
        assert delayed is not None
        assert delayed.status == DeliveryStatus.PENDING
        assert delayed.attempts == 0  # Crucial: 429 must not burn through max_attempts!
        assert delayed.flood_not_before >= now + 59.0

        # Verify pending queries exclude records where flood_not_before > now
        pending = ledger.get_pending_deliveries()
        assert not any(p.idempotency_key == key for p in pending)
    finally:
        if os.path.exists(db_path):

            os.remove(db_path)


# ==============================================================================
# 2. Cryptographic Approval Transport Tests
# ==============================================================================

def test_canonical_json_determinism():
    d1 = {"b": 2, "a": 1, "c": {"y": [1, 2], "x": "val"}}
    d2 = {"c": {"x": "val", "y": [1, 2]}, "a": 1, "b": 2}
    
    # Must produce identical canonical strings regardless of insertion order
    assert canonical_json(d1) == canonical_json(d2)


def test_approval_transport_sealing_and_verification():
    now = time.time()
    req = ApprovalTransport.create_request(
        token="appr_test_123",
        action_type="CLOSE_ALL",
        level=3,
        description="Emergency close all positions",
        details={"symbol": "EURUSD", "volume": 1.5},
        requested_at=now,
        expires_at=now + 300.0,
    )
    assert req.verify_integrity() is True
    assert len(req.request_digest) == 64

    # Sign decision bound to request
    dec = ApprovalTransport.create_decision(
        request=req,
        approved=True,
        decided_by="admin_operator",
        decided_at=now + 10.0,
        reason="Manual liquidation approved",
    )
    assert dec.verify_integrity() is True
    assert dec.request_digest == req.request_digest

    # Verify valid binding
    valid, msg = ApprovalTransport.verify_binding(req, dec)
    assert valid is True
    assert "verified" in msg.lower()


def test_approval_transport_tamper_rejection():
    now = time.time()
    req = ApprovalTransport.create_request(
        token="appr_test_tamper",
        action_type="BUY",
        level=2,
        description="Buy 0.1 EURUSD",
        details={"volume": 0.1},
        requested_at=now,
        expires_at=now + 300.0,
    )

    dec = ApprovalTransport.create_decision(
        request=req,
        approved=True,
        decided_by="admin_operator",
        decided_at=now + 5.0,
    )

    # Tamper with request details after signing
    req.details["volume"] = 100.0  # Malicious injection
    valid, msg = ApprovalTransport.verify_binding(req, dec)
    assert valid is False
    assert "mismatch" in msg.lower()


def test_approval_transport_expired_rejection():
    now = time.time()
    req = ApprovalTransport.create_request(
        token="appr_expired",
        action_type="SELL",
        level=2,
        description="Sell 0.5 XAUUSD",
        details={"volume": 0.5},
        requested_at=now - 500.0,
        expires_at=now - 100.0,  # Expired
    )
    dec = ApprovalDecisionPayload(
        token=req.token,
        request_digest=req.request_digest,
        approved=True,
        decided_by="admin",
        decided_at=now,
    )
    valid, msg = ApprovalTransport.verify_binding(req, dec, now=now)
    assert valid is False
    assert "expiry" in msg.lower()


# ==============================================================================
# 3. Webhook Ingress & Replay Protection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_webhook_ingress_signature_and_rotation():
    primary_secret = "secret_key_v1"
    secondary_secret = "secret_key_v2"
    verifier = WebhookSignatureVerifier(
        primary_secret=primary_secret,
        secondary_secret=secondary_secret,
        max_drift_seconds=300.0,
    )
    router = WebhookIngressRouter(verifier=verifier, enforce_signature=True, enforce_timestamp=True)

    received_events = []
    async def sample_handler(payload, headers):
        received_events.append(payload)
        return {"status": "ok"}

    router.register_handler("market_alert", sample_handler)

    now = time.time()
    body = json.dumps({"event_type": "market_alert", "symbol": "BTCUSD", "price": 68000}).encode()

    # 1. Sign with primary secret
    sig_primary = "sha256=" + hmac.new(primary_secret.encode(), body, hashlib.sha256).hexdigest()
    headers_primary = {
        "x-signature": sig_primary,
        "x-timestamp": str(now),
        "x-nonce": "nonce_001",
    }
    res1 = await router.process_event(body, headers_primary, now=now)
    assert res1.is_success is True
    assert len(received_events) == 1

    # 2. Sign with secondary rotated secret (valid during migration)
    sig_secondary = hmac.new(secondary_secret.encode(), body, hashlib.sha256).hexdigest()
    headers_secondary = {
        "x-signature": sig_secondary,
        "x-timestamp": str(now),
        "x-nonce": "nonce_002",
    }
    res2 = await router.process_event(body, headers_secondary, now=now)
    assert res2.is_success is True
    assert len(received_events) == 2

    # 3. Invalid signature rejected
    headers_bad = {
        "x-signature": "sha256=invalid_signature_hex",
        "x-timestamp": str(now),
        "x-nonce": "nonce_003",
    }
    res3 = await router.process_event(body, headers_bad, now=now)
    assert res3.status == WebhookIngressStatus.INVALID_SIGNATURE


@pytest.mark.asyncio
async def test_webhook_ingress_replay_prevention():
    secret = "test_webhook_secret"
    verifier = WebhookSignatureVerifier(primary_secret=secret, max_drift_seconds=60.0)
    router = WebhookIngressRouter(verifier=verifier)

    async def noop_handler(payload, headers):
        return True

    router.register_handler("*", noop_handler)

    now = time.time()
    body = b'{"type":"ping"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    headers = {
        "x-signature": sig,
        "x-timestamp": str(now),
        "x-nonce": "nonce_fixed_123",
    }

    # First attempt: success
    res1 = await router.process_event(body, headers, now=now)
    assert res1.is_success is True

    # Replay identical nonce: rejected
    res2 = await router.process_event(body, headers, now=now + 1.0)
    assert res2.status == WebhookIngressStatus.REPLAY_DETECTED


# ==============================================================================
# 4. ACP Server Protocol Tests
# ==============================================================================

def test_acp_server_protocol_lifecycle():
    server = AcpServer()

    # Capture outputs by intercepting sys.stdout
    import io
    import sys
    fake_stdout = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = fake_stdout

    try:
        # 1. Initialize
        server.handle_message(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
        # 2. New session
        server.handle_message(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "new_session",
            "params": {"session_id": "test_sess_01", "cwd": "/workspace"},
        }))
        # 3. Load session
        server.handle_message(json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "load_session",
            "params": {"session_id": "test_sess_01"},
        }))
    finally:
        sys.stdout = old_stdout

    output_lines = [json.loads(line) for line in fake_stdout.getvalue().strip().split("\n") if line]
    assert len(output_lines) == 3

    init_res = output_lines[0]
    assert init_res["id"] == 1
    assert init_res["result"]["agent"]["name"] == "Monika"
    assert init_res["result"]["capabilities"]["permissions"] is True

    new_res = output_lines[1]
    assert new_res["id"] == 2
    assert new_res["result"]["session_id"] == "test_sess_01"

    load_res = output_lines[2]
    assert load_res["id"] == 3
    assert load_res["result"]["session_id"] == "test_sess_01"
    assert load_res["result"]["cwd"] == "/workspace"


def test_acp_server_client_permission_resolution():
    server = AcpServer()

    # Simulate client responding to outbound request
    import io
    import sys
    fake_stdout = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = fake_stdout

    try:
        # Trigger outbound request in a separate thread
        import threading
        result_holder = []

        def worker():
            granted = server.request_permission(
                session_id="sess_perm",
                tool_name="terminal_bash",
                tool_args={"command": "dir"},
                timeout=5.0,
            )
            result_holder.append(granted)

        t = threading.Thread(target=worker)
        t.start()

        # Give small tick to let thread emit request
        time.sleep(0.05)

        # Retrieve request ID sent to stdout
        sent_req = json.loads(fake_stdout.getvalue().strip())
        outbound_id = sent_req["id"]
        assert sent_req["method"] == "request_permission"

        # Simulate editor client answering with allow_session
        client_response = {
            "jsonrpc": "2.0",
            "id": outbound_id,
            "result": {"decision": "allow_session"},
        }
        server.handle_message(json.dumps(client_response))

        t.join(timeout=2.0)
        assert len(result_holder) == 1
        assert result_holder[0] is True
    finally:
        sys.stdout = old_stdout
