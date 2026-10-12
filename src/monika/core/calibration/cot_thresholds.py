from typing import Optional


def get_cot_extreme_thresholds(symbol: str, history_percentiles: Optional[list] = None) -> dict:
    """Single source of truth for COT extreme thresholds (using long % of total leveraged positions)."""
    if "JPY" in symbol or "EUR" in symbol:
        base_long = 80.0
        base_short = 20.0
    elif "GBP" in symbol or "AUD" in symbol or "NZD" in symbol or symbol in ["XAUUSD", "BTCUSD"]:
        base_long = 85.0
        base_short = 15.0
    else:
        base_long = 80.0
        base_short = 20.0
        
    if history_percentiles and len(history_percentiles) >= 10:
        sorted_hist = sorted(history_percentiles)
        idx_long = int(len(sorted_hist) * 0.9)
        idx_short = int(len(sorted_hist) * 0.1)
        dyn_long = sorted_hist[idx_long]
        dyn_short = sorted_hist[idx_short]
        return {
            "extreme_long": (base_long + dyn_long) / 2.0,
            "extreme_short": (base_short + dyn_short) / 2.0
        }
        
    return {"extreme_long": base_long, "extreme_short": base_short}

def cot_extreme_score(symbol: str, current_percentile: float, history_percentiles: Optional[list] = None) -> int:
    """Returns +1 if extreme short (bullish for asset), -1 if extreme long (bearish), 0 if neutral"""
    if current_percentile is None:
        return 0
    t = get_cot_extreme_thresholds(symbol, history_percentiles)
    if current_percentile >= t["extreme_long"]:
        return -1
    elif current_percentile <= t["extreme_short"]:
        return 1
    return 0
