---
name: usdjpy_rejection_wick_extreme_playbook
description: 24-hour range extreme rejection wick sweep for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.48
profit_factor: 1.37
max_drawdown_pct: 6.44
win_rate: 0.424
---

# USDJPY Empirical Playbook: 24-Hour Range Extreme Rejection Wick Sweep

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.48 (Zero-Lookahead simulation)
- **Profit Factor**: 1.37 (59 verified trade executions)
- **Max Drawdown**: 6.4% (Institutional risk profile)
- **Total PnL Return**: +12.1%
- **Win Rate**: 42.4% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Candle total range >= 1.0x 14-period ATR.
- Long Trigger: Lower wick >= 55% of candle range testing 24-hour low and closing higher.
- Short Trigger: Upper wick >= 55% of candle range testing 24-hour high and closing lower.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if subsequent candle breaks the extreme tip of the rejection wick.
- Invalidate if spread widens beyond asset risk limit.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
