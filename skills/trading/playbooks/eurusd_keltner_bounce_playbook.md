---
name: eurusd_keltner_bounce_playbook
description: Keltner channel dynamic boundary bounce for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 1.02
profit_factor: 1.12
max_drawdown_pct: 13.62
win_rate: 0.358
---

# EURUSD Empirical Playbook: Keltner Channel Dynamic Boundary Bounce

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.02 (Zero-Lookahead simulation)
- **Profit Factor**: 1.12 (187 verified trade executions)
- **Max Drawdown**: 13.6% (Institutional risk profile)
- **Total PnL Return**: +13.5%
- **Win Rate**: 35.8% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Calculate 20-period Keltner Channel with 1.5x ATR multiplier on H1.
- Long Trigger: Low pierces lower Keltner boundary, closes back above it, with RSI <= 45.
- Short Trigger: High pierces upper Keltner boundary, closes back below it, with RSI >= 55.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully outside the Keltner envelope.
- Invalidate if midline slope is accelerating in direction of the breakout.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
