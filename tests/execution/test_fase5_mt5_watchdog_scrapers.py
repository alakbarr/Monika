# ==============================================================================
# File: tests/execution/test_fase5_mt5_watchdog_scrapers.py
# Description: Unit tests for Phase 5 (MT5 Requote Retry, Pending In-Flight Rec,
#              Emergency Timeout Safety, Dialect-Agnostic Scraping, BI Rate Extraction)
# ==============================================================================

import asyncio
import json
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from monika.infrastructure.brokers.mt5_client import _close_position, MT5Client
from monika.application.execution.service.emergency_manager import EmergencyManagerMixin
from monika.infrastructure.data_ingestion.scrapers.macro.central_bank_doc_scraper import (
    CentralBankDocScraper,
)
from monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia import (
    BankIndonesiaFetcher,
)
from monika.infrastructure.database.models import CentralBankDocument, Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_mt5_close_position_requote_retry():
    """Verify _close_position retries with updated tick price on requote retcode (10004)."""
    with patch("MetaTrader5.positions_get") as mock_pos_get, \
         patch("MetaTrader5.symbol_info_tick") as mock_tick, \
         patch("MetaTrader5.symbol_info") as mock_sym, \
         patch("MetaTrader5.order_send") as mock_order_send:

        mock_pos = MagicMock()
        mock_pos.volume = 0.5
        mock_pos.symbol = "EURUSD"
        mock_pos.type = 0  # BUY -> close with SELL
        mock_pos.profit = 42.0
        mock_pos_get.return_value = [mock_pos]

        # Initial tick bid 1.1000, retry tick bid 1.0995
        tick1 = MagicMock(bid=1.1000, ask=1.1002)
        tick2 = MagicMock(bid=1.0995, ask=1.0997)
        mock_tick.side_effect = [tick1, tick2]

        sym_info = MagicMock(filling_mode=1, bid=1.1000, ask=1.1002)
        mock_sym.return_value = sym_info

        # First attempt: 10004 (requote), Second attempt: 10009 (done)
        res_requote = MagicMock(retcode=10004, comment="Requote")
        res_done = MagicMock(retcode=10009, price=1.0995, comment="Done")
        mock_order_send.side_effect = [res_requote, res_done]

        res = _close_position(ticket=1001, volume=0.5, comment="CloseTest")

        assert res["success"] is True
        assert res["price"] == 1.0995
        assert res["profit"] == 42.0
        assert res["retcode"] == 10009
        assert mock_order_send.call_count == 2

        # Verify second call used updated price
        second_request = mock_order_send.call_args_list[1][0][0]
        assert second_request["price"] == 1.0995


@pytest.mark.asyncio
async def test_mt5_in_flight_reconciliation_pending_orders():
    """Verify place_order timeout reconciliation checks active pending orders."""
    client = MT5Client()

    with patch.object(client, "ensure_connected", new=AsyncMock(return_value=True)), \
         patch.object(client, "_run", side_effect=asyncio.TimeoutError("MT5 Timeout")), \
         patch.object(client, "get_open_positions", new=AsyncMock(return_value=[])), \
         patch.object(client, "get_orders") as mock_get_orders:

        mock_pending_order = {
            "ticket": 88888,
            "symbol": "EURUSD",
            "direction": "buy",
            "volume": 0.2,
            "price_open": 1.0950,
            "time": datetime.now(timezone.utc),
            "sl": 1.0900,
            "tp": 1.1050,
        }
        mock_get_orders.return_value = [mock_pending_order]

        result = await client.place_order(
            symbol="EURUSD",
            direction="buy",
            volume=0.2,
            price=1.0950,
            order_type="LIMIT",
        )

        assert result["success"] is True
        assert result["ticket"] == 88888
        assert result["price"] == 1.0950
        assert result["recovered_from_timeout"] is True


