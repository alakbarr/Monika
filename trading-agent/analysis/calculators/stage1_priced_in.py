from typing import Optional
from utils.calibration.cot_thresholds import cot_extreme_score

def calculate_stage1_priced_in_baseline(
    symbol: str,
    cot_percentile: float,
    retail_sentiment: Optional[float] = None,
    fedwatch_dominant_prob: Optional[float] = None,
    eurusd_run_up_vs_atr: Optional[float] = None,
    fedwatch_repricing_delta: Optional[float] = None,
) -> dict:
    score = 0
    reasons = []
    cot_val = cot_extreme_score(symbol, cot_percentile)
    if cot_val == -1:
        score += 1
        reasons.append('COT positioning is extremely long (Priced-in for downside)')
    elif cot_val == 1:
        score += 1
        reasons.append('COT positioning is extremely short (Priced-in for upside)')
    if retail_sentiment is not None:
        if retail_sentiment > 70.0:
            score += 1
            reasons.append(f'Retail is heavily long ({retail_sentiment}%)')
        elif retail_sentiment < 30.0:
            score += 1
            reasons.append(f'Retail is heavily short ({retail_sentiment}%)')
    if fedwatch_dominant_prob is not None and fedwatch_dominant_prob > 80.0:
        score += 1
        reasons.append(f'FedWatch dominant outcome at {fedwatch_dominant_prob:.0f}% — largely priced in')
    if fedwatch_repricing_delta is not None and abs(fedwatch_repricing_delta) >= 10.0:
        score += 1
        sign = "+" if fedwatch_repricing_delta > 0 else ""
        reasons.append(f'FedWatch repricing shift {sign}{fedwatch_repricing_delta:.1f}% — active central bank repricing')
    if eurusd_run_up_vs_atr is not None and eurusd_run_up_vs_atr > 2.5:
        score += 1
        reasons.append(f'EURUSD (USD proxy) run-up {eurusd_run_up_vs_atr:.1f}x ATR — aggressive pre-positioning')
    is_priced_in = score >= 2   # dinaikkan dari >=1 karena sekarang ada sinyal repricing delta
    return {'score': score, 'is_priced_in': is_priced_in, 'reasons': reasons}
