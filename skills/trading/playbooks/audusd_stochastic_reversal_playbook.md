---
name: audusd_stochastic_reversal_playbook
description: Stochastic oscillator exhaustion reversal for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 0.61
profit_factor: 1.06
max_drawdown_pct: 14.39
win_rate: 0.418
---

# AUDUSD Empirical Playbook: Stochastic Oscillator Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.61 (Zero-Lookahead simulation)
- **Profit Factor**: 1.06 (251 verified trade executions)
- **Max Drawdown**: 14.4% (Institutional risk profile)
- **Total PnL Return**: +7.1%
- **Win Rate**: 41.8% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Calculate Stochastic Oscillator (14, 3, 3) on H1.
- Long Trigger: Stochastic %K <= 22, crosses above %D, and candle closes higher than open.
- Short Trigger: Stochastic %K >= 78, crosses below %D, and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price continues trending against signal while Stochastic stays pinned.
- Invalidate if entry candle fails to close in direction of reversal.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
