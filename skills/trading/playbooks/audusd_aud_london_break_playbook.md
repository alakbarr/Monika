---
name: audusd_aud_london_break_playbook
description: London open liquidity breakout and expansion for AUDUSD.
symbol: AUDUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.13
profit_factor: 1.2
max_drawdown_pct: 6.93
win_rate: 0.408
---

# AUDUSD Empirical Playbook: London Open Liquidity Breakout & Expansion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.13 (Zero-Lookahead simulation)
- **Profit Factor**: 1.20 (49 verified trade executions)
- **Max Drawdown**: 6.9% (Institutional risk profile)
- **Total PnL Return**: +5.8%
- **Win Rate**: 40.8% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Active during European session open (07:00 and 08:00 UTC).
- Map the preceding 8-hour Asian consolidation high and low.
- Long Trigger: H1 Close breaks strictly above the 8-hour high.
- Short Trigger: H1 Close breaks strictly below the 8-hour low.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle exhibits an opposing wick > 50% of total range.
- Invalidate if European market opens with zero volume expansion.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
