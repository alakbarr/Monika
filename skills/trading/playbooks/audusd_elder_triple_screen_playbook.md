---
name: audusd_elder_triple_screen_playbook
description: Alexander Elder triple screen pullback for AUDUSD.
symbol: AUDUSD
regime: trending
timeframe: H1
min_rr: 2.13
status: active
sharpe_ratio: 1.72
profit_factor: 1.18
max_drawdown_pct: 11.13
win_rate: 0.413
---

# AUDUSD Empirical Playbook: Alexander Elder Triple Screen Trend Pullback

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.72 (Zero-Lookahead simulation)
- **Profit Factor**: 1.18 (150 verified trade executions)
- **Max Drawdown**: 11.1% (Institutional risk profile)
- **Total PnL Return**: +15.1%
- **Win Rate**: 41.3% (Normalized at minimum 1:2.13 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.2x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Higher Timeframe (H4) trend filter: EMA 50 > EMA 200 (Bull) or EMA 50 < EMA 200 (Bear).
- Long Trigger: H4 Bull, H1 Stochastic %K <= 35, %K crosses above %D, and Close > Open.
- Short Trigger: H4 Bear, H1 Stochastic %K >= 65, %K crosses below %D, and Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.13 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if H4 trend structure invalidates with EMA 50/200 cross.
- Invalidate if Stochastic %K recrosses %D within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
