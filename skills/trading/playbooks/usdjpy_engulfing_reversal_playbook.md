---
name: usdjpy_engulfing_reversal_playbook
description: High-volume engulfing reversal pattern playbook for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 1.27
profit_factor: 1.13
max_drawdown_pct: 14.86
win_rate: 0.304
---

# USDJPY Empirical Playbook: High-Volume Engulfing Reversal Pattern

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.27 (Zero-Lookahead simulation)
- **Profit Factor**: 1.13 (69 verified trade executions)
- **Max Drawdown**: 14.9% (Institutional risk profile)
- **Total PnL Return**: +5.5%
- **Win Rate**: 30.4% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Current candle body >= 1.2x previous candle body and >= 0.6x 14-period ATR.
- Long Trigger: Bearish candle followed by bullish engulfing closing above previous high with RSI <= 48.
- Short Trigger: Bullish candle followed by bearish engulfing closing below previous low with RSI >= 52.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if engulfing candle has an opposing wick > 40% of its body.
- Invalidate if the preceding trend was fewer than 3 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
