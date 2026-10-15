import pytest
from monika.domain.execution.verification_engine import EvidenceFirstVerifier


@pytest.mark.asyncio
async def test_pre_trade_assertions_valid():
    verifier = EvidenceFirstVerifier()
    valid_signal = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0920,
        "confidence": 0.75,
        "confluence_score": 9,
        "priced_in_score": 4,
        "invalidation": "Invalid if D1 candle closes below 1.0820",
        "key_evidence": ["D1+H4 aligned", "Unmitigated FVG at 1.0845"],
        "quote_age_seconds": 15,
    }
    passed, violations = await verifier.pre_trade_assertions(valid_signal)
    assert passed is True
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_pre_trade_assertions_invalid_sl():
    verifier = EvidenceFirstVerifier()
    # BUY signal where SL is higher than entry (impossible)
    bad_signal = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0890,
        "take_profit": 1.0950,
        "confidence": 0.75,
        "confluence_score": 8,
        "priced_in_score": 3,
        "invalidation": "Thesis invalid below support",
        "key_evidence": ["SMC zone", "DXY weak"],
    }
    passed, violations = await verifier.pre_trade_assertions(bad_signal)
    assert passed is False
    assert any("ASSERT_3" in v for v in violations)


@pytest.mark.asyncio
async def test_pre_trade_assertions_low_rr():
    verifier = EvidenceFirstVerifier()
    # R:R < 1.3
    bad_rr_signal = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0800,  # 50 pips SL
        "take_profit": 1.0870,  # 20 pips TP -> R:R 0.4
        "confidence": 0.75,
        "confluence_score": 8,
        "priced_in_score": 3,
        "invalidation": "Thesis invalid below support",
        "key_evidence": ["SMC zone", "DXY weak"],
    }
    passed, violations = await verifier.pre_trade_assertions(bad_rr_signal)
    assert passed is False
    assert any("ASSERT_4" in v for v in violations)


@pytest.mark.asyncio
async def test_post_execution_reconciliation_mock():
    verifier = EvidenceFirstVerifier()
    order_result = {"ticket": 987654, "requested_price": 1.0850}
    report = await verifier.post_execution_reconciliation(order_result, mt5_client=None)
    assert report["verified"] is True
    assert report["ticket"] == 987654


def test_record_evidence_payload_hash():
    import hashlib, json

    verifier = EvidenceFirstVerifier()
    decision_payload = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0920,
    }
    rec = verifier.record_evidence(decision_payload)
    assert "payload_hash" in rec
    expected_hash = hashlib.sha256(json.dumps(decision_payload, sort_keys=True, default=str).encode()).hexdigest()
    assert rec["payload_hash"] == expected_hash


@pytest.mark.asyncio
async def test_pre_trade_assertions_edge_registry_exempt_assert_7():
    verifier = EvidenceFirstVerifier()
    # Quantitative edge strategy signal without LLM confluence score
    edge_signal = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0920,
        "confidence": 0.45,
        "confluence_score": 0,
        "priced_in_score": 0,
        "invalidation": "Strategy exit: smc_fvg",
        "key_evidence": ["FVG zone mitigation", "R:R 2.33"],
        "quote_age_seconds": 10,
        "decision_source": "edge_registry",
        "source_strategy_id": "smc_fvg",
    }
    passed, violations = await verifier.pre_trade_assertions(edge_signal)
    assert passed is True
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_pre_trade_assertions_edge_registry_low_confidence():
    verifier = EvidenceFirstVerifier()
    edge_signal = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0820,
        "take_profit": 1.0920,
        "confidence": 0.25,  # below 0.30 floor
        "confluence_score": 0,
        "priced_in_score": 0,
        "invalidation": "Strategy exit: smc_fvg",
        "key_evidence": ["FVG zone mitigation", "R:R 2.33"],
        "decision_source": "edge_registry",
        "source_strategy_id": "smc_fvg",
    }
    passed, violations = await verifier.pre_trade_assertions(edge_signal)
    assert passed is False
    assert any("ASSERT_6" in v for v in violations)
    assert not any("ASSERT_7" in v for v in violations)
