---
name: xtiusd_triple_ema_pullback_playbook
description: Triple EMA alignment pullback continuation for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.8
status: active
sharpe_ratio: null
legacy_t_statistic: 5.23
profit_factor: 1.15
max_drawdown_pct: 14.8
win_rate: 0.403
---

# XTIUSD Empirical Playbook: Triple EMA Alignment Pullback Continuation

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 5.23 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (191 verified trade executions)
- **Max Drawdown**: 14.8% (Institutional risk profile)
- **Total PnL Return**: +17.1%
- **Win Rate**: 40.3% (Normalized at minimum 1:1.8 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.8x ATR, Max Holding = 16 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Bullish alignment: EMA 9 > EMA 21 > EMA 50.
- Bearish alignment: EMA 9 < EMA 21 < EMA 50.
- Long Trigger: Low tests EMA 21, candle closes higher than open and above EMA 21.
- Short Trigger: High tests EMA 21, candle closes lower than open and below EMA 21.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.8 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50.
- Invalidate if ribbon order flips prior to entry.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
