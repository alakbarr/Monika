import json
from monika.application.analysis.context.data_compactor import (
    compact_ohlcv_bars,
    compact_indicators,
    compact_market_structure,
)


def test_compact_ohlcv_bars():
    bars = [
        {"timeframe": "M15", "open": 4050.5, "high": 4065.2, "low": 4048.1, "close": 4060.0, "volume": 1250},
        {"timeframe": "H1", "open": 4040.0, "high": 4070.0, "low": 4035.0, "close": 4060.0, "volume": 5400},
    ]
    res = compact_ohlcv_bars(bars)
    assert "M15  | O:4050.50 H:4065.20 L:4048.10 C:4060.00 | Vol:1250" in res
    assert "H1   | O:4040.00 H:4070.00 L:4035.00 C:4060.00 | Vol:5400" in res


def test_compact_indicators():
    indicators = [
        {"timeframe": "M15", "indicator_name": "RSI", "value_json": json.dumps({"value": 64.44})},
        {"timeframe": "H1", "indicator_name": "MACD", "value_json": json.dumps({"macd": 4.69, "signal": 3.20})},
    ]
    res = compact_indicators(indicators)
    assert "M15  | RSI             : value=64.44" in res
    assert "H1   | MACD            : macd=4.69, signal=3.20" in res


def test_compact_market_structure_combined():
    bars = [{"timeframe": "D1", "open": 4000.0, "high": 4080.0, "low": 3990.0, "close": 4060.0, "volume": 25000}]
    indicators = [{"timeframe": "D1", "indicator_name": "ADX", "value_json": json.dumps({"adx": 45.34})}]
    combined = compact_market_structure(ohlcv_bars=bars, indicators=indicators)
    assert "=== MARKET STRUCTURE & TECHNICAL DATA ===" in combined
    assert "D1   | O:4000.00" in combined
    assert "D1   | ADX" in combined
