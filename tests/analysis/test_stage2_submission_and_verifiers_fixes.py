"""Unit tests for Stage 2 submission, bracket adoption, prompt calibration, and verifier fixes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.stages.per_asset.context_builder import (
    SYSTEM_PROMPT_STATIC,
    ContextBuilder,
)
from monika.application.analysis.tools.executor import FACTOR_POINT_MAP, ToolExecutor
from monika.application.analysis.tools.mixins.base import (
    FACTOR_POINT_MAP as MIXIN_FACTOR_POINT_MAP,
)
from monika.application.analysis.validators.adjudication_verifier import (
    ADJUDICATION_SYSTEM_PROMPT,
)
from monika.application.analysis.validators.output_verifier import OutputVerifier
from monika.core.primitives.jev_primitives import build_adjudication_questions
from monika.infrastructure.database.models import FundamentalBrief
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager


def _create_mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_uncrowded_institutional_synergy_registered_and_accepted() -> None:
    """Verify 'uncrowded_institutional_synergy' has +2 pts in FACTOR_POINT_MAP and is accepted by _tool_submit_asset_analysis."""
    assert FACTOR_POINT_MAP.get("uncrowded_institutional_synergy") == 2
    assert MIXIN_FACTOR_POINT_MAP.get("uncrowded_institutional_synergy") == 2

    mock_session = _create_mock_session()
    mock_brief = FundamentalBrief(
        id=501,
        generated_at=datetime.now(timezone.utc),
        confidence=0.80,
        structured_json=json.dumps(
            {
                "currency_bias": {"EUR": "bullish", "USD": "bearish"},
                "currency_confidence": {"EUR": 0.80, "USD": 0.80},
                "per_asset_macro_matrix": {
                    "EURUSD": {
                        "directional_bias": "bullish",
                        "confidence": 0.80,
                    }
                },
                "asset_priced_in_scores": {"EURUSD": 4},
                "priced_in_assessment": {"priced_in_score": 4},
            }
        ),
    )

    def _execute_side_effect(*args: object, **_kwargs: object) -> MagicMock:
        query_str = str(args[0]).lower() if args else ""
        res = MagicMock()
        if "fundamental_briefs" in query_str:
            res.scalar_one_or_none.return_value = mock_brief
            res.scalars.return_value.all.return_value = [mock_brief]
        elif "technical_indicators.value_json" in query_str:
            mock_ind = MagicMock(
                value_json=json.dumps({"atr": 0.0025}),
                timestamp=datetime.now(timezone.utc),
            )
            res.scalar_one_or_none.return_value = mock_ind
            res.scalars.return_value.all.return_value = [mock_ind]
        elif "technical_indicators" in query_str:
            res.scalar_one_or_none.return_value = datetime.now(timezone.utc)
            res.scalars.return_value.all.return_value = [datetime.now(timezone.utc)]
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=_execute_side_effect)
    executor = ToolExecutor(mock_session)
    executor.bracket_options = {
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": 1.08500,
            "entry_type": "market",
            "stop_loss": 1.08150,
            "take_profit": 1.09060,
            "rr_ratio": 1.60,
            "sl_distance_atr": 1.20,
        }
    }

    with (
        patch(
            "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
            new=AsyncMock(return_value={"computed_score": 10}),
        ),
        patch(
            "monika.application.analysis.calculators.unified_threshold_calculator.compute_unified_confluence_threshold",
            new=AsyncMock(return_value=(7, "Standard threshold")),
        ),
    ):
        result = await executor._tool_submit_asset_analysis(
            {
                "symbol": "EURUSD",
                "decision": "buy",
                "confidence": 0.82,
                "rationale": (
                    "Technical and Macro specialists aligned bullish in DISCOUNT_ACCUMULATION_ZONE "
                    "while Sentiment is contrarian bearish (UNCROWDED_INSTITUTIONAL_SYNERGY)."
                ),
                "adopted_bracket": "LONG_OPTION_A",
                "invalidation": "Thesis invalid if H4 candle closes below 1.08150 demand origin.",
                "invalidation_price": 1.08150,
                "invalidation_direction": "below",
                "reevaluation_trigger": {
                    "type": "price_level",
                    "symbol": "EURUSD",
                    "price": 1.08150,
                    "direction": "below",
                    "detail": "Re-evaluate if price breaks below 1.08150.",
                },
                "priced_in_score": 4,
                "confluence_score": 10,
                "confluence_factors": [
                    "fundamental_bias",
                    "d1_trend",
                    "near_order_block",
                    "near_fvg",
                    "uncrowded_institutional_synergy",
                ],
            }
        )

    assert result["status"] == "saved"
    assert result["decision"] == "buy"


@pytest.mark.asyncio
async def test_resolve_adopted_bracket_persists_in_entry_condition_and_skips_check5() -> None:
    """Verify _resolve_adopted_bracket stores adopted_bracket in entry_condition and OutputVerifier skips Check 5."""
    mock_session = _create_mock_session()
    executor = ToolExecutor(mock_session)
    executor.bracket_options = {
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": 157.850,
            "entry_type": "market",
            "stop_loss": 157.450,
            "take_profit": 158.490,
            "rr_ratio": 1.60,
            "sl_distance_atr": 1.15,
        }
    }

    payload: dict[str, object] = {
        "symbol": "USDJPY",
        "decision": "buy",
        "adopted_bracket": "LONG_OPTION_A",
        "stop_loss": 157.100,  # deviated mental value that must be overwritten by pre-verified bracket
        "take_profit": 158.000,
    }
    resolved_ok = await executor._resolve_adopted_bracket(payload)
    assert resolved_ok is True
    assert payload["stop_loss"] == 157.450
    assert payload["take_profit"] == 158.490
    entry_cond = payload.get("entry_condition")
    assert isinstance(entry_cond, dict)
    assert entry_cond.get("price") == 157.850
    assert entry_cond.get("adopted_bracket") == "LONG_OPTION_A"

    # Verify OutputVerifier._run_all_checks skips Check 5 (_near_any_level) when adopted_bracket is in entry_condition
    verifier = OutputVerifier({})
    raw_output_from_db = {
        "decision": "buy",
        "entry_condition": {
            "type": "market",
            "price": 157.850,
            "detail": "Adopted verified bracket LONG_OPTION_A",
            "adopted_bracket": "LONG_OPTION_A",
        },
        "stop_loss": 157.450,
        "take_profit": 158.490,
        "confluence_score": 9,
        "priced_in_score": 4,
    }
    # Structural levels are far away (156.400, 156.600) with ATR=0.350 -> would fail Check 5 if not exempted
    context_data = {
        "get_atr_H4": {"atr": 0.350},
        "get_smc_zones_H4": {
            "order_blocks": [
                {"price_low": 156.400, "price_high": 156.600, "direction": "bullish"},
            ]
        },
    }
    failures = await verifier._run_all_checks(
        output=raw_output_from_db,
        symbol="USDJPY",
        session=None,
        settings={},
        context_data=context_data,
    )
    assert not any("far" in f and "from any structural level" in f for f in failures)

    # Also verify _apply_deterministic_math_snapping does not snap Entry away from LONG_OPTION_A
    snapped_output, snaps = verifier._apply_deterministic_math_snapping(
        output=raw_output_from_db,
        failures=[],
        settings={},
        symbol="USDJPY",
        context_data={
            "get_atr_H4": {"atr": 0.350},
            "get_smc_zones_H4": {
                "order_blocks": [
                    {"price_low": 157.800, "price_high": 157.810, "direction": "bullish"},
                ]
            },
        },
    )
    assert snapped_output["entry_condition"]["price"] == 157.850
    assert not any("anchored Entry" in s for s in snaps)


def test_canonical_tier0_anchor_and_context_builder_calibration() -> None:
    """Verify CANONICAL_TIER0_ANCHOR, ContextBuilder, AdjudicationVerifier, and jev_primitives calibration."""
    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR
    assert "unanimous specialist consensus" not in anchor.lower()
    assert "Institutional Synergy" in anchor
    assert "1.25x-2.0x H4 ATR" in anchor

    builder = ContextBuilder({})
    user_msg = builder._build_user_message("EURUSD")
    trimmed_msg = builder._build_trimmed_user_message("EURUSD")

    for text in (SYSTEM_PROMPT_STATIC, user_msg, trimmed_msg):
        assert "CROWDED_UNANIMOUS_EXHAUSTION" in text
        assert "pos <= 0.45" in text
        assert "pos >= 0.55" in text
        assert "72.7%" in text
        assert "80.0%" in text

    assert "UNCROWDED_INSTITUTIONAL_SYNERGY" in ADJUDICATION_SYSTEM_PROMPT
    assert "CROWDED_TECH_SENT_TRAP_VS_MACRO" in ADJUDICATION_SYSTEM_PROMPT

    jev_q = build_adjudication_questions()
    verdict_q = jev_q["verdict"]
    assert "UNCROWDED_INSTITUTIONAL_SYNERGY" in verdict_q.instructions
    assert "CROWDED_TECH_SENT_TRAP_VS_MACRO" in verdict_q.instructions
