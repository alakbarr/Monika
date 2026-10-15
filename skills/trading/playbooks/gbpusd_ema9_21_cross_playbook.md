---
name: gbpusd_ema9_21_cross_playbook
description: Fast EMA 9/21 trend crossover playbook for GBPUSD.
symbol: GBPUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.17
profit_factor: 1.15
max_drawdown_pct: 7.49
win_rate: 0.387
---

# GBPUSD Empirical Playbook: Fast EMA 9/21 Trend Crossover & Expansion

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.17 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (93 verified trade executions)
- **Max Drawdown**: 7.5% (Institutional risk profile)
- **Total PnL Return**: +7.8%
- **Win Rate**: 38.7% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Calculate 9-period and 21-period EMA on H1.
- Long Trigger: EMA 9 crosses above EMA 21 and Close > EMA 50.
- Short Trigger: EMA 9 crosses below EMA 21 and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if EMAs converge back together within 2 bars (whipsaw filter).
- Invalidate if crossover occurs in flat 200 EMA slope.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
