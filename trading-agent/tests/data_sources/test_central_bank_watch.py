# ==============================================================================
# File: tests/data_sources/test_central_bank_watch.py
# ==============================================================================

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from database.models import CentralBankRateExpectation, BondYieldData, InterestRate
from data_sources.central_bank_watch import CentralBankWatchFetcher


SAMPLE_CBW_HOME_HTML = """
<!DOCTYPE html>
<html>
<body>
  <div class="cb-card fed">
    <h3>Federal Reserve</h3>
    <p class="current-rate">Current Rate: 5.25% - 5.50%</p>
    <p class="cb-meeting-date">May 6, 2026</p>
    <div class="prob-display">
      <div class="prob-item">Hike: 5.0%</div>
      <div class="prob-item">No Change: 85.0%</div>
      <div class="prob-item">Cut: 10.0%</div>
    </div>
  </div>

  <div class="cb-card ecb">
    <h3>European Central Bank</h3>
    <p class="current-rate">Deposit Facility Rate: 3.75%</p>
    <p class="cb-meeting-date">June 11, 2026</p>
    <div class="prob-display">
      <div class="prob-item">Hike: 0.0%</div>
      <div class="prob-item">Hold: 20.0%</div>
      <div class="prob-item">Cut: 80.0%</div>
    </div>
  </div>

  <div class="cb-card boe">
    <h3>Bank of England</h3>
    <p class="current-rate">Bank Rate: 4.75%</p>
    <p class="cb-meeting-date">May 7, 2026</p>
    <div class="prob-display">
      <div class="prob-item">Hike: 0.0%</div>
      <div class="prob-item">Hold: 60.0%</div>
      <div class="prob-item">Cut: 40.0%</div>
    </div>
  </div>

  <div class="cb-card boj">
    <h3>Bank of Japan</h3>
    <p class="current-rate">Policy Rate: 0.50%</p>
    <p class="cb-meeting-date">April 30, 2026</p>
    <div class="prob-display">
      <div class="prob-item">Hike: 70.0%</div>
      <div class="prob-item">Hold: 30.0%</div>
      <div class="prob-item">Cut: 0.0%</div>
    </div>
  </div>

  <div class="cb-card rba">
    <h3>Reserve Bank of Australia</h3>
    <p class="current-rate">Cash Rate Target: 4.35%</p>
    <p class="cb-meeting-date">May 19, 2026</p>
    <div class="prob-display">
      <div class="prob-item">Hike: 10.0%</div>
      <div class="prob-item">Hold: 75.0%</div>
      <div class="prob-item">Cut: 15.0%</div>
    </div>
  </div>
</body>
</html>
"""

