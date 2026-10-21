---
name: xbrusd_ema_stoch_confluence_playbook
description: EMA trend and stochastic momentum confluence for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.82
status: active
sharpe_ratio: null
legacy_t_statistic: 8.5
profit_factor: 1.26
max_drawdown_pct: 11.0
win_rate: 0.436
---

# XBRUSD Empirical Playbook: EMA Trend & Stochastic Momentum Confluence

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 8.50 (Zero-Lookahead simulation)
- **Profit Factor**: 1.26 (101 verified trade executions)
- **Max Drawdown**: 11.0% (Institutional risk profile)
- **Total PnL Return**: +15.1%
- **Win Rate**: 43.6% (Normalized at minimum 1:1.82 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.1x ATR, Take-Profit = 2.0x ATR, Max Holding = 18 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Trend filter: Close > EMA 50 (Bull) or Close < EMA 50 (Bear).
- Long Trigger: Stochastic %K crosses above %D below 45, and candle closes higher than open.
- Short Trigger: Stochastic %K crosses below %D above 55, and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.82 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.1x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if Stochastic %K recrosses %D within 2 bars.
- Invalidate if price falls across EMA 50.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