@pytest.mark.asyncio
async def test_emergency_manager_close_position_timeout_safety():
    """Verify close_position_by_ticket times out safely after 15.0s without hanging event loop."""
    class DummyExecutionService(EmergencyManagerMixin):
        def __init__(self):
            self.broker_adapter = MagicMock()
            self._ticket_locks = {}

    service = DummyExecutionService()

    async def _hanging_close(*args, **kwargs):
        await asyncio.sleep(20.0)
        return {"success": True}

    service.broker_adapter.close_position = AsyncMock(side_effect=_hanging_close)

    with patch("monika.application.execution.service.emergency_manager.get_session") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # DB pos not yet closed
        mock_session.execute = AsyncMock(return_value=mock_res)
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        # Patch timeout to small value (0.1s) for fast unit test
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await service.close_position_by_ticket(ticket=777, requested_by="test")

            assert result["success"] is False
            assert "Liquidation timed out after 15.0s for ticket 777" in result["error"]


@pytest.mark.asyncio
async def test_central_bank_doc_scraper_sqlite_upsert():
    """Verify CentralBankDocumentScraper persists and upserts seamlessly on SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        scraper = CentralBankDocScraper(session=session)

        # 1. First insert
        rec1 = await scraper._persist_document_record(
            bank="ECB",
            doc_type="statement",
            meeting_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
            title="ECB Rate Decision",
            source_url="https://ecb.europa.eu/press/1",
            paragraphs=["Paragraph 1", "Paragraph 2"],
            tone_score=0.45,
            key_phrases=["inflation", "policy rate"],
        )
        assert rec1["bank"] == "ECB"
        assert rec1["title"] == "ECB Rate Decision"

        # 2. Upsert same (bank, doc_type, meeting_date) with updated score and paragraphs
        rec2 = await scraper._persist_document_record(
            bank="ECB",
            doc_type="statement",
            meeting_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
            title="ECB Rate Decision Updated",
            source_url="https://ecb.europa.eu/press/1",
            paragraphs=["Paragraph 1 updated", "Paragraph 2 updated"],
            tone_score=0.60,
            key_phrases=["hawkish shift"],
        )
        assert rec2["title"] == "ECB Rate Decision Updated"
        assert rec2["hawkish_dovish_score"] == 0.60

    await engine.dispose()


@pytest.mark.asyncio
async def test_bank_indonesia_targeted_bi_rate_success():
    """Verify BankIndonesiaFetcher accurately parses BI-Rate from HTML table."""
    html_sample = """
    <html>
      <body>
        <div class="content">
          <table class="table-striped">
            <tr>
              <td>Indikator Moneter</td>
              <td>Level</td>
            </tr>
            <tr>
              <td>BI-Rate (7-Day Reverse Repo Rate)</td>
              <td>6,25 %</td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """
    fetcher = BankIndonesiaFetcher()
    with patch("monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia.fetch_with_retry",
               new=AsyncMock(return_value=html_sample)):
        data = await fetcher.fetch_bi_rate()
        assert data["status"] == "success"
        assert data["rate_pct"] == 6.25
        assert data["central_bank"] == "Bank Indonesia"


@pytest.mark.asyncio
async def test_bank_indonesia_targeted_bi_rate_range_rejection():
    """Verify BankIndonesiaFetcher rejects out-of-range percentage (e.g. 1.2% or 19.5%)."""
    html_bad_sample = """
    <html>
      <body>
        <div class="content">
          <table>
            <tr>
              <td>BI-Rate Outlier</td>
              <td>19,50 %</td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """
    fetcher = BankIndonesiaFetcher()
    with patch("monika.infrastructure.data_ingestion.scrapers.macro.bank_indonesia.fetch_with_retry",
               new=AsyncMock(return_value=html_bad_sample)), \
         patch("monika.infrastructure.data_ingestion.sources.web_search.WebSearchService.search",
               new=AsyncMock(return_value={"results": []})):

        data = await fetcher.fetch_bi_rate()
        # Outlier 19.5% must be rejected; baseline 6.00% returned
        assert data["rate_pct"] == 6.00
        assert data["status"] == "estimated_baseline"
