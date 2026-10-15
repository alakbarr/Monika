---
name: xbrusd_macd_zero_cross_playbook
description: MACD zero-line momentum expansion playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 1.89
profit_factor: 1.17
max_drawdown_pct: 7.8
win_rate: 0.444
---

# XBRUSD Empirical Playbook: MACD Zero-Line Momentum Expansion

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.89 (Zero-Lookahead simulation)
- **Profit Factor**: 1.17 (108 verified trade executions)
- **Max Drawdown**: 7.8% (Institutional risk profile)
- **Total PnL Return**: +9.8%
- **Win Rate**: 44.4% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Calculate MACD (12, 26, 9) on H1.
- Long Trigger: MACD line crosses strictly above zero line, Histogram > 0, and Close > EMA 50.
- Short Trigger: MACD line crosses strictly below zero line, Histogram < 0, and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if MACD histogram prints a declining bar within 2 bars of entry.
- Invalidate if price falls back across EMA 50.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
