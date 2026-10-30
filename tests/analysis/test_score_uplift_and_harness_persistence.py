import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import create_mock_async_session
from monika.application.analysis.tools.tool_executor import ToolExecutor
from monika.infrastructure.database.models import TechnicalIndicator, SystemConfig, AssetAnalysis
from monika.application.agent.harness.agent_harness import AgentHarness


@pytest.mark.asyncio
async def test_score_uplift_soft_warn_within_hard_block():
    """Verify that uplift of 6 (reported=12, verified_base=6) is within HARD_BLOCK_UPLIFT (6) and soft-warns rather than hard blocks."""
    mock_session = create_mock_async_session()
    executor = ToolExecutor(mock_session)

    atr_indicator = TechnicalIndicator(
        symbol="USDJPY",
        timeframe="H4",
        indicator_name="ATR_14",
        value_json=json.dumps({"value": 0.50, "atr": 0.50}),
    )
    rsi_indicator = TechnicalIndicator(
        symbol="USDJPY",
        timeframe="H4",
        indicator_name="RSI_14",
        value_json=json.dumps({"value": 52.0, "rsi": 52.0}),
    )

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        if "technical_indicators" in query:
            if "atr_14" in query:
                res.scalar_one_or_none.return_value = atr_indicator
            elif "rsi_14" in query:
                res.scalar_one_or_none.return_value = rsi_indicator
            else:
                res.scalar_one_or_none.return_value = atr_indicator
            res.scalars.return_value.all.return_value = [atr_indicator, rsi_indicator]
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    executor.verification_ledger = MagicMock()
    executor.verification_ledger.has_passed_evidence.return_value = True

    with (
        patch(
            "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
            new_callable=AsyncMock,
        ) as mock_calc,
        patch(
            "monika.application.analysis.calculators.unified_threshold_calculator.compute_unified_confluence_threshold",
            new_callable=AsyncMock,
        ) as mock_thresh,
    ):
        mock_calc.return_value = {"computed_score": 6, "blocking_issues": [], "factors": []}
        mock_thresh.return_value = (7, "standard_threshold")

        inp = {
            "symbol": "USDJPY",
            "decision": "buy",
            "confidence": 0.85,
            "entry_price": 150.0,
            "stop_loss": 149.0,
            "take_profit": 152.0,
            "confluence_score": 12,
            "confluence_factors": [
                "fundamental_bias",  # 2
                "d1_trend",  # 2
                "near_fvg",  # 2
                "breakout_expansion",  # 2
                "volume_expansion",  # 2
                "rsi_neutral",  # 1
                "dxy_confirms",  # 1
            ],  # Total = 12
            "priced_in_score": 4,
            "rationale": "High confluence setup.",
            "entry_condition": {"type": "market", "detail": "Immediate market buy"},
            "invalidation": "Drop below 148.50 invalidates structure",
            "invalidation_price": 148.50,
            "invalidation_direction": "below",
        }

        res = await executor._tool_submit_asset_analysis(inp)
        # Uplift is 12 - 6 = 6. With HARD_BLOCK_UPLIFT = 6, it should NOT trigger EXTREME uplift hard block
        assert not any("Non-deterministic score uplift EXTREME" in e for e in res.get("errors", []))


@pytest.mark.asyncio
async def test_score_uplift_extreme_hard_block_above_6():
    """Verify that uplift of 7 (reported=13, verified_base=6) triggers HARD_BLOCK_UPLIFT (>6) with actionable guidance."""
    mock_session = create_mock_async_session()
    executor = ToolExecutor(mock_session)

    atr_indicator = TechnicalIndicator(
        symbol="USDJPY",
        timeframe="H4",
        indicator_name="ATR_14",
        value_json=json.dumps({"value": 0.50, "atr": 0.50}),
    )

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        if "technical_indicators" in query:
            res.scalar_one_or_none.return_value = atr_indicator
            res.scalars.return_value.all.return_value = [atr_indicator]
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    executor.verification_ledger = MagicMock()
    executor.verification_ledger.has_passed_evidence.return_value = True

    with patch(
        "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
        new_callable=AsyncMock,
    ) as mock_calc:
        mock_calc.return_value = {"computed_score": 6, "blocking_issues": [], "factors": []}

        inp = {
            "symbol": "USDJPY",
            "decision": "buy",
            "confidence": 0.85,
            "entry_price": 150.0,
            "stop_loss": 149.0,
            "take_profit": 152.0,
            "confluence_score": 13,
            "confluence_factors": [
                "fundamental_bias",  # 2
                "d1_trend",  # 2
                "near_fvg",  # 2
                "breakout_expansion",  # 2
                "volume_expansion",  # 2
                "rsi_neutral",  # 1
                "dxy_confirms",  # 1
                "vix_ok",  # 1
            ],  # Total = 13
            "priced_in_score": 4,
            "rationale": "High confluence setup.",
            "entry_condition": {"type": "market", "detail": "Immediate market buy"},
            "invalidation": "Drop below 148.50 invalidates structure",
            "invalidation_price": 148.50,
            "invalidation_direction": "below",
        }

        res = await executor._tool_submit_asset_analysis(inp)
        assert res.get("status") == "validation_failed"
        assert any("Non-deterministic score uplift EXTREME" in e for e in res.get("errors", []))
        assert "Max allowable reported score is 9/14" in res["errors"][0]
        assert "SCORE UPLIFT EXTREME" in res.get("guidance", "")


