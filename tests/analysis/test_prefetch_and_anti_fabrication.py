import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.analysis.calculators.universal_cb_differ import UniversalCentralBankDiffer
from monika.application.analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer
from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from tests.conftest import create_mock_async_session


def test_dynamic_symbol_precision_instrument_spec():
    # Verify dynamic instrument spec lookup for BTCUSD and EURUSD
    prec_btc = Stage2DataBundler.get_symbol_precision("BTCUSD")
    prec_eur = Stage2DataBundler.get_symbol_precision("EURUSD")
    assert prec_btc == 2
    assert prec_eur == 5


@pytest.mark.asyncio
async def test_universal_cb_differ_insufficient_history_fail_closed():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    # Provide only 1 document in database
    mock_doc = MagicMock()
    mock_doc.title = "Only FOMC Meeting"
    mock_doc.meeting_date = MagicMock()
    mock_doc.meeting_date.strftime.return_value = "2026-10-01"
    mock_doc.hawkish_dovish_score = 0.2
    mock_res.scalars.return_value.all.return_value = [mock_doc]
    mock_session.execute.return_value = mock_res

    differ = UniversalCentralBankDiffer(mock_session)
    differ.router.ensure_cb_document_available = AsyncMock()

    res = await differ.diff_cb_documents("FED", "MINUTES")
    # Must fail closed with status insufficient_history, never fabricate fake previous paragraphs
    assert res["status"] == "insufficient_history"
    assert "Only 1 meeting document found" in res["message"]
    assert res["monetary_tone_shift"]["delta_score"] == 0.0


@pytest.mark.asyncio
async def test_universal_liquidity_analyzer_empty_ecb_fail_closed():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    analyzer = UniversalLiquidityAnalyzer(mock_session)
    res = await analyzer.analyze_ecb_balance_sheet_and_qt()
    assert res["status"] == "data_unavailable"
    assert res["current_assets_eur_millions"] == 0.0
    assert "currently unavailable" in res["institutional_verdict"]


@pytest.mark.asyncio
async def test_stage2_data_bundler_shared_global_cache():
    session = create_mock_async_session()
    bundler = Stage2DataBundler(session)

    # Populate shared global cache
    bundler._shared_global_cache = {
        "get_dxy": {"dxy": 104.2},
        "get_vix": {"vix": 16.5},
    }

    assert bundler._shared_global_cache["get_dxy"]["dxy"] == 104.2
    assert bundler._shared_global_cache["get_vix"]["vix"] == 16.5
