# ==============================================================================
# File: tests/data_sources/test_bond_yields.py
# ==============================================================================

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select

from database.models import BondYieldData
from data_sources.bond_yields_fetcher import BondYieldFetcher


@pytest.mark.asyncio
async def test_bond_yield_ecb_fetch(db_session):
    """Memastikan BondYieldFetcher dapat mengunduh dari ECB Data Portal dan menyimpan DE_10Y ke DB."""
    fetcher = BondYieldFetcher(db_session)

    dummy_csv = (
        "KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-08-25,2.35\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-08-26,2.38\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-08-27,2.41\n"
    )

    with patch("data_sources.bond_yields_fetcher.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = dummy_csv
        with patch("data_sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields", new_callable=AsyncMock, return_value={}):
            results = await fetcher.fetch()
            assert results.get("DE_10Y") == 3

    # Verifikasi tersimpan di DB
    rows = (await db_session.execute(
        select(BondYieldData).where(BondYieldData.country_tenor == "DE_10Y").order_by(BondYieldData.date.asc())
    )).scalars().all()
    assert len(rows) == 3
    assert rows[0].yield_percent == 2.35
    assert rows[2].yield_percent == 2.41


@pytest.mark.asyncio
async def test_bond_yield_fred_fetch(db_session):
    """Memastikan BondYieldFetcher dapat mengambil UK, JP, AU dari FRED API saat fallback."""
    fetcher = BondYieldFetcher(db_session, fred_api_key="test_key")

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, return_value=1):
        with patch("data_sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields", new_callable=AsyncMock, return_value={}):
            with patch.object(fetcher, "_fetch_fred_bond_series", new_callable=AsyncMock) as mock_fred:
                mock_fred.return_value = 2
                results = await fetcher.fetch()
                assert results.get("DE_10Y") == 1
                assert results.get("UK_10Y") == 2
                assert results.get("JP_10Y") == 2
                assert results.get("AU_10Y") == 2


@pytest.mark.asyncio
async def test_bond_yield_cbw_priority_over_fred(db_session):
    """Memastikan CentralBankWatch menjadi sumber primer sebelum memanggil FRED."""
    fetcher = BondYieldFetcher(db_session, fred_api_key="test_key")

    cbw_mock_data = {
        "UK_10Y": 4.25, "UK_2Y": 4.10,
        "JP_10Y": 1.15, "JP_2Y": 0.55,
        "AU_10Y": 4.05, "AU_2Y": 3.75,
    }

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, return_value=1):
        with patch("data_sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields", new_callable=AsyncMock, return_value=cbw_mock_data):
            with patch.object(fetcher, "_fetch_fred_bond_series", new_callable=AsyncMock) as mock_fred:
                results = await fetcher.fetch()
                assert results.get("UK_10Y") == 1
                assert results.get("UK_2Y") == 1
                assert results.get("JP_10Y") == 1
                assert results.get("AU_10Y") == 1
                # FRED tidak dipanggil karena CBW sudah mengisi
                mock_fred.assert_not_called()


@pytest.mark.asyncio
async def test_bond_yield_deduplication(db_session):
    """Memastikan tidak terjadi duplikasi saat data tanggal yang sama diambil kembali."""
    fetcher = BondYieldFetcher(db_session)

    dummy_csv = (
        "KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-08-27,2.41\n"
    )

    with patch("data_sources.bond_yields_fetcher.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = dummy_csv
        first_save = await fetcher._fetch_ecb_yield()
        assert first_save == 1

        second_save = await fetcher._fetch_ecb_yield()
        assert second_save == 0  # Deduplicated

    rows = (await db_session.execute(
        select(BondYieldData).where(BondYieldData.country_tenor == "DE_10Y")
    )).scalars().all()
    assert len(rows) == 1

