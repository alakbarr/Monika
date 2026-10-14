---
name: usdjpy_london_continuation_playbook
description: Mid-London session trend continuation playbook for USDJPY.
symbol: USDJPY
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 3.92
profit_factor: 1.24
max_drawdown_pct: 10.77
win_rate: 0.393
---

# USDJPY Empirical Playbook: Mid-London Session Trend Continuation

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.92 (Zero-Lookahead simulation)
- **Profit Factor**: 1.24 (84 verified trade executions)
- **Max Drawdown**: 10.8% (Institutional risk profile)
- **Total PnL Return**: +12.2%
- **Win Rate**: 39.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.6x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Active during established London trend hours (10:00 to 12:00 UTC).
- Long Trigger: EMA 20 > EMA 50, price pulls back to test EMA 20, and closes bullish.
- Short Trigger: EMA 20 < EMA 50, price pulls back to test EMA 20, and closes bearish.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50 during European midday.
- Invalidate before high-impact UK/European inflation or rate decisions.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
