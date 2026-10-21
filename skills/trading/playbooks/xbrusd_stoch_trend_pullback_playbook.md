---
name: xbrusd_stoch_trend_pullback_playbook
description: Stochastic trend pullback playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: null
legacy_t_statistic: 11.47
profit_factor: 1.36
max_drawdown_pct: 13.5
win_rate: 0.484
---

# XBRUSD Empirical Playbook: Stochastic Trend Retest & Dynamic Continuation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 11.47 (Zero-Lookahead simulation)
- **Profit Factor**: 1.36 (159 verified trade executions)
- **Max Drawdown**: 13.5% (Institutional risk profile)
- **Total PnL Return**: +35.0%
- **Win Rate**: 48.4% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.0x ATR, Max Holding = 18 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, Stoch %K <= 32, turns above %D, Close > Open.
- Short Trigger: Close < EMA 50, Stoch %K >= 68, turns below %D, Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price breaks across EMA 50 before entry execution.
- Invalidate if Stochastic indicator remains pinned at opposing extreme.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
