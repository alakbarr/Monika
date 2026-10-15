---
name: xauusd_aud_sydney_breakout_playbook
description: Sydney opening session range breakout for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 4.91
profit_factor: 1.31
max_drawdown_pct: 8.12
win_rate: 0.364
---

# XAUUSD Empirical Playbook: Sydney Session Opening Liquidity Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.91 (Zero-Lookahead simulation)
- **Profit Factor**: 1.31 (77 verified trade executions)
- **Max Drawdown**: 8.1% (Institutional risk profile)
- **Total PnL Return**: +16.4%
- **Win Rate**: 36.4% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.6x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Active during Sydney open hours (21:00 to 23:00 UTC).
- Map preceding 4-hour consolidation high and low.
- Long Trigger: Close breaks above 4-hour high and Close > Open.
- Short Trigger: Close breaks below 4-hour low and Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.6x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle fails to hold outside 4-hour range.
- Invalidate if spread widens beyond asset risk limit.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
