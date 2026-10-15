---
name: audusd_aud_us_close_reversion_playbook
description: US session close range exhaustion reversion for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.62
profit_factor: 1.37
max_drawdown_pct: 7.96
win_rate: 0.453
---

# AUDUSD Empirical Playbook: US Session Close Range Exhaustion Reversion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.62 (Zero-Lookahead simulation)
- **Profit Factor**: 1.37 (75 verified trade executions)
- **Max Drawdown**: 8.0% (Institutional risk profile)
- **Total PnL Return**: +15.6%
- **Win Rate**: 45.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Active during US session close window (20:00 to 22:00 UTC) ahead of Sydney open.
- Long Trigger: RSI <= 42 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 58 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if unexpected geopolitical news breaks during market rollover.
- Invalidate if spread widens beyond 3.0 pips during 21:00-22:00 UTC transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
