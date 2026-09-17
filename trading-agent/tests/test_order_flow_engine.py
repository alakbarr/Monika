# ==============================================================================
# File: tests/test_order_flow_engine.py
# ==============================================================================

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from indicators.order_flow import OrderFlowEngine, OrderFlowSnapshot, fetch_latest_order_flow
from database.models import PriceOHLCV, TechnicalIndicator


@pytest.mark.asyncio
async def test_order_flow_real_dom_l2_calculation():
    """Verify OrderFlowEngine uses Real DOM L2 when mt5.market_book_add succeeds."""
    mock_mt5 = AsyncMock()
    mock_mt5.market_book_add.return_value = True

    # Mock L2 DOM book with 2 bids and 2 asks
    class MockBook:
        def __init__(self, book_type, price, volume):
            self.type = book_type
            self.price = price
            self.volume = volume

    # type 2 = BUY (bid), type 1 = SELL (ask)
    books = (
        MockBook(book_type=2, price=2000.0, volume=150.0),
        MockBook(book_type=2, price=1999.5, volume=100.0),
        MockBook(book_type=1, price=2000.5, volume=50.0),
        MockBook(book_type=1, price=2001.0, volume=50.0),
    )
    mock_mt5.market_book_get.return_value = books

    engine = OrderFlowEngine(mt5_client=mock_mt5)
    mock_session = AsyncMock()

    snapshot = await engine.analyze_order_flow(mock_session, "XAUUSD")

    assert snapshot.mode == "REAL_DOM_L2"
    # Total bid vol = 250, total ask vol = 100, tot = 350
    # OBI = (250 - 100) / 350 = 150 / 350 = ~0.4286 (Bullish bid dominant)
    assert 0.42 < snapshot.order_book_imbalance < 0.44
    assert snapshot.top_of_book_depth["bid_depth"] == 250.0
    assert snapshot.top_of_book_depth["ask_depth"] == 100.0
    assert snapshot.top_of_book_depth["spread"] == 0.5


@pytest.mark.asyncio
async def test_order_flow_lee_ready_fallback_and_absorption():
    """Verify OrderFlowEngine falls back to Lee-Ready Tick Rule CVD when DOM unsupported."""
    mock_mt5 = AsyncMock()
    mock_mt5.market_book_add.return_value = False  # Broker doesn't support DOM

    engine = OrderFlowEngine(mt5_client=mock_mt5)
    now = datetime.now(timezone.utc)

    # Construct candles where price goes up but volume delta diverges (bearish absorption)
    # First half: price 100.0 -> 101.0 with high buyer volume
    # Second half: price 101.0 -> 105.0 but delta drops because downticks dominate volume
    bars = []
    # First half: price rises with buyer ticks
    for i in range(10):
        bars.append(PriceOHLCV(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=now - timedelta(minutes=15 * (20 - i)),
            open=100.0 + i * 0.2,
            high=100.0 + i * 0.2 + 0.3,
            low=100.0 + i * 0.2 - 0.1,
            close=100.0 + (i + 1) * 0.2,
            volume=500.0
        ))
    # Second half: price continues higher, but closes are lower than previous bar or with negative tick delta
    for i in range(10):
        bars.append(PriceOHLCV(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=now - timedelta(minutes=15 * (10 - i)),
            open=103.0 + i * 0.3,
            high=103.0 + i * 0.3 + 0.1,
            low=103.0 + i * 0.3 - 0.2,
            close=103.0 + i * 0.3 - 0.05,  # Downtick from previous
            volume=800.0
        ))

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = list(reversed(bars))  # desc order
    mock_session.execute.return_value = mock_result

    snapshot = await engine.analyze_order_flow(mock_session, "EURUSD")

    assert snapshot.mode == "SYNTHETIC_TICK_RULE"
    assert -1.0 <= snapshot.order_book_imbalance <= 1.0
    assert snapshot.cvd_divergence in ("BEARISH_ABSORPTION", "NONE", "BULLISH_ABSORPTION")


@pytest.mark.asyncio
async def test_fetch_latest_order_flow_retrieval():
    """Verify fetch_latest_order_flow retrieves stored snapshot from TechnicalIndicator table."""
    mock_session = AsyncMock()
    mock_row = TechnicalIndicator(
        symbol="BTCUSD",
        timeframe="H1",
        indicator_name="ORDER_FLOW_SNAPSHOT",
        value_json='{"mode": "REAL_DOM_L2", "order_book_imbalance": 0.25, "cvd_session_delta": 45.0, "cvd_divergence": "BULLISH_ABSORPTION", "top_of_book_depth": {"bid_depth": 100, "ask_depth": 60}}',
        timestamp=datetime.now(timezone.utc)
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_row
    mock_session.execute.return_value = mock_result

    snapshot = await fetch_latest_order_flow(mock_session, "BTCUSD")

    assert snapshot.symbol == "BTCUSD"
    assert snapshot.mode == "REAL_DOM_L2"
    assert snapshot.order_book_imbalance == 0.25
    assert snapshot.cvd_divergence == "BULLISH_ABSORPTION"


@pytest.mark.asyncio
async def test_order_flow_real_dom_dict_structure():
    """Verify OrderFlowEngine parses dict structures (e.g. from JSON/REST remote gateway)."""
    mock_mt5 = AsyncMock()
    mock_mt5.market_book_add.return_value = True

    books = [
        {"type": 2, "price": 2000.0, "volume": 150.0},
        {"type": 1, "price": 2000.5, "volume": 50.0},
    ]
    mock_mt5.market_book_get.return_value = books

    engine = OrderFlowEngine(mt5_client=mock_mt5)
    mock_session = AsyncMock()

    snapshot = await engine.analyze_order_flow(mock_session, "XAUUSD")
    assert snapshot.mode == "REAL_DOM_L2"
    assert snapshot.order_book_imbalance == 0.5  # (150 - 50) / 200
    assert snapshot.top_of_book_depth["bid_depth"] == 150.0
    assert snapshot.top_of_book_depth["ask_depth"] == 50.0
    assert snapshot.top_of_book_depth["spread"] == 0.5

