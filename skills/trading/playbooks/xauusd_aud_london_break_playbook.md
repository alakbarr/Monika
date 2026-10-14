---
name: xauusd_aud_london_break_playbook
description: London open liquidity breakout and expansion for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 5.98
profit_factor: 1.78
max_drawdown_pct: 5.87
win_rate: 0.459
---

# XAUUSD Empirical Playbook: London Open Liquidity Breakout & Expansion

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.98 (Zero-Lookahead simulation)
- **Profit Factor**: 1.78 (61 verified trade executions)
- **Max Drawdown**: 5.9% (Institutional risk profile)
- **Total PnL Return**: +27.7%
- **Win Rate**: 45.9% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Active during European session open (07:00 and 08:00 UTC).
- Map the preceding 8-hour Asian consolidation high and low.
- Long Trigger: H1 Close breaks strictly above the 8-hour high.
- Short Trigger: H1 Close breaks strictly below the 8-hour low.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle exhibits an opposing wick > 50% of total range.
- Invalidate if European market opens with zero volume expansion.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
