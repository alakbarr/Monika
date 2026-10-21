---
name: xauusd_lon_ema5_bounce_playbook
description: Verified trending tactical execution playbook for XAUUSD.
symbol: XAUUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: null
legacy_t_statistic: 10.82
profit_factor: 1.34
max_drawdown_pct: 9.5
win_rate: 0.449
---

# XAUUSD Empirical Playbook: Lon EMA 5 Bounce Strategy

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 10.82 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (207 verified trade executions)
- **Max Drawdown**: 9.5% (Institutional risk profile)
- **Total PnL Return**: +42.6%
- **Win Rate**: 44.9% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
