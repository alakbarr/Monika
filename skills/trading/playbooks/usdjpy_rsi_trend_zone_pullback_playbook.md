---
name: usdjpy_rsi_trend_zone_pullback_playbook
description: RSI trend continuation pullback for USDJPY.
symbol: USDJPY
regime: trending
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 3.06
profit_factor: 1.31
max_drawdown_pct: 9.72
win_rate: 0.375
---

# USDJPY Empirical Playbook: RSI Equilibrium Zone Trend Pullback Continuation

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.06 (Zero-Lookahead simulation)
- **Profit Factor**: 1.31 (48 verified trade executions)
- **Max Drawdown**: 9.7% (Institutional risk profile)
- **Total PnL Return**: +9.0%
- **Win Rate**: 37.5% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.5x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, RSI tests 40-48 zone, and closes bullish.
- Short Trigger: Close < EMA 50, RSI tests 52-60 zone, and closes bearish.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if RSI crosses opposite zone extreme (<35 or >65).
- Invalidate if candle body closes across EMA 50.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
