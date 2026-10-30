from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.agent.harness.agent_harness import AgentHarness
from monika.application.analysis.tools.executor import ToolExecutor
from monika.application.analysis.tools.tool_guardrails import ReadBeforeActGuard
from monika.domain.risk.risk_gate import RiskGate
from monika.infrastructure.brokers.broker_adapter import BrokerAdapter, MT5LiveAdapter
from monika.infrastructure.database.models import AssetAnalysis
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockBlock, MockResponse
from tests.conftest import create_mock_async_session


class DummyHarnessClient(BaseLLMClient):
    """Test client for AgentHarness."""

    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, max_tokens=4096, **kwargs)
        self.provider_name = "dummy"
        self._save_token_usage = AsyncMock()
        self._log_tool_call = AsyncMock()
        self.mock_run_tool_agent = AsyncMock()

    async def generate(self, prompt: str, system: str = "", temperature=None, max_tokens=None):
        return "dummy_text"

    async def classify_json(self, prompt: str, system_prompt=None, schema=None, temperature=None, max_tokens=None):
        return {}

    async def run_tool_agent(self, messages: list, tools: list, system_prompt=None):
        return await self.mock_run_tool_agent(messages, tools, system_prompt)

    async def run_chat_loop(self, system_prompt, conversation_history, new_user_message, tools, tool_executor=None):
        return {"reply": "ok"}


