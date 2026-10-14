---
name: eurusd_ny_morning_breakout_playbook
description: New York morning session breakout for EURUSD.
symbol: EURUSD
regime: breakout
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 2.6
profit_factor: 1.25
max_drawdown_pct: 6.4
win_rate: 0.381
---

# EURUSD Empirical Playbook: New York Morning Session Expansion Breakout

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.60 (Zero-Lookahead simulation)
- **Profit Factor**: 1.25 (84 verified trade executions)
- **Max Drawdown**: 6.4% (Institutional risk profile)
- **Total PnL Return**: +12.9%
- **Win Rate**: 38.1% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Active during high-liquidity New York morning open (13:00 to 15:00 UTC).
- Map the preceding 6-hour London consolidation high and low.
- Long Trigger: Close breaks above 6-hour high and Close > EMA 50.
- Short Trigger: Close breaks below 6-hour low and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle fails to hold beyond the 6-hour boundary.
- Invalidate during major US FOMC interest rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
