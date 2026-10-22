# ==============================================================================
# File: tests/agent/test_p0_safety_and_invariants.py
# ==============================================================================

import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.agent.estop import get_estop_candidate_paths, is_estop_active
from monika.application.analysis.strategies.evidence_store import StrategyEvidenceStore
from monika.application.analysis.tools.handlers.advanced_quant_tools import handle_simulate_portfolio_drawdown
from monika.application.analysis.tools.handlers.ptc_handler import PTCHandler
from monika.application.agent.chat.pending_actions import PendingAction
from monika.application.agent.chat.action_state import ActionStateMixin


def test_estop_candidates_include_repo_root_and_cwd():
    candidates = get_estop_candidate_paths()
    cwd_estop = Path.cwd() / "ESTOP"
    assert cwd_estop in candidates
    from monika.core.paths import get_repo_root

    assert (get_repo_root() / "ESTOP") in candidates


def test_evidence_store_fail_closed_on_empty_store(tmp_path):
    # Use a temporary store so the test does not depend on runtime evidence state.
    store = StrategyEvidenceStore(tmp_path / "strategy_evidence_store.json")
    assert len(store._store) == 0

    # General baseline allowed
    ok_gen, _ = store.is_strategy_eligible_to_trade("general")
    assert ok_gen is True

    # Specific strategy ID without verified backtest must be REJECTED (fail-closed)
    ok_strat, reason = store.is_strategy_eligible_to_trade("custom_breakout_alpha")
    assert ok_strat is False
    assert "No verified backtest evidence" in reason


@pytest.mark.asyncio
async def test_quant_tools_crypto_contract_size_fallback():
    mock_client = AsyncMock(spec=["ensure_connected", "get_account_info"])
    mock_client.ensure_connected = AsyncMock(return_value=True)
    mock_client.get_account_info = AsyncMock(
        return_value={"equity": 50000.0, "margin_free": 50000.0, "leverage": 100.0}
    )

    # Simulate portfolio drawdown on BTCUSD: 1 lot, entry 60000, sl 59000 (1000 pts)
    positions = [{"symbol": "BTCUSD", "direction": "buy", "lots": 1.0, "entry": 60000.0, "sl": 59000.0}]
    res = await handle_simulate_portfolio_drawdown(
        {"positions": positions},
        mt5_client=mock_client,
        settings={"trading": {"risk": {"max_daily_drawdown_percent": 5.0}}},
    )

    assert "details" in res
    pos_res = res["details"][0]
    # For BTCUSD with contract_size 1.0, 1000 pts loss on 1 lot = $1000 USD (NOT $100,000,000)
    assert pos_res["sl_loss_usd"] == 1000.0
    # Margin req: (60000 * 1.0 * 1.0) / 100 = $600 USD (NOT $60,000,000)
    assert pos_res["margin_req_usd"] == 600.0


@pytest.mark.asyncio
async def test_ptc_handler_blocks_mutating_trade_tools():
    mock_executor = AsyncMock()
    handler = PTCHandler(mock_executor)

    rpc, port = await handler._start_tool_rpc_server()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        import json

        # Attempt to call place_order through PTC
        payload = {"tool": "place_order", "args": {"symbol": "EURUSD"}, "token": rpc.token}
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()

        resp_line = await reader.readline()
        resp = json.loads(resp_line.decode("utf-8"))
        assert "error" in resp
        assert "forbidden in PTC" in resp["error"]

        # Attempt to call custom mutating tool
        payload2 = {"tool": "execute_trade_custom", "args": {}, "token": rpc.token}
        writer2, reader2 = writer, reader  # connection is closed per request by server
        reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
        writer2.write((json.dumps(payload2) + "\n").encode("utf-8"))
        await writer2.drain()
        resp_line2 = await reader2.readline()
        resp2 = json.loads(resp_line2.decode("utf-8"))
        assert "error" in resp2
        assert "forbidden in PTC" in resp2["error"]
    finally:
        rpc.close()
        await rpc.wait_closed()


@pytest.mark.asyncio
async def test_action_state_persisted_claim_race_safety():
    class DummyChatAgent(ActionStateMixin):
        def __init__(self):
            self._pending_actions = {}
            self._session_approvals = {}
            self._consecutive_denials = 0
            self._proposals_paused = False
            self.user_id = 12345
            self._action_lock = asyncio.Lock()

        async def _execute_action(self, action):
            return "SUCCESS: Order filled"

    agent = DummyChatAgent()
    action = PendingAction(
        action_id="test_act_123",
        action_type="place_order",
        params={"symbol": "EURUSD"},
        description="Buy EURUSD",
        is_persisted=True,
    )
    agent._pending_actions[action.action_id] = action

    # Mock _claim_persisted_pending_action: first caller wins, second caller loses
    claim_calls = 0

    async def mock_claim(action_id):
        nonlocal claim_calls
        claim_calls += 1
        return claim_calls == 1  # only first claim succeeds

    agent._claim_persisted_pending_action = mock_claim

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("monika.application.agent.chat.action_state.get_session", return_value=mock_ctx):
        # First confirmation
        ok1, msg1 = await agent.confirm_action("test_act_123")
        assert ok1 is True

        # Second confirmation (simulating double click or duplicate process)
        ok2, msg2 = await agent.confirm_action("test_act_123")
        assert ok2 is False
        assert "already processed" in msg2 or "not found" in msg2
