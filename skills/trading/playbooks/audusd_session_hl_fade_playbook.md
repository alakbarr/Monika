---
name: audusd_session_hl_fade_playbook
description: Rolling 24-hour high and low rejection fade for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 0.37
profit_factor: 1.04
max_drawdown_pct: 14.77
win_rate: 0.364
---

# AUDUSD Empirical Playbook: Rolling 24-Hour High/Low Rejection Fade

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.37 (Zero-Lookahead simulation)
- **Profit Factor**: 1.04 (165 verified trade executions)
- **Max Drawdown**: 14.8% (Institutional risk profile)
- **Total PnL Return**: +2.7%
- **Win Rate**: 36.4% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Map rolling 24-hour swing high and low extremes.
- Long Trigger: Price touches or sweeps 24-hour low and closes back above it.
- Short Trigger: Price touches or sweeps 24-hour high and closes back below it.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body prints a full breakout close beyond the 24-hour extreme.
- Invalidate during major scheduled interest rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
