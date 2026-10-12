# ==============================================================================
# File: tests/data_sources/test_prediction_market.py
# Monika Prediction Market Client Test Suite
# ==============================================================================

import json
from unittest.mock import AsyncMock, patch
import pytest

from data_sources.prediction_market import PredictionMarketClient


@pytest.fixture
def mock_gamma_events():
    return [
        {
            "id": "ev1",
            "title": "Fed Interest Rate Cut by September 2026",
            "description": "Will FOMC cut federal funds rate?",
            "volume": "1500000",
            "liquidity": "450000",
            "endDate": "2026-09-30",
            "markets": [
                {
                    "id": "m1",
                    "question": "Will Fed cut 25bps in September?",
                    "outcomePrices": json.dumps(["0.72", "0.28"]),
                    "clobTokenIds": json.dumps(["token_123", "token_456"]),
                    "volume24hr": "50000",
                    "acceptingOrders": True,
                }
            ],
        },
        {
            "id": "ev2",
            "title": "Middle East Oil Supply Disruption",
            "description": "Crude oil transit blockade",
            "volume": "800000",
            "liquidity": "200000",
            "endDate": "2026-12-31",
            "markets": [
                {
                    "id": "m2",
                    "question": "Will Strait of Hormuz face active blockade?",
                    "lastTradePrice": 0.58,
                    "clobTokenIds": json.dumps(["token_789"]),
                    "volume24hr": "20000",
                    "acceptingOrders": True,
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_fetch_macro_events_parsing(mock_gamma_events):
    client = PredictionMarketClient()
    with patch("data_sources.prediction_market.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_gamma_events
        events = await client.fetch_macro_events()

        assert len(events) == 2
        assert events[0]["title"] == "Fed Interest Rate Cut by September 2026"
        assert len(events[0]["markets"]) == 1
        m1 = events[0]["markets"][0]
        assert m1["yes_probability"] == 0.72
        assert m1["no_probability"] == 0.28
        assert m1["token_id"] == "token_123"

        m2 = events[1]["markets"][0]
        assert m2["yes_probability"] == 0.58
        assert m2["no_probability"] == 0.42


@pytest.mark.asyncio
async def test_fetch_clob_orderbook():
    client = PredictionMarketClient()
    mock_book = {
        "bids": [{"price": "0.71", "size": "1000"}],
        "asks": [{"price": "0.74", "size": "800"}],
    }
    with patch("data_sources.prediction_market.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_book
        ob = await client.fetch_clob_orderbook("token_123")

        assert ob["best_bid"] == 0.71
        assert ob["best_ask"] == 0.74
        assert ob["spread"] == 0.03
        assert ob["bid_depth"] == 1


from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_ingest_and_persist_classification(mock_gamma_events):
    session = create_mock_async_session()

    client = PredictionMarketClient(session=session)
    with patch("data_sources.prediction_market.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_gamma_events
        with patch("database.safe_ops.safe_commit", new_callable=AsyncMock):
            result = await client.ingest_and_persist()

            assert result["source"] == "Polymarket"
            assert result["events_count"] == 2
            assert len(result["fed_rate_odds"]) == 1
            assert len(result["geopolitics_odds"]) == 1
            # Geopolitics odds > 0.50 triggers RISK_OFF
            assert result["sentiment_bias"] == "RISK_OFF"
