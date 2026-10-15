---
name: xbrusd_stoch_trend_pullback_playbook
description: Stochastic trend pullback playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 3.79
profit_factor: 1.28
max_drawdown_pct: 13.22
win_rate: 0.485
---

# XBRUSD Empirical Playbook: Stochastic Trend Retest & Dynamic Continuation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.79 (Zero-Lookahead simulation)
- **Profit Factor**: 1.28 (167 verified trade executions)
- **Max Drawdown**: 13.2% (Institutional risk profile)
- **Total PnL Return**: +26.5%
- **Win Rate**: 48.5% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 1.8x ATR, Max Holding = 16 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, Stoch %K <= 32, turns above %D, Close > Open.
- Short Trigger: Close < EMA 50, Stoch %K >= 68, turns below %D, Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price breaks across EMA 50 before entry execution.
- Invalidate if Stochastic indicator remains pinned at opposing extreme.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
