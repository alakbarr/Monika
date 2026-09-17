import pytest
from utils.llm.prompt_compressor import estimate_tokens, truncate_to_budget, ContextCompressor

def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("1234") == 1
    assert estimate_tokens("a" * 400) == 100

def test_truncate_to_budget():
    text = "a" * 1000
    res = truncate_to_budget(text, max_tokens=50) # 50 tok = 200 chars
    assert len(res) < 1000
    assert "[TRUNCATED — budget exceeded]" in res

def test_compress_ohlcv():
    compressor = ContextCompressor()
    bars = [
        {"time": f"2026-08-20T{i:02d}:00:00Z", "open": 1.1, "high": 1.12, "low": 1.09, "close": 1.11, "volume": 100}
        for i in range(50)
    ]
    compressed = compressor.compress_ohlcv(bars, max_bars=20)
    assert len(compressed) <= 20
    # Last bar must be preserved
    assert compressed[-1]["time"] == bars[-1]["time"]

def test_compress_indicators():
    compressor = ContextCompressor()
    indicators = {
        "RSI_14": 30.0, # Extreme -> keep
        "RSI_14_neutral": 50.0, # Neutral -> drop
        "MACD": {"hist": 0.5}, # Dict -> keep
        "SMA_20": 1.105, # Trend -> keep
        "STOCH_K": 50.0, # Neutral -> drop
        "STOCH_K_extreme": 15.0, # Extreme -> keep
    }
    res = compressor.compress_indicators(indicators)
    assert "RSI_14" in res
    assert "RSI_14_neutral" not in res
    assert "MACD" in res
    assert "SMA_20" in res
    assert "STOCH_K" not in res
    assert "STOCH_K_extreme" in res

def test_compress_bundles():
    compressor = ContextCompressor()
    bundle = "line\n" * 10000
    res1 = compressor.compress_stage1_bundle(bundle, max_tokens=100)
    assert estimate_tokens(res1) <= 120
    res2 = compressor.compress_stage2_bundle(bundle, symbol="EURUSD", max_tokens=100)
    assert estimate_tokens(res2) <= 120
