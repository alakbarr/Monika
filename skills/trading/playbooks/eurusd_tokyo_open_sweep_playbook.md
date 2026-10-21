---
name: eurusd_tokyo_open_sweep_playbook
description: Tokyo open liquidity sweep playbook for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 37.56
profit_factor: 2.71
max_drawdown_pct: 3.0
win_rate: 0.567
---

# EURUSD Empirical Playbook: Tokyo Open Session Liquidity Sweep

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 37.56 (Zero-Lookahead simulation)
- **Profit Factor**: 2.71 (30 verified trade executions)
- **Max Drawdown**: 3.0% (Institutional risk profile)
- **Total PnL Return**: +23.4%
- **Win Rate**: 56.7% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.0x ATR, Max Holding = 16 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Active during Tokyo open hours between 00:00 and 02:00 UTC.
- Map rolling 12-hour high and low liquidity extremes.
- Long Trigger: Low sweeps 12-hour low, closes back inside with bullish candle.
- Short Trigger: High sweeps 12-hour high, closes back inside with bearish candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes consecutively beyond swept extreme.
- Invalidate if volume surge exceeds 2.5x volume MA.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
