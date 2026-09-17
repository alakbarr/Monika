import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from analysis.validators.output_verifier import OutputVerifier

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
        "reevaluation_trigger": {"type": "price_level", "price": 1.0940}
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={}
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
        "priced_in_score": 3
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={}
    )
    assert any("BUY direction error" in f for f in failures)

@pytest.mark.asyncio
async def test_output_verifier_insufficient_rr():
    verifier = OutputVerifier()
    payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0950, # 50 pips SL
        "take_profit": 1.1050, # 50 pips TP -> R:R 1.0 < 1.3
        "confluence_score": 9,
        "priced_in_score": 3
    }
    failures = await verifier._run_all_checks(
        session=None,
        settings={"trading": {"risk": {"min_rr_ratio": 1.3}}},
        symbol="EURUSD",
        output=payload,
        context_data={}
    )
    assert any("R:R" in f for f in failures)

@pytest.mark.asyncio
async def test_output_verifier_self_correction():
    verifier = OutputVerifier()
    # Initial invalid payload
    bad_payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.1050, # bad SL
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3
    }
    good_payload = {
        "decision": "buy",
        "entry_condition": {"price": 1.1000},
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "confluence_score": 9,
        "priced_in_score": 3
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
        max_retries=2
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
