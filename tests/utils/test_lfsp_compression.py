import pytest
import json
from utils.llm.prompt_compressor import truncate_to_budget

def test_lfsp_preserves_unmitigated_zones_over_mitigated():
    # 15 zones, 5 are mitigated (older and newer), 10 unmitigated
    zones = []
    for i in range(15):
        is_mit = i % 3 == 0
        zones.append({
            "price_low": 2700.0 + i,
            "price_high": 2705.0 + i,
            "type": "OB",
            "is_mitigated": is_mit
        })
    raw_payload = {"symbol": "XAUUSD", "zones": zones}
    
    # Truncate with target budget
    json_input = json.dumps(raw_payload)
    res_str = truncate_to_budget(json_input, max_tokens=150)
    parsed = json.loads(res_str)
    res_zones = parsed["zones"]
    # All retained zones must be unmitigated!
    assert len(res_zones) > 0
    assert all(not z.get("is_mitigated") for z in res_zones)

def test_lfsp_preserves_ohlcv_structural_extremes():
    candles = []
    for i in range(25):
        high = 2710.0 + (50.0 if i == 7 else i)  # Bar 7 is the global swing high (2760)
        low = 2700.0 - (40.0 if i == 12 else i) # Bar 12 is the global swing low (2660)
        candles.append({
            "time": 1000 + i,
            "open": 2705.0 + i,
            "high": high,
            "low": low,
            "close": 2706.0 + i,
        })
    raw_payload = {"symbol": "XAUUSD", "candles": candles}
    json_input = json.dumps(raw_payload)
    res_str = truncate_to_budget(json_input, max_tokens=180)
    parsed = json.loads(res_str)
    res_candles = parsed["candles"]
    # Extreme high (2760) and extreme low (2660) MUST be preserved!
    highs = [c["high"] for c in res_candles]
    lows = [c["low"] for c in res_candles]
    assert 2760.0 in highs
    assert 2660.0 in lows