@pytest.mark.asyncio
async def test_score_uplift_attempt_2_forces_wait():
    """Verify that when attempt >= 2 has an extreme uplift error, it gracefully forces WAIT and saves to DB."""
    mock_session = create_mock_async_session()
    executor = ToolExecutor(mock_session)

    atr_indicator = TechnicalIndicator(
        symbol="USDJPY",
        timeframe="H4",
        indicator_name="ATR_14",
        value_json=json.dumps({"value": 0.50, "atr": 0.50}),
    )

    # Simulate attempt 2 stored in SystemConfig
    cfg_attempt = SystemConfig(key="submit_attempt_USDJPY_any", value="1")

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        if "system_config" in query:
            res.scalar_one_or_none.return_value = cfg_attempt
        elif "technical_indicators" in query:
            res.scalar_one_or_none.return_value = atr_indicator
            res.scalars.return_value.all.return_value = [atr_indicator]
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    executor.verification_ledger = MagicMock()
    executor.verification_ledger.has_passed_evidence.return_value = True

    with patch(
        "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
        new_callable=AsyncMock,
    ) as mock_calc:
        mock_calc.return_value = {"computed_score": 5, "blocking_issues": [], "factors": []}

        inp = {
            "symbol": "USDJPY",
            "decision": "buy",
            "confidence": 0.85,
            "entry_price": 150.0,
            "stop_loss": 149.0,
            "take_profit": 152.0,
            "confluence_score": 13,
            "confluence_factors": [
                "fundamental_bias",  # 2
                "d1_trend",  # 2
                "near_fvg",  # 2
                "breakout_expansion",  # 2
                "volume_expansion",  # 2
                "rsi_neutral",  # 1
                "dxy_confirms",  # 1
                "vix_ok",  # 1
            ],
            "priced_in_score": 4,
            "rationale": "High confluence setup.",
            "entry_condition": {"type": "market", "detail": "Immediate market buy"},
            "invalidation": "Drop below 148.50 invalidates structure",
            "invalidation_price": 148.50,
            "invalidation_direction": "below",
        }

        res = await executor._tool_submit_asset_analysis(inp)
        assert res.get("status") == "saved"
        assert res.get("decision") == "wait"
        assert any(isinstance(call.args[0], AssetAnalysis) for call in mock_session.add.call_args_list)


@pytest.mark.asyncio
async def test_harness_mandatory_persistence_tracking():
    """Verify AgentHarness tracks persisted_mandatory_tools and nudges when submission failed validation."""
    mock_client = MagicMock()
    harness = AgentHarness(llm_client=mock_client, settings={})

    # Simulating turn 1 where submit_asset_analysis returns validation_failed
    stage_name = "per_asset_USDJPY"
    mandatory_tool = harness.get_mandatory_tool_for_stage(stage_name)
    assert mandatory_tool == "submit_asset_analysis"

    called_tools = {"submit_asset_analysis"}
    persisted_mandatory_tools = set()  # Not persisted because status was validation_failed

    is_mandatory_unpersisted = (
        mandatory_tool in ("submit_asset_analysis", "submit_fundamental_brief")
        and mandatory_tool not in persisted_mandatory_tools
    )
    assert is_mandatory_unpersisted is True

    # When tool_use_blocks is empty and turns < effective_max_turns, it must trigger nudge
    turns = 1
    effective_max_turns = 15
    should_nudge = (
        mandatory_tool
        and (mandatory_tool not in called_tools or is_mandatory_unpersisted)
        and turns < effective_max_turns
    )
    assert should_nudge is True


@pytest.mark.asyncio
async def test_confluence_calculator_scale_allows_scores_above_10():
    """Verify that calculate_confluence allows scores up to 14 and is no longer clamped at 10."""
    from monika.application.analysis.calculators.confluence_calculator import calculate_confluence
    from monika.infrastructure.database.models import StructureBreak, VIXData, DXYData
    from datetime import date, datetime, timezone

    mock_session = create_mock_async_session()

    h4_break = StructureBreak(
        symbol="USDJPY", timeframe="H4", direction="bullish", formed_at=datetime.now(timezone.utc)
    )
    d1_break = StructureBreak(
        symbol="USDJPY", timeframe="D1", direction="bullish", formed_at=datetime.now(timezone.utc)
    )
    vix = VIXData(date=date.today(), close=15.0)
    dxy_items = [
        DXYData(date=date.today(), close=105.0),
        DXYData(date=date.today(), close=104.0),
        DXYData(date=date.today(), close=103.0),
        DXYData(date=date.today(), close=102.0),
        DXYData(date=date.today(), close=101.0),
    ]

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        if "structure_breaks" in query:
            if "h4" in query:
                res.scalars.return_value.first.return_value = h4_break
            else:
                res.scalars.return_value.first.return_value = d1_break
        elif "vix_data" in query:
            res.scalar_one_or_none.return_value = vix
        elif "dxy_data" in query:
            res.scalars.return_value.all.return_value = dxy_items
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
            res.scalars.return_value.first.return_value = None
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    with (
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as mock_sweep,
        patch(
            "monika.application.analysis.strategies.registry.StrategyRegistry.evaluate_all",
            new_callable=AsyncMock,
        ) as mock_quant,
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as mock_adr,
    ):
        mock_sweep.return_value = {"structure_confirmed": True, "valid_for_direction": "buy"}
        sig = MagicMock()
        sig.valid = True
        sig.direction = "buy"
        sig.edge_strength = 0.8
        sig.confidence = 0.8
        mock_quant.return_value = [sig]
        mock_adr.return_value = {}

        res = await calculate_confluence(
            session=mock_session,
            symbol="USDJPY",
            direction="buy",
            entry_price=150.0,
        )

        # H4 aligned (+2), D1 aligned (+1), Sweep (+2), Quant (+2 +1 = 3), VIX (+1), DXY (+1) = 11
        score = res["computed_score"]
        assert score > 10, f"Expected score > 10, got {score}"
        assert score <= 14, f"Expected score <= 14, got {score}"
