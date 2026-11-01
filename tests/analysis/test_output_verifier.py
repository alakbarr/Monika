import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from monika.application.analysis.validators.output_verifier import OutputVerifier


@pytest.mark.asyncio
async def test_output_verifier_valid_buy():
    verifier = OutputVerifier()
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3,
        "reevaluation_trigger": {"type": "price_level", "price": 1.0940},
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={},
    )
    assert failures == []


@pytest.mark.asyncio
async def test_output_verifier_invalid_direction():
    verifier = OutputVerifier()
    # BUY with SL > Entry
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.1050,
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3,
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={},
    )
    assert any("BUY direction error" in f for f in failures)


@pytest.mark.asyncio
async def test_output_verifier_insufficient_rr():
    verifier = OutputVerifier()
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0950,  # 50 pips SL
        "take_profit": 1.1050,  # 50 pips TP -> R:R 1.0 < 1.3
        "confluence_score": 9,
        "priced_in_score": 3,
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={},
    )
    assert any("R:R" in f for f in failures)


@pytest.mark.asyncio
async def test_output_verifier_self_correction():
    verifier = OutputVerifier()
    # Initial invalid payload
    bad_payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.1050,  # bad SL
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3,
    }
    good_payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3,
    }

    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(return_value=good_payload)

    verified, corrections = await verifier.verify_and_correct(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        raw_output=bad_payload,
        context_data={},
        client=mock_client,
        max_retries=2,
    )

    assert verified["stop_loss"] == 1.0950
    assert len(corrections) == 1
    assert "Attempt 1" in corrections[0]


@pytest.mark.asyncio
async def test_output_verifier_sl_widening_snapping():
    verifier = OutputVerifier()
    # BUY entry 1.1000, but SL is 1.0995 (only 0.0005 away, when ATR is 0.0020 -> min SL distance is 0.0020)
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0995,
        "take_profit": 1.1060,
    }
    context_data = {"get_atr": 0.0020}

    snapped, snaps = verifier._apply_deterministic_math_snapping(
        output=payload,
        failures=[],
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        context_data=context_data,
    )

    assert snapped["stop_loss"] == 1.0980  # 1.1000 - 0.0020
    assert any("widened BUY SL" in s for s in snaps)


@pytest.mark.asyncio
async def test_output_verifier_snapping_precision_and_direction_invariant():
    verifier = OutputVerifier()
    # XAUUSD: spec digits = 2
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 2650.1234},
        "stop_loss": 2645.5678,
        "take_profit": 2652.0000,  # poor RR: 1.878 / 4.5556 < 1.3
    }
    snapped, snaps = verifier._apply_deterministic_math_snapping(
        output=payload,
        failures=["R:R ratio 0.41 is below minimum 1.3"],
        settings={"trading": {"risk": {"min_rr_ratio": 1.5}}},
        symbol="XAUUSD",
        context_data={"get_atr": 10.0},
    )
    # Digits must be 2 for XAUUSD
    assert snapped["stop_loss"] == 2640.12  # widened to 1.0x ATR = 10.0
    assert snapped["take_profit"] == 2665.12  # 2650.12 + 10.0 * 1.5
    assert snapped["entry_condition"]["price"] == 2650.12
    # Invariant: entry > stop_loss and take_profit > entry
    assert snapped["entry_condition"]["price"] > snapped["stop_loss"]
    assert snapped["take_profit"] > snapped["entry_condition"]["price"]


def test_output_verifier_extract_atr_variants():
    verifier = OutputVerifier()
    assert verifier._extract_atr({"get_atr_H4": {"atr": 0.0025}}) == pytest.approx(0.0025)
    assert verifier._extract_atr({"get_atr_H1": 0.0018}) == pytest.approx(0.0018)
    assert verifier._extract_atr({"ATR_14": {"value": 0.0025}}) == pytest.approx(0.0025)
    assert verifier._extract_atr(
        {"get_technical_indicators_H4": {"indicators": {"ATR_14": {"value": 0.0025}}}}
    ) == pytest.approx(0.0025)
    assert verifier._extract_atr({"precomputed_invariants": {"atr_14": 0.0031}}) == pytest.approx(0.0031)


@pytest.mark.asyncio
async def test_output_verifier_market_entry_price_at_analysis_fallback():
    verifier = OutputVerifier()
    payload = {
        "decision": "buy",
        "entry_condition": {"type": "market", "price": None},
        "price_at_analysis": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1080,
        "confluence_score": 9,
        "priced_in_score": 3,
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.5}}},
        symbol="EURUSD",
        output=payload,
        context_data={"get_smc_zones_H4": {"fair_value_gaps": [{"gap_low": 1.0995, "gap_high": 1.1005}]}},
    )
    assert failures == []


@pytest.mark.asyncio
async def test_output_verifier_adr_allows_1_05x_atr_stop(monkeypatch):
    verifier = OutputVerifier()

    # Suppose ATR = 0.0020 (20 pips), so 1.05x ATR = 0.0021 (21 pips), TP = 1.55x SL = 0.003255.
    # Suppose raw 35% ADR target_sl_max_distance is tight (0.0015 < 1.0x ATR).
    async def mock_adr_ctx(session, symbol, settings):
        return {
            "adr": 0.0043,
            "target_sl_min_distance": 0.0008,
            "target_sl_max_distance": 0.0015,
            "target_tp_min_distance": 0.0022,
            "target_tp_max_distance": 0.0034,
        }

    monkeypatch.setattr(
        "monika.application.analysis.validators.output_verifier.compute_daily_range_context",
        mock_adr_ctx,
    )

    payload = {
        "decision": "buy",
        "entry_condition": {"type": "market", "price": None},
        "price_at_analysis": 1.25000,
        "stop_loss": 1.24790,  # 0.00210 = 1.05x ATR
        "take_profit": 1.25326,  # 0.00326 = 1.55x SL
        "confluence_score": 10,
        "priced_in_score": 3,
    }
    failures = await verifier._run_all_checks(
        session=MagicMock(),
        settings={"trading": {"risk": {"min_rr_ratio": 1.5}}},
        symbol="GBPUSD",
        output=payload,
        context_data={
            "get_atr_H4": {"atr": 0.0020},
            "get_support_resistance": {"sr_zones": [{"price_low": 1.2498, "price_high": 1.2502}]},
        },
    )
    assert failures == []
