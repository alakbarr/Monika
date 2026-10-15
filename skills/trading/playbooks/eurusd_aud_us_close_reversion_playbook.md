---
name: eurusd_aud_us_close_reversion_playbook
description: US session close range exhaustion reversion for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.3
profit_factor: 1.19
max_drawdown_pct: 10.26
win_rate: 0.42
---

# EURUSD Empirical Playbook: US Session Close Range Exhaustion Reversion

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.30 (Zero-Lookahead simulation)
- **Profit Factor**: 1.19 (69 verified trade executions)
- **Max Drawdown**: 10.3% (Institutional risk profile)
- **Total PnL Return**: +7.2%
- **Win Rate**: 42.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Active during US session close window (20:00 to 22:00 UTC) ahead of Sydney open.
- Long Trigger: RSI <= 42 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 58 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if unexpected geopolitical news breaks during market rollover.
- Invalidate if spread widens beyond 3.0 pips during 21:00-22:00 UTC transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
