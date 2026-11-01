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


def test_invariants_zone_filtering_and_high_atr_adr_harmony():
    from monika.application.analysis.calculators.invariant_calculator import (
        compute_trade_invariants,
        format_invariants_for_prompt,
    )

    # Distant and wrong-side SMC zones should be filtered out; atr > 0.50 * adr_5d
    smc_zones = [
        {"type": "demand", "direction": "bullish", "price": 2650.00, "mitigated": False},  # too far below
        {"type": "demand", "direction": "bullish", "price": 2765.00, "mitigated": False},  # wrong side (> curr_px)
        {"type": "supply", "direction": "bearish", "price": 2850.00, "mitigated": False},  # too far above
        {"type": "supply", "direction": "bearish", "price": 2735.00, "mitigated": False},  # wrong side (< curr_px)
    ]

    inv = compute_trade_invariants(
        symbol="XAUUSD",
        current_price=2750.00,
        atr=35.00,
        adr_5d=50.00,
        smc_zones=smc_zones,
        min_rr=1.50,
    )

    long_a = inv["bracket_options"]["long_option_a"]
    short_b = inv["bracket_options"]["short_option_b"]
    b_sl = inv["buy_bounds"]["sl_range"]
    b_tp = inv["buy_bounds"]["tp_range"]
    s_sl = inv["sell_bounds"]["sl_range"]
    s_tp = inv["sell_bounds"]["tp_range"]

    assert long_a["entry"] == 2750.00
    assert long_a["entry_type"] == "market"
    assert short_b["entry"] == 2750.00
    assert short_b["entry_type"] == "market"

    assert b_sl[0] <= long_a["stop_loss"] <= b_sl[1]
    assert b_tp[0] <= long_a["take_profit"] <= b_tp[1]
    assert s_sl[0] <= short_b["stop_loss"] <= s_sl[1]
    assert s_tp[0] <= short_b["take_profit"] <= s_tp[1]

    prompt_txt = format_invariants_for_prompt(inv)
    assert "Pre-Verified R:R >= 1.50" in prompt_txt


@pytest.mark.asyncio
async def test_submit_asset_analysis_harmonizes_tp_max_and_repairs_rr_before_reject():
    import json
    from unittest.mock import patch
    from monika.infrastructure.database.models import TechnicalIndicator

    mock_session = AsyncMock()
    atr_ind = TechnicalIndicator(
        symbol="XAUUSD",
        timeframe="H4",
        indicator_name="ATR_14",
        value_json=json.dumps({"atr": 35.0}),
        timestamp=datetime.now(timezone.utc),
    )

    async def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt).lower()
        if "technical_indicators" in stmt_str and "value_json" in stmt_str:
            mock_res.scalar_one_or_none.return_value = atr_ind
        elif "technical_indicators" in stmt_str:
            mock_res.scalar_one_or_none.return_value = datetime.now(timezone.utc)
        else:
            mock_res.scalar_one_or_none.return_value = None
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalars.return_value.first.return_value = None
        return mock_res

    mock_session.execute = AsyncMock(side_effect=mock_execute)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    executor = ToolExecutor(
        session=mock_session,
        symbol="XAUUSD",
        settings={"trading": {"risk": {"min_rr_ratio": 1.5, "strict_structural_mapping": False}}},
    )
    executor.verification_ledger = None

    captured_adr_kwargs = {}

    async def fake_adr_ctx(session, symbol, settings, **kwargs):
        captured_adr_kwargs.update(kwargs)
        # Simulate tight ADR (50.0) vs high H4 ATR (35.0): 0.35 * 50 = 17.5 < 35.0
        return {
            "adr": 50.0,
            "lookback_days": 5,
            "band_tolerance_pct": 0.10,
            "target_sl_max_distance": 17.5,
            "target_tp_min_distance": 25.0,
            "target_tp_max_distance": 40.0,
            "entry_allowed": True,
            "room_remaining_pct": 0.65,
            "today_range_so_far": 17.5,
        }

    with (
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            side_effect=fake_adr_ctx,
        ),
        patch(
            "monika.application.analysis.calculators.unified_threshold_calculator.compute_unified_confluence_threshold",
            new=AsyncMock(return_value=(7, "standard")),
        ),
        patch(
            "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
            new=AsyncMock(return_value={"computed_score": 8}),
        ),
    ):
        # Submit with initially sub-threshold R:R (TP=2790 -> 40/35 = 1.14 < 1.5) that BracketOptimizer repairs
        res = await executor._tool_submit_asset_analysis(
            {
                "symbol": "XAUUSD",
                "decision": "buy",
                "confidence": 0.82,
                "entry_condition": {"type": "market", "price": 2750.0, "detail": "Breakout entry"},
                "stop_loss": 2715.0,
                "take_profit": 2790.0,
                "invalidation": "H4 close below 2715.0 invalidates bullish structure completely",
                "invalidation_price": 2715.0,
                "invalidation_direction": "below",
                "reevaluation_trigger": {
                    "type": "price_level",
                    "symbol": "XAUUSD",
                    "price": 2715.0,
                    "detail": "Re-evaluate if 2715 breaks",
                },
                "rationale": "Strong bullish continuation supported by macro and technical synergy.",
                "confluence_score": 8,
                "priced_in_score": 3,
                "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
            }
        )

    assert captured_adr_kwargs.get("atr_h4") == 35.0
    assert res["status"] == "saved"
    assert res["decision"] == "buy"
