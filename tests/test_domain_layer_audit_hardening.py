"""
Unit and integration tests for Domain Layer audit hardening.
Covers F-24, F-27, F-28, F-29.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from monika.domain.execution.broker_plugin import InstrumentSpec
from monika.domain.indicators.pattern_similarity.context_verifier import PatternContextVerifier
from monika.domain.risk.crypto_audit_ledger import CryptoAuditLedger, LedgerCorruptionError
from monika.domain.risk.portfolio_optimizer import PortfolioOptimizer


def test_instrument_spec_broker_plugin_defaults():
    """Verify InstrumentSpec dynamically resolves accurate contract and pip sizes (F-27)."""
    gold = InstrumentSpec(symbol="XAUUSD")
    assert gold.pip_size == 0.01
    assert gold.contract_size == 100.0

    btc = InstrumentSpec(symbol="BTCUSD")
    assert btc.contract_size == 1.0

    fx = InstrumentSpec(symbol="EURUSD")
    assert fx.pip_size == 0.0001
    assert fx.contract_size == 100000.0


def test_portfolio_optimizer_zero_volatility():
    """Verify flat/frozen assets with zero volatility do not absorb 99.88% weight (F-29)."""
    symbols = ["ACTIVE_ASSET", "FROZEN_ASSET"]
    expected_returns = np.array([0.10, 0.00])
    # Covariance: ACTIVE has variance 0.04 (vol 0.20), FROZEN has variance 0.0
    cov_matrix = np.array([[0.04, 0.00], [0.00, 0.00]])

    opt = PortfolioOptimizer(symbols=symbols, cov_matrix=cov_matrix, expected_returns=expected_returns)
    res = opt.solve_equal_volatility()

    assert res.converged is True
    # Active asset should receive all or majority weight, frozen asset receives 0.0
    assert res.weights["ACTIVE_ASSET"] == 1.0
    assert res.weights["FROZEN_ASSET"] == 0.0


def test_crypto_audit_ledger_corrupted_disk_rejection(tmp_path):
    """Verify CryptoAuditLedger rejects appending if on-disk file was tampered with (F-28)."""
    ledger_file = tmp_path / "test_audit.jsonl"
    ledger = CryptoAuditLedger(ledger_file)

    # Append valid initial record
    rec1 = ledger.append("INIT", {"status": "ok"})
    assert rec1.seq == 0

    # Tamper with the ledger file on disk
    with open(ledger_file, "a", encoding="utf-8") as f:
        f.write('{"seq": 999, "corrupt": true}\n')

    # Next append must detect on-disk corruption and raise LedgerCorruptionError
    with pytest.raises(LedgerCorruptionError):
        ledger.append("NEXT_ACTION", {"data": 123})


@pytest.mark.asyncio
async def test_context_verifier_read_only_session_guard():
    """Verify PatternContextVerifier safely handles read-only session commit (F-24)."""
    verifier = PatternContextVerifier()

    # Session with is_readonly flag
    mock_session = MagicMock()
    mock_session.is_readonly = True
    mock_session.commit = AsyncMock()

    # Mock web search service so no external network call happens
    mock_search_svc = MagicMock()
    mock_search_svc.search = AsyncMock(return_value={"results": [{"title": "Fed Rate Cut Signals Historical Policy"}]})

    with patch(
        "monika.infrastructure.data_ingestion.sources.web_search.get_web_search_service",
        return_value=mock_search_svc,
    ):
        res = await verifier._search_and_cache_chronicle(
            session=mock_session,
            symbol="EURUSD",
            match_dt=MagicMock(strftime=lambda fmt: "January 2020"),
        )
        assert "Fed Rate Cut" in res
        # commit must not be called because session.is_readonly is True
        assert mock_session.commit.await_count == 0
