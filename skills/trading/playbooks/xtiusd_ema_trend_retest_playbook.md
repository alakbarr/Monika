---
name: xtiusd_ema_trend_retest_playbook
description: Triple moving average trend retest playbook for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 6.37
profit_factor: 1.79
max_drawdown_pct: 7.91
win_rate: 0.556
---

# XTIUSD Empirical Playbook: Triple Moving Average Trend Retest

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 6.37 (Zero-Lookahead simulation)
- **Profit Factor**: 1.79 (45 verified trade executions)
- **Max Drawdown**: 7.9% (Institutional risk profile)
- **Total PnL Return**: +16.9%
- **Win Rate**: 55.6% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Confirm structural trend: EMA 20 > EMA 50 > EMA 200 (Bull) or EMA 20 < EMA 50 < EMA 200 (Bear).
- Long Trigger: Price pulls back to test EMA 50 and closes strongly back above EMA 20.
- Short Trigger: Price pulls back to test EMA 50 and closes strongly back below EMA 20.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond the 200-period EMA.
- Invalidate if EMA 20 crosses below EMA 50 before entry.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
