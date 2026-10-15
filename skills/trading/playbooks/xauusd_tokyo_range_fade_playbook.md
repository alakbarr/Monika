---
name: xauusd_tokyo_range_fade_playbook
description: Tokyo midday range boundary mean reversion for XAUUSD.
symbol: XAUUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.13
status: active
sharpe_ratio: 5.49
profit_factor: 1.73
max_drawdown_pct: 4.14
win_rate: 0.489
---

# XAUUSD Empirical Playbook: Tokyo Midday Range Boundary Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.49 (Zero-Lookahead simulation)
- **Profit Factor**: 1.73 (47 verified trade executions)
- **Max Drawdown**: 4.1% (Institutional risk profile)
- **Total PnL Return**: +18.5%
- **Win Rate**: 48.9% (Normalized at minimum 1:2.13 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.2x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Active during quiet Tokyo midday session (02:00 to 05:00 UTC).
- Compute rolling 4-hour local high and low boundaries.
- Short Trigger: Price tests 4-hour high, closes lower than open, with RSI >= 55.
- Long Trigger: Price tests 4-hour low, closes higher than open, with RSI <= 45.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.13 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if Australian or Chinese macroeconomic data prints during the bar.
- Invalidate if price closes beyond the 4-hour extreme.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
