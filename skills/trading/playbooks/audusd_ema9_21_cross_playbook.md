---
name: audusd_ema9_21_cross_playbook
description: Fast EMA 9/21 trend crossover playbook for AUDUSD.
symbol: AUDUSD
regime: trending
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 3.31
profit_factor: 1.39
max_drawdown_pct: 10.48
win_rate: 0.43
---

# AUDUSD Empirical Playbook: Fast EMA 9/21 Trend Crossover & Expansion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.31 (Zero-Lookahead simulation)
- **Profit Factor**: 1.39 (114 verified trade executions)
- **Max Drawdown**: 10.5% (Institutional risk profile)
- **Total PnL Return**: +29.7%
- **Win Rate**: 43.0% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Calculate 9-period and 21-period EMA on H1.
- Long Trigger: EMA 9 crosses above EMA 21 and Close > EMA 50.
- Short Trigger: EMA 9 crosses below EMA 21 and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if EMAs converge back together within 2 bars (whipsaw filter).
- Invalidate if crossover occurs in flat 200 EMA slope.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