class ConcreteDummyBrokerAdapter(BrokerAdapter):
    """Minimal concrete subclass of BrokerAdapter for testing defaults."""

    async def get_account_info(self) -> Dict[str, Any]:
        return {}

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def get_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def submit_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    async def modify_order(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        return True

    async def cancel_order(self, ticket: int) -> bool:
        return True

    async def close_position(self, ticket: int, lots: Optional[float] = None) -> bool:
        return True

    async def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None


@pytest.mark.asyncio
async def test_harness_dedup_turn_refund():
    """Verify that when a tool call is satisfied by prefetch and returns dedup notice,

    the harness refunds the turn (turns -= 1, max 2).
    With max_tool_turns=2, this allows 3 tool steps before exhaustion.
    """
    mock_session = create_mock_async_session()
    client = DummyHarnessClient()
    harness = AgentHarness(client, max_tool_turns=2)

    mock_executor = AsyncMock()
    mock_executor.registry = None
    # Turn 1: dedup notice (refunded: turns 1 -> 0)
    # Turn 2: sizing call (turns 0 -> 1)
    # Turn 3: submission call (turns 1 -> 2)
    mock_executor.execute = AsyncMock(
        side_effect=[
            {"status": "skipped", "message": "already satisfied in prefetch bundle"},
            {"status": "success", "lot_size": 0.1, "risk_amount": 50.0},
            {"status": "submitted"},
        ]
    )

    resp1 = MockResponse(
        content=[
            MockBlock(
                "tool_use",
                name="get_price_history",
                input={"symbol": "EURUSD", "timeframe": "M15"},
                id="call_1",
            )
        ],
        stop_reason="tool_use",
        input_tokens=50,
        output_tokens=20,
    )
    resp2 = MockResponse(
        content=[
            MockBlock(
                "tool_use",
                name="calculate_position_size",
                input={"symbol": "EURUSD", "stop_loss": 1.0800, "take_profit": 1.0900},
                id="call_2",
            )
        ],
        stop_reason="tool_use",
        input_tokens=60,
        output_tokens=25,
    )
    resp3 = MockResponse(
        content=[
            MockBlock(
                "tool_use",
                name="submit_asset_analysis",
                input={
                    "symbol": "EURUSD",
                    "decision": "BUY",
                    "stop_loss": 1.0800,
                    "take_profit": 1.0900,
                    "take_profit_1": 1.0900,
                    "invalidation_price": 1.0780,
                    "invalidation_direction": "below",
                    "rationale": "Strong demand zone test with bullish confluence",
                    "invalidation": "Clean break below 1.0780 invalidates structure",
                    "confluence_score": 8,
                    "priced_in_score": 5,
                },
                id="call_3",
            )
        ],
        stop_reason="tool_use",
        input_tokens=70,
        output_tokens=30,
    )
    client.mock_run_tool_agent.side_effect = [resp1, resp2, resp3]

    result = await harness.run_agent_from_messages(
        session=mock_session,
        system_prompt="Analyze EURUSD",
        messages=[{"role": "user", "content": "Start"}],
        tools=[
            {"name": "get_price_history"},
            {"name": "calculate_position_size"},
            {"name": "submit_asset_analysis"},
        ],
        stage_name="per_asset_EURUSD",
        prefetch_satisfied_tools={"get_price_history"},
        tool_executor=mock_executor,
    )

    assert result["success"] is True
    # Without dedup refund, max_tool_turns=2 would have aborted at Turn 3!
    # With dedup refund, it successfully executed 3 tool calls within budget.
    assert client.mock_run_tool_agent.call_count == 3


@pytest.mark.asyncio
@patch("monika.application.analysis.calculators.confluence_calculator.calculate_confluence", new_callable=AsyncMock)
async def test_submit_asset_analysis_auto_sizing_fallback(mock_calc_conf):
    """Verify that submit_asset_analysis automatically computes sizing on the fly

    when sizing was not called beforehand, marking sizing_verified=True.
    """
    mock_calc_conf.return_value = {"computed_score": 8, "max_score": 14, "components": [], "issues": []}

    mock_session = create_mock_async_session()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    executor = ToolExecutor(mock_session)
    from monika.application.agent.harness.verification_evidence_ledger import VerificationEvidenceLedger

    v_ledger = VerificationEvidenceLedger()
    executor.verification_ledger = v_ledger

    mock_price = MagicMock()
    mock_price.scalar_one_or_none.return_value.close = 2000.0

    mock_atr = MagicMock()
    mock_atr.scalar_one_or_none.return_value.value_json = '{"atr": 15.0}'

    mock_ts = MagicMock()
    mock_ts.scalar_one_or_none.return_value = datetime.now(timezone.utc)

    mock_cfg = MagicMock()
    mock_cfg.scalar_one_or_none.return_value = None

    mock_brief = MagicMock()
    mock_brief.scalar_one_or_none.return_value = 11

    mock_fvg = MagicMock()
    mock_fvg.scalars.return_value.all.return_value = []
    mock_ob = MagicMock()
    mock_ob.scalars.return_value.all.return_value = []
    mock_swings = MagicMock()
    mock_swings.scalars.return_value.all.return_value = []

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        if "max(" in query or "min(" in query:
            return mock_ts
        elif "price_ohlcv" in query:
            return mock_price
        elif "technical_indicators" in query and "timestamp" in query and "indicator_name" not in query:
            return mock_ts
        elif "technical_indicators" in query:
            return mock_atr
        elif "system_config" in query:
            return mock_cfg
        elif "fundamental_briefs" in query:
            return mock_brief
        elif "fvg_zones" in query:
            return mock_fvg
        elif "order_blocks" in query:
            return mock_ob
        elif "swing_points" in query:
            return mock_swings
        elif "sr_zones" in query:
            return mock_swings
        return mock_brief

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    def assign_id():
        for obj in mock_session.add.call_args_list:
            if isinstance(obj[0][0], AssetAnalysis):
                obj[0][0].id = 202

    mock_session.flush.side_effect = assign_id

    # Call submit_asset_analysis WITHOUT calculate_lot_size called before
    payload = {
        "symbol": "XAUUSD",
        "decision": "buy",
        "confidence": 0.85,
        "confluence_score": 8,
        "priced_in_score": 5,
        "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
        "entry_condition": {"type": "market", "detail": "Immediate market entry"},
        "stop_loss": 1985.0,  # 15 points SL
        "take_profit": 2030.0,
        "take_profit_1": 2030.0,  # 30 points TP (RR = 2.0)
        "invalidation_price": 1975.0,
        "invalidation_direction": "below",
        "timeframe": "M15",
        "rationale": "Strong bullish continuation setup from weekly order block",
        "invalidation": "Break below 1975 structural swing invalidates setup",
    }

    res = await executor._tool_submit_asset_analysis(payload)
    assert res.get("status") in ("success", "saved")
    assert res.get("decision").upper() == "BUY"
    # Evidence ledger was automatically satisfied by the on-the-fly sizing calculation
    assert v_ledger.has_passed_evidence("XAUUSD") is True


def test_read_before_act_guard_read_tools_called():
    """Verify ReadBeforeActGuard allows submit if read tools were called in the session."""
    guard = ReadBeforeActGuard()
    guard.record_call("get_smc_zones")
    v = guard.evaluate("submit_asset_analysis", {"decision": "buy", "symbol": "EURUSD"})
    assert v.allowed is True


@pytest.mark.asyncio
async def test_broker_adapter_get_spread_and_fallback():
    """Verify MT5LiveAdapter.get_spread and base BrokerAdapter.get_spread behavior."""
    # Base BrokerAdapter returns default spread dict
    base_adapter = ConcreteDummyBrokerAdapter()
    base_spread = await base_adapter.get_spread("EURUSD")
    assert base_spread["symbol"] == "EURUSD"
    assert base_spread["spread_points"] == 0.0

    # MT5LiveAdapter returns spread details
    mock_client = AsyncMock()
    mock_client.get_spread.return_value = {
        "symbol": "EURUSD",
        "spread_points": 1.5,
        "bid": 1.08500,
        "ask": 1.08515,
        "spread_cost": 0.00015,
    }
    mt5_adapter = MT5LiveAdapter(mt5_client=mock_client)
    spread_info = await mt5_adapter.get_spread("EURUSD")
    assert spread_info["symbol"] == "EURUSD"
    assert spread_info["spread_points"] == pytest.approx(1.5, abs=0.1)
    assert spread_info["bid"] == 1.08500
    assert spread_info["ask"] == 1.08515


@pytest.mark.asyncio
async def test_execution_checks_spread_fallback():
    """Verify _check_max_spread falls back to get_tick when get_spread is not implemented."""
    mock_session = create_mock_async_session()
    mock_client = AsyncMock()
    mock_client.is_connected = AsyncMock(return_value=True)
    # Mock client has get_tick but not get_spread
    del mock_client.get_spread
    mock_client.get_tick = AsyncMock(return_value={"bid": 1.0850, "ask": 1.0852})

    gate = RiskGate(settings={"paper_trading": False}, mt5_client=mock_client)
    passed, reason = await gate._check_max_spread(mock_session, "EURUSD", is_paper=False)

    assert passed is True
    assert reason in ("ok", "spread_ok")
    assert mock_client.get_tick.called
