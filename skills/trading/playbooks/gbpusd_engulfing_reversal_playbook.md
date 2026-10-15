---
name: gbpusd_engulfing_reversal_playbook
description: High-volume engulfing reversal pattern playbook for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 1.23
profit_factor: 1.13
max_drawdown_pct: 5.41
win_rate: 0.451
---

# GBPUSD Empirical Playbook: High-Volume Engulfing Reversal Pattern

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.23 (Zero-Lookahead simulation)
- **Profit Factor**: 1.13 (82 verified trade executions)
- **Max Drawdown**: 5.4% (Institutional risk profile)
- **Total PnL Return**: +5.2%
- **Win Rate**: 45.1% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Current candle body >= 1.2x previous candle body and >= 0.6x 14-period ATR.
- Long Trigger: Bearish candle followed by bullish engulfing closing above previous high with RSI <= 48.
- Short Trigger: Bullish candle followed by bearish engulfing closing below previous low with RSI >= 52.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if engulfing candle has an opposing wick > 40% of its body.
- Invalidate if the preceding trend was fewer than 3 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
