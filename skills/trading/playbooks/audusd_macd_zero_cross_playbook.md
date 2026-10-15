---
name: audusd_macd_zero_cross_playbook
description: MACD zero-line momentum expansion playbook for AUDUSD.
symbol: AUDUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 0.88
profit_factor: 1.1
max_drawdown_pct: 13.75
win_rate: 0.375
---

# AUDUSD Empirical Playbook: MACD Zero-Line Momentum Expansion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.88 (Zero-Lookahead simulation)
- **Profit Factor**: 1.10 (96 verified trade executions)
- **Max Drawdown**: 13.8% (Institutional risk profile)
- **Total PnL Return**: +5.1%
- **Win Rate**: 37.5% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Calculate MACD (12, 26, 9) on H1.
- Long Trigger: MACD line crosses strictly above zero line, Histogram > 0, and Close > EMA 50.
- Short Trigger: MACD line crosses strictly below zero line, Histogram < 0, and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if MACD histogram prints a declining bar within 2 bars of entry.
- Invalidate if price falls back across EMA 50.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
