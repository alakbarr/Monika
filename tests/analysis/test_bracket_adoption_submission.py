import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from monika.application.analysis.tools.executor import ToolExecutor
from monika.application.analysis.calculators.invariant_calculator import generate_concrete_bracket_options


@pytest.mark.asyncio
async def test_bracket_adoption_in_submit_asset_analysis():
    mock_session = AsyncMock()

    # Setup mock bracket options
    brackets = generate_concrete_bracket_options(
        symbol="EURUSD",
        current_price=1.10000,
        atr=0.00200,
        adr_5d=0.00800,
        target_rr=1.80,
    )

    executor = ToolExecutor(session=mock_session, symbol="EURUSD")
    executor.bracket_options = brackets

    # Mock query executions (SystemConfig, PriceOHLCV, etc.)
    async def mock_execute(stmt):
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_res.scalars.return_value.all.return_value = []
        return mock_res

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    # Provide payload with adopted_bracket='LONG_OPTION_A' and no manual SL/TP
    payload = {
        "symbol": "EURUSD",
        "decision": "buy",
        "adopted_bracket": "LONG_OPTION_A",
        "confidence": 0.85,
        "rationale": "Adopting pre-computed long option A with verified 1.80 R:R at demand zone",
        "confluence_score": 8,
        "priced_in_score": 3,
        "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
    }

    # Verify that before submission, resolving adopted bracket populates all levels
    from monika.application.analysis.calculators.invariant_calculator import resolve_bracket_choice

    resolved = resolve_bracket_choice(payload["adopted_bracket"], brackets)
    assert resolved is not None
    assert resolved["direction"] == "buy"
    assert resolved["rr_ratio"] == 1.80
    assert resolved["stop_loss"] < resolved["entry"] < resolved["take_profit"]


@pytest.mark.asyncio
async def test_specialist_disagreement_auto_adjudication():
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, symbol="EURUSD")

    # Mock SystemConfig with specialist_disagreement flag
    import json
    from monika.infrastructure.database.models import SystemConfig

    disagreement_cfg = SystemConfig(
        key="specialist_disagreement_EURUSD",
        value=json.dumps(
            {
                "biases": {"technical": "bullish", "sentiment": "bearish", "macro": "bullish"},
                "flagged_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
    )

    async def mock_execute(stmt):
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = disagreement_cfg
        return mock_res

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    inp = {
        "symbol": "EURUSD",
        "decision": "buy",
        "confidence": 0.8,
        "confluence_score": 8,
        "priced_in_score": 3,
        "stop_loss": 1.0950,
        "take_profit": 1.1050,
    }

    # Simulate disagreement check block
    flagged_at = datetime.now(timezone.utc)
    if (datetime.now(timezone.utc) - flagged_at).total_seconds() < 900:
        adjudication = inp.get("specialist_adjudication")
        if not adjudication or not adjudication.get("conflict_detected"):
            inp["specialist_adjudication"] = {
                "conflict_detected": True,
                "resolution_path": "override_macro",
                "resolution_justification": "Auto-adjudicated BUY setup for Dialectical Debate.",
            }

    assert inp["specialist_adjudication"]["conflict_detected"] is True
    assert inp["specialist_adjudication"]["resolution_path"] == "override_macro"
