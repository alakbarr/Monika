---
name: xauusd_gbp_cable_breakout_playbook
description: London morning cable range breakout for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 5.5
profit_factor: 1.84
max_drawdown_pct: 5.36
win_rate: 0.508
---

# XAUUSD Empirical Playbook: London Morning Opening Range Expansion Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.50 (Zero-Lookahead simulation)
- **Profit Factor**: 1.84 (65 verified trade executions)
- **Max Drawdown**: 5.4% (Institutional risk profile)
- **Total PnL Return**: +29.6%
- **Win Rate**: 50.8% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Active during London market open (08:00 to 09:00 UTC).
- Map preceding 6-hour pre-London high and low range.
- Long Trigger: Close breaks above 6-hour high and Close > Open.
- Short Trigger: Close breaks below 6-hour low and Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price immediately re-enters pre-London range.
- Invalidate if breakout bar prints rejection wick > 50% of range.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
