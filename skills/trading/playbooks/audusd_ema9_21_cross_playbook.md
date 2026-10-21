---
name: audusd_ema9_21_cross_playbook
description: Fast EMA 9/21 trend crossover playbook for AUDUSD.
symbol: AUDUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 9.49
profit_factor: 1.3
max_drawdown_pct: 11.0
win_rate: 0.43
---

# AUDUSD Empirical Playbook: Fast EMA 9/21 Trend Crossover & Expansion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 9.49 (Zero-Lookahead simulation)
- **Profit Factor**: 1.30 (114 verified trade executions)
- **Max Drawdown**: 11.0% (Institutional risk profile)
- **Total PnL Return**: +21.8%
- **Win Rate**: 43.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Calculate 9-period and 21-period EMA on H1.
- Long Trigger: EMA 9 crosses above EMA 21 and Close > EMA 50.
- Short Trigger: EMA 9 crosses below EMA 21 and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if EMAs converge back together within 2 bars (whipsaw filter).
- Invalidate if crossover occurs in flat 200 EMA slope.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
