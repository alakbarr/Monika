---
name: usdjpy_tokyo_afternoon_push_playbook
description: Tokyo afternoon institutional trend push for USDJPY.
symbol: USDJPY
regime: trending
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 1.94
profit_factor: 1.14
max_drawdown_pct: 13.21
win_rate: 0.444
---

# USDJPY Empirical Playbook: Tokyo Afternoon Institutional Trend Push

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.94 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (180 verified trade executions)
- **Max Drawdown**: 13.2% (Institutional risk profile)
- **Total PnL Return**: +12.9%
- **Win Rate**: 44.4% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 1.8x ATR, Max Holding = 14 bars

## Trigger Conditions & Tactical Directives
- Active during late Tokyo / Singapore afternoon session (05:00 to 07:00 UTC).
- Long Trigger: Close > EMA 20, Close > Open, and RSI >= 50.
- Short Trigger: Close < EMA 20, Close < Open, and RSI <= 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if volatility collapses below minimum execution spread threshold.
- Invalidate if European pre-market news disrupts trend structure.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
