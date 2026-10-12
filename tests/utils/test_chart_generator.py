# ==============================================================================
# File: tests/utils/test_chart_generator.py
# ==============================================================================

import io
import pytest
from datetime import datetime, timezone, timedelta

pytest.importorskip("matplotlib")
pytest.importorskip("mplfinance")
from utils.chart_generator import generate_candlestick_chart


def test_generate_candlestick_chart_valid():
    """Memastikan chart generator menghasilkan buffer PNG valid dari data OHLCV."""
    now = datetime.now(timezone.utc)
    ohlcv_rows = [
        {
            "timestamp": now - timedelta(hours=50 - i),
            "open": 2000.0 + i * 0.5,
            "high": 2005.0 + i * 0.5,
            "low": 1998.0 + i * 0.5,
            "close": 2003.0 + i * 0.5,
            "volume": 1500 + i * 10,
        }
        for i in range(50)
    ]

    buf = generate_candlestick_chart(
        ohlcv_rows=ohlcv_rows,
        symbol="XAUUSD",
        timeframe="H1",
        show_volume=True,
        show_ma=(20, 50),
    )

    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 1000  # PNG image binary size
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic header


def test_generate_candlestick_chart_insufficient_data():
    """Memastikan ValueError dilempar jika data lilin kurang dari 2 baris."""
    with pytest.raises(ValueError):
        generate_candlestick_chart(
            ohlcv_rows=[{"open": 100, "high": 105, "low": 95, "close": 102}],
            symbol="EURUSD",
        )
