---
name: xbrusd_ema_stoch_confluence_playbook
description: EMA trend and stochastic momentum confluence for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.83
status: active
sharpe_ratio: 2.11
profit_factor: 1.17
max_drawdown_pct: 13.28
win_rate: 0.43
---

# XBRUSD Empirical Playbook: EMA Trend & Stochastic Momentum Confluence

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.11 (Zero-Lookahead simulation)
- **Profit Factor**: 1.17 (100 verified trade executions)
- **Max Drawdown**: 13.3% (Institutional risk profile)
- **Total PnL Return**: +9.7%
- **Win Rate**: 43.0% (Normalized at minimum 1:1.83 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.2x ATR, Max Holding = 18 bars

## Trigger Conditions & Tactical Directives
- Trend filter: Close > EMA 50 (Bull) or Close < EMA 50 (Bear).
- Long Trigger: Stochastic %K crosses above %D below 45, and candle closes higher than open.
- Short Trigger: Stochastic %K crosses below %D above 55, and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.83 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if Stochastic %K recrosses %D within 2 bars.
- Invalidate if price falls across EMA 50.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
