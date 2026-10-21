---
name: xbrusd_lon_ema40_bounce_playbook
description: Verified trending tactical execution playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.7
status: active
sharpe_ratio: null
legacy_t_statistic: 10.76
profit_factor: 1.33
max_drawdown_pct: 7.8
win_rate: 0.453
---

# XBRUSD Empirical Playbook: Lon EMA 40 Bounce Strategy

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 10.76 (Zero-Lookahead simulation)
- **Profit Factor**: 1.33 (95 verified trade executions)
- **Max Drawdown**: 7.8% (Institutional risk profile)
- **Total PnL Return**: +18.4%
- **Win Rate**: 45.3% (Normalized at minimum 1:1.7 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.7x ATR, Max Holding = 14 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.7 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.7x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
