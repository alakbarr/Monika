---
name: usdjpy_rejection_wick_extreme_playbook
description: 24-hour range extreme rejection wick sweep for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.89
profit_factor: 1.39
max_drawdown_pct: 6.04
win_rate: 0.452
---

# USDJPY Empirical Playbook: 24-Hour Range Extreme Rejection Wick Sweep

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.89 (Zero-Lookahead simulation)
- **Profit Factor**: 1.39 (62 verified trade executions)
- **Max Drawdown**: 6.0% (Institutional risk profile)
- **Total PnL Return**: +12.7%
- **Win Rate**: 45.2% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 30 bars

## Trigger Conditions & Tactical Directives
- Candle total range >= 1.0x 14-period ATR.
- Long Trigger: Lower wick >= 55% of candle range testing 24-hour low and closing higher.
- Short Trigger: Upper wick >= 55% of candle range testing 24-hour high and closing lower.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if subsequent candle breaks the extreme tip of the rejection wick.
- Invalidate if spread widens beyond asset risk limit.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 30 bars.
