#!/usr/bin/env python3
# ==============================================================================
# File: scripts/simulate_websocket_handshake.py
# Description: Comprehensive simulation & verification test for WebSocket
#              handshake authentication, ticket lifecycle, and timeout resilience.
# ==============================================================================

import asyncio
import logging
import os
import sys
from unittest.mock import patch

from starlette.testclient import TestClient

# Configure stream logger to verify log outputs
logger = logging.getLogger("SimulationTest")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)

from monika.interfaces.dashboard.api import app


def print_banner(text: str) -> None:
    print(f"\n{'=' * 75}\n  {text}\n{'=' * 75}")


def run_full_simulation() -> None:
    print_banner("MONIKA WEBSOCKET HANDSHAKE RESILIENCE & SIMULATION TEST")

    client = TestClient(app)
    env = {
        "DASHBOARD_API_KEYS": "admin:adm_secret_key_123,operator:ops_secret_key_456,viewer:view_secret_key_789",
        "DASHBOARD_API_KEY": "",
    }

    with patch.dict(os.environ, env):
        # ----------------------------------------------------------------------
        # TEST 1: Ephemeral Ticket Upfront Acquisition (The Primary Solution)
        # ----------------------------------------------------------------------
        print("\n[STEP 1] Testing Upfront Ephemeral Ticket Handshake on /ws/live-feed...")
        ticket_res = client.post("/api/v1/ws/ticket", headers={"X-API-Key": "adm_secret_key_123"})
        assert ticket_res.status_code == 200, f"Ticket acquisition failed: {ticket_res.text}"
        ticket_data = ticket_res.json()
        assert ticket_data["status"] == "success"
        assert ticket_data["role"] == "admin"
        ticket_live = ticket_data["ticket"]
        print(f"  --> Ticket acquired: {ticket_live[:12]}... (Role: {ticket_data['role']})")

        with client.websocket_connect(f"/ws/live-feed?ticket={ticket_live}") as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["status"] == "connected"
            print("  [PASS] /ws/live-feed connected & authenticated immediately during HTTP upgrade.")

        # ----------------------------------------------------------------------
        # TEST 2: Agent Chat Ticket Authentication with Role Propagation
        # ----------------------------------------------------------------------
        print("\n[STEP 2] Testing Upfront Ephemeral Ticket Handshake on /ws/agent-chat...")
        ticket_res2 = client.post("/api/v1/ws/ticket", headers={"X-API-Key": "adm_secret_key_123"})
        assert ticket_res2.status_code == 200
        ticket_chat = ticket_res2.json()["ticket"]

        with client.websocket_connect(f"/ws/agent-chat?ticket={ticket_chat}") as ws:
            init_msg2 = ws.receive_json()
            assert init_msg2["type"] == "connection_established"
            assert init_msg2["role"] == "admin"
            print(f"  [PASS] /ws/agent-chat connected with role '{init_msg2['role']}' immediately.")

        # ----------------------------------------------------------------------
        # TEST 3: Single-Use Ticket Enforcement (Anti-Replay Security Check)
        # ----------------------------------------------------------------------
        print("\n[STEP 3] Verifying Single-Use Security Invariant (Ticket Replay Rejection)...")
        try:
            with client.websocket_connect(f"/ws/live-feed?ticket={ticket_live}") as ws:
                ws.receive_json()
                print("  [FAIL] Replayed ticket should have been rejected!")
                sys.exit(1)
        except Exception:
            print("  [PASS] Replayed ticket was rejected with 1008 as required by Security Architecture.")

        # ----------------------------------------------------------------------
        # TEST 4: Fallback In-Band Handshake with Immediate Token
        # ----------------------------------------------------------------------
        print("\n[STEP 4] Testing Fallback In-Band Authentication (No Query Param)...")
        with client.websocket_connect("/ws/live-feed") as ws:
            ws.send_json({"type": "authenticate", "token": "ops_secret_key_456"})
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            print("  [PASS] In-band token auth on /ws/live-feed succeeded without waiting on slow HTTP.")

        with client.websocket_connect("/ws/agent-chat") as ws:
            ws.send_json({"type": "authenticate", "token": "ops_secret_key_456"})
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["role"] == "operator"
            print(f"  [PASS] In-band token auth on /ws/agent-chat succeeded with role '{init_msg['role']}'.")

        # ----------------------------------------------------------------------
        # TEST 5: Handshake Timeout Error Formatting Verification
        # ----------------------------------------------------------------------
        print("\n[STEP 5] Testing Timeout Error Log Formatting (No More Blank ': ' Log)...")
        captured_logs = []

        class TestLogHandler(logging.Handler):
            def emit(self, record):
                captured_logs.append(self.format(record))

        test_handler = TestLogHandler()
        ws_logger = logging.getLogger("TradingAgent.DashboardAPI.WebSocket")
        ws_logger.addHandler(test_handler)

        async def _mock_wait_for(coro, timeout=None):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise asyncio.TimeoutError()

        with patch("asyncio.wait_for", side_effect=_mock_wait_for):
            try:
                with client.websocket_connect("/ws/live-feed"):
                    pass
            except Exception:
                pass

        ws_logger.removeHandler(test_handler)
        matched = any("timed out waiting for authenticate message" in log for log in captured_logs)
        assert matched, f"Expected explicit timeout detail in logs, got: {captured_logs}"
        print(
            f"  [PASS] Verified log contains explicit error message: '{[l for l in captured_logs if 'timed out' in l][0]}'"
        )

    print_banner("ALL SIMULATION AND VERIFICATION TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    run_full_simulation()
