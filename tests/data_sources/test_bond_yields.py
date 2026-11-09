# ==============================================================================
# File: tests/data_sources/test_bond_yields.py
# ==============================================================================

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select

from monika.infrastructure.database.models import BondYieldData
from monika.infrastructure.data_ingestion.sources.bond_yields_fetcher import BondYieldFetcher


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

    with patch(
        "monika.infrastructure.data_ingestion.sources.bond_yields_fetcher.fetch_with_retry", new_callable=AsyncMock
    ) as mock_http:
        mock_http.return_value = dummy_csv
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value={},
        ):
            results = await fetcher.fetch()
            assert results.get("DE_10Y") == 3

    # Verifikasi tersimpan di DB
    rows = (
        (
            await db_session.execute(
                select(BondYieldData).where(BondYieldData.country_tenor == "DE_10Y").order_by(BondYieldData.date.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert rows[0].yield_percent == 2.35
    assert rows[2].yield_percent == 2.41


@pytest.mark.asyncio
async def test_bond_yield_fred_fetch(db_session):
    """Memastikan BondYieldFetcher dapat mengambil UK, JP, AU dari FRED API saat fallback."""
    fetcher = BondYieldFetcher(db_session, fred_api_key="test_key")

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, return_value=1):
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value={},
        ):
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
        "UK_10Y": 4.25,
        "UK_2Y": 4.10,
        "JP_10Y": 1.15,
        "JP_2Y": 0.55,
        "AU_10Y": 4.05,
        "AU_2Y": 3.75,
    }

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, return_value=1):
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value=cbw_mock_data,
        ):
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

    with patch(
        "monika.infrastructure.data_ingestion.sources.bond_yields_fetcher.fetch_with_retry", new_callable=AsyncMock
    ) as mock_http:
        mock_http.return_value = dummy_csv
        first_save = await fetcher._fetch_ecb_yield()
        assert first_save == 1

        second_save = await fetcher._fetch_ecb_yield()
        assert second_save == 0  # Deduplicated

    rows = (
        (await db_session.execute(select(BondYieldData).where(BondYieldData.country_tenor == "DE_10Y"))).scalars().all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_bond_yield_ecb_timeout_fallback_to_cbw(db_session):
    """Memastikan saat ECB Data Portal timeout (seperti insiden 35s), CBW langsung mengisi DE_10Y dan DE_2Y."""
    fetcher = BondYieldFetcher(db_session)

    cbw_mock_data = {
        "DE_10Y": 2.45,
        "DE_2Y": 2.10,
        "UK_10Y": 4.25,
        "UK_2Y": 4.10,
        "JP_10Y": 1.15,
        "JP_2Y": 0.55,
        "AU_10Y": 4.05,
        "AU_2Y": 3.75,
    }

    # Simulasikan ECB gagal dengan TimeoutError / None
    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, side_effect=TimeoutError("ECB Timeout")):
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value=cbw_mock_data,
        ):
            results = await fetcher.fetch()

            # Verifikasi semua 8 tenor berhasil diisi via CBW fallback
            assert results.get("DE_10Y") == 1
            assert results.get("DE_2Y") == 1
            assert results.get("UK_10Y") == 1
            assert results.get("UK_2Y") == 1
            assert results.get("JP_10Y") == 1
            assert results.get("JP_2Y") == 1
            assert results.get("AU_10Y") == 1
            assert results.get("AU_2Y") == 1


@pytest.mark.asyncio
async def test_bond_yield_ecb_500_504_error_fallback(db_session):
    """Memastikan saat ECB mengembalikan HTTP 500 / 504 (-1), pipeline tidak crash dan jatuh ke CBW."""
    fetcher = BondYieldFetcher(db_session)

    cbw_mock_data = {
        "DE_10Y": 2.50,
        "DE_2Y": 2.20,
    }

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, return_value=-1):
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value=cbw_mock_data,
        ):
            results = await fetcher.fetch()
            assert results.get("DE_10Y") == 1
            assert results.get("DE_2Y") == 1


@pytest.mark.asyncio
async def test_bond_yield_ecb_budget_protection(db_session):
    """Memastikan proteksi budget membatalkan ECB jika menggantung, tanpa membunuh CBW & FRED."""
    fetcher = BondYieldFetcher(db_session)

    cbw_mock_data = {
        "DE_10Y": 2.30,
        "DE_2Y": 2.05,
        "UK_10Y": 4.15,
    }

    # Simulasikan TimeoutError saat budget ECB habis
    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock, side_effect=TimeoutError()):
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value=cbw_mock_data,
        ):
            results = await fetcher.fetch()
            # Karena ECB dibatalkan oleh timeout, CBW mengisi tanpa hambatan
            assert results.get("DE_10Y") == 1
            assert results.get("DE_2Y") == 1
            assert results.get("UK_10Y") == 1


@pytest.mark.asyncio
async def test_bond_yield_ecb_combined_multi_key_fetch(db_session):
    """Memastikan single request SDMX gabungan (SR_10Y + SR_2Y) mempopulasi DE_10Y dan DE_2Y sekaligus."""
    fetcher = BondYieldFetcher(db_session)
    BondYieldFetcher._last_ecb_fetch_ts = 0.0

    dummy_combined_csv = (
        "KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-11-04,3.34\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-11-05,3.29\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_2Y,2026-11-04,3.00\n"
        "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_2Y,2026-11-05,2.96\n"
    )

    with patch(
        "monika.infrastructure.data_ingestion.sources.bond_yields_fetcher.fetch_with_retry", new_callable=AsyncMock
    ) as mock_http:
        mock_http.return_value = dummy_combined_csv
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value={},
        ):
            results = await fetcher.fetch()
            assert results.get("DE_10Y") == 2
            assert results.get("DE_2Y") == 2

    # Verifikasi kedua tenor tersimpan di DB
    de10_rows = (
        (await db_session.execute(select(BondYieldData).where(BondYieldData.country_tenor == "DE_10Y"))).scalars().all()
    )
    de2_rows = (
        (await db_session.execute(select(BondYieldData).where(BondYieldData.country_tenor == "DE_2Y"))).scalars().all()
    )
    assert len(de10_rows) == 2
    assert len(de2_rows) == 2


@pytest.mark.asyncio
async def test_bond_yield_cache_skipping(db_session):
    """Memastikan fetcher melewati remote call ke ECB jika data masih fresh dalam cache TTL."""
    import time

    fetcher = BondYieldFetcher(db_session)
    BondYieldFetcher._last_ecb_fetch_ts = time.time()

    with patch.object(fetcher, "_fetch_ecb_yield", new_callable=AsyncMock) as mock_ecb:
        with patch(
            "monika.infrastructure.data_ingestion.sources.central_bank_watch.CentralBankWatchFetcher.fetch_sovereign_yields",
            new_callable=AsyncMock,
            return_value={},
        ):
            results = await fetcher.fetch(cache_ttl_sec=3600.0)
            # Remote ECB fetch dilewati
            mock_ecb.assert_not_called()
            assert results.get("DE_10Y") == 1
            assert results.get("DE_2Y") == 1

    BondYieldFetcher._last_ecb_fetch_ts = 0.0
