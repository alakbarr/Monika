---
name: audusd_tokyo_open_sweep_playbook
description: Tokyo open liquidity sweep playbook for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 0.62
profit_factor: 1.07
max_drawdown_pct: 7.01
win_rate: 0.371
---

# AUDUSD Empirical Playbook: Tokyo Open Session Liquidity Sweep

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.62 (Zero-Lookahead simulation)
- **Profit Factor**: 1.07 (35 verified trade executions)
- **Max Drawdown**: 7.0% (Institutional risk profile)
- **Total PnL Return**: +1.3%
- **Win Rate**: 37.1% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Active during Tokyo open hours between 00:00 and 02:00 UTC.
- Map rolling 12-hour high and low liquidity extremes.
- Long Trigger: Low sweeps 12-hour low, closes back inside with bullish candle.
- Short Trigger: High sweeps 12-hour high, closes back inside with bearish candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes consecutively beyond swept extreme.
- Invalidate if volume surge exceeds 2.5x volume MA.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
