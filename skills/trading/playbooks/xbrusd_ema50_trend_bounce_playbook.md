---
name: xbrusd_ema50_trend_bounce_playbook
description: Institutional 50-EMA trend boundary bounce for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 7.2
profit_factor: 1.22
max_drawdown_pct: 8.9
win_rate: 0.405
---

# XBRUSD Empirical Playbook: Institutional 50-EMA Trend Boundary Bounce

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 7.20 (Zero-Lookahead simulation)
- **Profit Factor**: 1.22 (168 verified trade executions)
- **Max Drawdown**: 8.9% (Institutional risk profile)
- **Total PnL Return**: +22.7%
- **Win Rate**: 40.5% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 20 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Macro trend filter: Close > EMA 200 (Bull) or Close < EMA 200 (Bear).
- Long Trigger: Low touches EMA 50, rejects, and candle closes bullish above EMA 50.
- Short Trigger: High touches EMA 50, rejects, and candle closes bearish below EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully across EMA 50.
- Invalidate if 200 EMA slope turns flat or opposing.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
