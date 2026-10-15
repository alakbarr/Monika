---
name: btcusd_asian_lunch_drift_playbook
description: Asian midday institutional drift for BTCUSD.
symbol: BTCUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.86
profit_factor: 1.27
max_drawdown_pct: 13.13
win_rate: 0.41
---

# BTCUSD Empirical Playbook: Asian Midday Institutional Drift Continuation

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.86 (Zero-Lookahead simulation)
- **Profit Factor**: 1.27 (183 verified trade executions)
- **Max Drawdown**: 13.1% (Institutional risk profile)
- **Total PnL Return**: +29.4%
- **Win Rate**: 41.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Active during quiet Asian midday window (04:00 to 06:00 UTC).
- Long Trigger: Close > EMA 20, Close > Open, and RSI >= 50.
- Short Trigger: Close < EMA 20, Close < Open, and RSI <= 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if European pre-market orderflow disrupts trend before 06:00 UTC.
- Invalidate if price crosses back across the 20-period EMA.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
