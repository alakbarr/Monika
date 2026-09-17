"""Unit tests for MyFxBook and FXSSI sentiment scrapers and FRED series integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from scrapers.sentiment.myfxbook_sentiment import MyFxBookSentimentFetcher
from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher
from data_sources.fred_treasury_yield import FREDDataFetcher, SERIES_TO_TENOR, TENOR_SERIES


def test_myfxbook_parse_html_multi_asset():
    """Test MyFxBook HTML parser with Forex and Gold."""
    sample_html = """
    <html>
        <body>
            <table class="outlookTable">
                <tr><td>EURUSD</td><td>SHORT 35%</td><td>LONG 65%</td></tr>
                <tr><td>GBP/USD</td><td>SHORT 40%</td><td>LONG 60%</td></tr>
                <tr><td>USD/JPY</td><td>SHORT 70%</td><td>LONG 30%</td></tr>
                <tr><td>AUD/USD</td><td>SHORT 45%</td><td>LONG 55%</td></tr>
                <tr><td>GOLD</td><td>SHORT 25%</td><td>LONG 75%</td></tr>
            </table>
        </body>
    </html>
    """
    fetcher = MyFxBookSentimentFetcher(session=MagicMock())
    results = fetcher._parse_html(sample_html)

    assert "EURUSD" in results
    assert results["EURUSD"]["long_percent"] == 65.0
    assert results["EURUSD"]["short_percent"] == 35.0

    assert "GBPUSD" in results
    assert results["GBPUSD"]["long_percent"] == 60.0

    assert "USDJPY" in results
    assert results["USDJPY"]["short_percent"] == 70.0

    assert "AUDUSD" in results
    assert results["AUDUSD"]["long_percent"] == 55.0

    assert "XAUUSD" in results
    assert results["XAUUSD"]["long_percent"] == 75.0


def test_fxssi_parse_html_dom_and_regex():
    """Test FXSSI HTML parser with DOM cards and regex fallback."""
    sample_html_dom = """
    <html>
        <body>
            <div class="cur-rat-container">
                <div class="cur-rat-cur-pair" data-filter="EURUSD">
                    <div class="cur-rat-title">EURUSD</div>
                    <div class="cur-rat-broker" data-name="Average">
                        <div class="ratio-bar-left">58%</div>
                        <div class="ratio-bar-right">42%</div>
                    </div>
                </div>
                <div class="cur-rat-cur-pair" data-filter="XAUUSD">
                    <div class="cur-rat-title">XAUUSD</div>
                    <div class="cur-rat-broker" data-name="Average">
                        <div class="ratio-bar-left">72%</div>
                        <div class="ratio-bar-right">28%</div>
                    </div>
                </div>
            </div>
            <div>
                GBPUSD Average 60% 40%
                USDJPY Average 30% 70%
                AUDUSD Average 52% 48%
                WTI Average 45% 55%
                BTCUSD Average 85% 15%
            </div>
        </body>
    </html>
    """
    fetcher = FXSSISentimentFetcher(session=MagicMock())
    results = fetcher._parse_html(sample_html_dom)

    assert "EURUSD" in results
    assert results["EURUSD"]["long_percent"] == 58.0
    assert results["EURUSD"]["short_percent"] == 42.0

    assert "XAUUSD" in results
    assert results["XAUUSD"]["long_percent"] == 72.0

    assert "GBPUSD" in results
    assert results["GBPUSD"]["long_percent"] == 60.0

    assert "USDJPY" in results
    assert results["USDJPY"]["short_percent"] == 70.0

    assert "AUDUSD" in results
    assert results["AUDUSD"]["long_percent"] == 52.0

    assert "XTIUSD" in results
    assert results["XTIUSD"]["long_percent"] == 45.0

    assert "BTCUSD" in results
    assert results["BTCUSD"]["long_percent"] == 85.0


@pytest.mark.asyncio
async def test_fred_series_mapping():
    """Test FREDDataFetcher series mappings include inflation and real yields."""
    assert "T10YIE" in TENOR_SERIES
    assert "DFII10" in TENOR_SERIES
    assert SERIES_TO_TENOR["T10YIE"] == "10Y_INFLATION"
    assert SERIES_TO_TENOR["DFII10"] == "10Y_REAL"

    mock_session = AsyncMock()
    config = {
        "series": {
            "treasury_10y": "DGS10",
            "inflation_expectation_10y": "T10YIE",
            "real_yield_10y": "DFII10",
        }
    }
    fetcher = FREDDataFetcher(session=mock_session, config=config, api_key="dummy_key")
    fetcher._fetch_treasury_series = AsyncMock(return_value=1)

    result = await fetcher.fetch_all()
    assert result["treasury"] == 3
    assert fetcher._fetch_treasury_series.call_count == 3


def test_base_scraper_is_cloudflare_challenge_multilingual():
    """Test BaseScraper._is_cloudflare_challenge recognizes Indonesian and English titles."""
    from scrapers.base_scraper import BaseScraper
    scraper = BaseScraper.__new__(BaseScraper)
    scraper.page = MagicMock()

    for sample_title in ["Just a moment...", "Tunggu sebentar...", "Attention Required! | Cloudflare", "Pemeriksaan keamanan"]:
        scraper.page.title = sample_title
        assert scraper._is_cloudflare_challenge() is True

    scraper.page.title = "Forex Sentiment | Myfxbook"
    scraper.page.ele.return_value = None
    assert scraper._is_cloudflare_challenge() is False


def test_myfxbook_fetch_sync_error_resilience():
    """Test MyFxBookSentimentFetcher.fetch_sync handles browser failure without unhandled crash."""
    from unittest.mock import patch
    fetcher = MyFxBookSentimentFetcher(session=MagicMock())
    with patch("scrapers.sentiment.myfxbook_sentiment.BaseScraper", side_effect=Exception("浏览器连接失败。 127.0.0.1:16944")):
        res = fetcher.fetch_sync()
        assert "error" in res
        assert "127.0.0.1:16944" in res["error"]