SAMPLE_CBW_YIELD_HTML = """
<!DOCTYPE html>
<html>
<body>
  <table>
    <thead>
      <tr>
        <th>Country</th><th>1M</th><th>1Y</th><th>2Y</th><th>10Y</th><th>30Y</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>United States</td><td>4.50</td><td>4.20</td><td>4.12</td><td>4.35</td><td>4.55</td>
      </tr>
      <tr>
        <td>Germany (Eurozone)</td><td>3.00</td><td>2.60</td><td>2.45</td><td>2.55</td><td>2.75</td>
      </tr>
      <tr>
        <td>United Kingdom</td><td>4.80</td><td>4.50</td><td>4.25</td><td>4.40</td><td>4.70</td>
      </tr>
      <tr>
        <td>Australia</td><td>4.10</td><td>3.95</td><td>3.85</td><td>4.15</td><td>4.45</td>
      </tr>
      <tr>
        <td>Japan</td><td>0.10</td><td>0.30</td><td>0.65</td><td>1.25</td><td>1.85</td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_central_bank_watch_fetch_expectations(db_session):
    """Verifikasi parser HTML kartu bank sentral dan penyimpanan ke tabel CentralBankRateExpectation."""
    # Siapkan data InterestRate awal untuk FED
    fed_rate = InterestRate(
        bank="FED",
        rate_percent=5.50,
        effective_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
        next_meeting_date=None,
    )
    db_session.add(fed_rate)
    await db_session.commit()

    fetcher = CentralBankWatchFetcher(db_session)

    with patch("data_sources.central_bank_watch.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = SAMPLE_CBW_HOME_HTML
        res = await fetcher.fetch_expectations()

        assert "FED" in res
        assert "ECB" in res
        assert "BOE" in res
        assert "BOJ" in res
        assert "RBA" in res

        # Cek data Fed
        fed_data = res["FED"]
        assert fed_data["prob_hike"] == 5.0
        assert fed_data["prob_hold"] == 85.0
        assert fed_data["prob_cut"] == 10.0
        assert "May 6, 2026" in fed_data["meeting_date"]

        # Cek data BoJ
        boj_data = res["BOJ"]
        assert boj_data["prob_hike"] == 70.0
        assert boj_data["prob_hold"] == 30.0
        assert boj_data["prob_cut"] == 0.0

    # Cek record tersimpan di database
    rows = (await db_session.execute(
        select(CentralBankRateExpectation).order_by(CentralBankRateExpectation.bank.asc())
    )).scalars().all()
    assert len(rows) == 5

    # Cek bahwa next_meeting_date pada fed_rate diperbarui
    await db_session.refresh(fed_rate)
    assert fed_rate.next_meeting_date is not None
    assert fed_rate.next_meeting_date.year == 2026
    assert fed_rate.next_meeting_date.month == 5


@pytest.mark.asyncio
async def test_central_bank_watch_fetch_sovereign_yields(db_session):
    """Verifikasi parser tabel sovereign yield 2Y dan 10Y dan upsert ke BondYieldData."""
    fetcher = CentralBankWatchFetcher(db_session)

    with patch("data_sources.central_bank_watch.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = SAMPLE_CBW_YIELD_HTML
        yields = await fetcher.fetch_sovereign_yields()

        assert yields.get("US_2Y") == 4.12
        assert yields.get("US_10Y") == 4.35
        assert yields.get("DE_2Y") == 2.45
        assert yields.get("DE_10Y") == 2.55
        assert yields.get("UK_2Y") == 4.25
        assert yields.get("UK_10Y") == 4.40
        assert yields.get("AU_2Y") == 3.85
        assert yields.get("AU_10Y") == 4.15
        assert yields.get("JP_2Y") == 0.65
        assert yields.get("JP_10Y") == 1.25

    # Cek tersimpan di DB
    rows = (await db_session.execute(
        select(BondYieldData)
    )).scalars().all()
    assert len(rows) == 10

    # Uji idempotency / upsert saat di-fetch ulang
    with patch("data_sources.central_bank_watch.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = SAMPLE_CBW_YIELD_HTML
        await fetcher.fetch_sovereign_yields()

    rows_after = (await db_session.execute(
        select(BondYieldData)
    )).scalars().all()
    assert len(rows_after) == 10


@pytest.mark.asyncio
async def test_central_bank_watch_fetch_all(db_session):
    """Verifikasi fetch_all menggabungkan expectations dan yields."""
    fetcher = CentralBankWatchFetcher(db_session)

    with patch.object(fetcher, "fetch_expectations", new_callable=AsyncMock) as mock_exp:
        mock_exp.return_value = {"FED": {"prob_hold": 90.0}}
        with patch.object(fetcher, "fetch_sovereign_yields", new_callable=AsyncMock) as mock_yld:
            mock_yld.return_value = {"DE_2Y": 2.50}

            combined = await fetcher.fetch_all()
            assert "expectations" in combined
            assert "yields" in combined
            assert combined["expectations"]["FED"]["prob_hold"] == 90.0
            assert combined["yields"]["DE_2Y"] == 2.50


@pytest.mark.asyncio
async def test_central_bank_watch_error_handling(db_session):
    """Verifikasi penanganan graceful jika respons HTTP None atau kosong."""
    fetcher = CentralBankWatchFetcher(db_session)

    with patch("data_sources.central_bank_watch.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = None
        exp = await fetcher.fetch_expectations()
        assert exp == {}

        yld = await fetcher.fetch_sovereign_yields()
        assert yld == {}


@pytest.mark.asyncio
async def test_central_bank_watch_card_class_matcher(db_session):
    """Verifikasi bahwa class_ filter lambda menangani class None, kosong, dan majemuk dengan benar."""
    from bs4 import BeautifulSoup

    html = """
    <div>
        <div>No class div</div>
        <div class="">Empty class div</div>
        <div class="other-card">Other card</div>
        <div class="cb-card fed-card">
            <p class="cb-meeting-date">July 29, 2026</p>
            <p class="current-rate">5.25%</p>
            <div class="prob-display">
                <div class="prob-item">Hike 0%</div>
                <div class="prob-item">Hold 85%</div>
                <div class="prob-item">Cut 15%</div>
            </div>
        </div>
    </div>
    """
    fetcher = CentralBankWatchFetcher(db_session)
    with patch("data_sources.central_bank_watch.fetch_with_retry", new_callable=AsyncMock) as mock_http:
        mock_http.return_value = html
        res = await fetcher.fetch_expectations()
        assert "FED" in res
        assert res["FED"]["current_rate"] == 5.25
        assert res["FED"]["prob_hold"] == 85.0
        assert res["FED"]["prob_cut"] == 15.0
