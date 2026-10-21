---
name: usdjpy_aud_us_close_reversion_playbook
description: US session close range exhaustion reversion for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.14
status: active
sharpe_ratio: null
legacy_t_statistic: 13.43
profit_factor: 1.46
max_drawdown_pct: 6.0
win_rate: 0.442
---

# USDJPY Empirical Playbook: US Session Close Range Exhaustion Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 13.43 (Zero-Lookahead simulation)
- **Profit Factor**: 1.46 (77 verified trade executions)
- **Max Drawdown**: 6.0% (Institutional risk profile)
- **Total PnL Return**: +21.2%
- **Win Rate**: 44.2% (Normalized at minimum 1:2.14 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.7x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Active during US session close window (20:00 to 22:00 UTC) ahead of Sydney open.
- Long Trigger: RSI <= 42 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 58 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.14 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.7x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if unexpected geopolitical news breaks during market rollover.
- Invalidate if spread widens beyond 3.0 pips during 21:00-22:00 UTC transition.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
