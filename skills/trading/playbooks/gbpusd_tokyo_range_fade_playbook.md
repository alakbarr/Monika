---
name: gbpusd_tokyo_range_fade_playbook
description: Tokyo midday range boundary mean reversion for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 4.76
profit_factor: 1.7
max_drawdown_pct: 4.73
win_rate: 0.479
---

# GBPUSD Empirical Playbook: Tokyo Midday Range Boundary Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.76 (Zero-Lookahead simulation)
- **Profit Factor**: 1.70 (48 verified trade executions)
- **Max Drawdown**: 4.7% (Institutional risk profile)
- **Total PnL Return**: +18.7%
- **Win Rate**: 47.9% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Active during quiet Tokyo midday session (02:00 to 05:00 UTC).
- Compute rolling 4-hour local high and low boundaries.
- Short Trigger: Price tests 4-hour high, closes lower than open, with RSI >= 55.
- Long Trigger: Price tests 4-hour low, closes higher than open, with RSI <= 45.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if Australian or Chinese macroeconomic data prints during the bar.
- Invalidate if price closes beyond the 4-hour extreme.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
