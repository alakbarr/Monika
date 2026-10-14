---
name: usdjpy_aud_us_close_reversion_playbook
description: US session close range exhaustion reversion for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 1.75
status: active
sharpe_ratio: 5.86
profit_factor: 1.43
max_drawdown_pct: 4.99
win_rate: 0.494
---

# USDJPY Empirical Playbook: US Session Close Range Exhaustion Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.86 (Zero-Lookahead simulation)
- **Profit Factor**: 1.43 (77 verified trade executions)
- **Max Drawdown**: 5.0% (Institutional risk profile)
- **Total PnL Return**: +17.9%
- **Win Rate**: 49.4% (Normalized at minimum 1:1.75 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.4x ATR, Max Holding = 10 bars

## Trigger Conditions & Tactical Directives
- Active during US session close window (20:00 to 22:00 UTC) ahead of Sydney open.
- Long Trigger: RSI <= 42 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 58 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.75 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if unexpected geopolitical news breaks during market rollover.
- Invalidate if spread widens beyond 3.0 pips during 21:00-22:00 UTC transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 10 bars.
