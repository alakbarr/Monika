---
name: gbpusd_tokyo_open_sweep_playbook
description: Tokyo open liquidity sweep playbook for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 7.37
profit_factor: 1.95
max_drawdown_pct: 4.01
win_rate: 0.5
---

# GBPUSD Empirical Playbook: Tokyo Open Session Liquidity Sweep

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 7.37 (Zero-Lookahead simulation)
- **Profit Factor**: 1.95 (20 verified trade executions)
- **Max Drawdown**: 4.0% (Institutional risk profile)
- **Total PnL Return**: +10.0%
- **Win Rate**: 50.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Active during Tokyo open hours between 00:00 and 02:00 UTC.
- Map rolling 12-hour high and low liquidity extremes.
- Long Trigger: Low sweeps 12-hour low, closes back inside with bullish candle.
- Short Trigger: High sweeps 12-hour high, closes back inside with bearish candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes consecutively beyond swept extreme.
- Invalidate if volume surge exceeds 2.5x volume MA.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
