---
name: btcusd_london_continuation_playbook
description: Mid-London session trend continuation playbook for BTCUSD.
symbol: BTCUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.94
profit_factor: 1.24
max_drawdown_pct: 9.05
win_rate: 0.4
---

# BTCUSD Empirical Playbook: Mid-London Session Trend Continuation

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.94 (Zero-Lookahead simulation)
- **Profit Factor**: 1.24 (85 verified trade executions)
- **Max Drawdown**: 9.1% (Institutional risk profile)
- **Total PnL Return**: +11.8%
- **Win Rate**: 40.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 18 bars

## Trigger Conditions & Tactical Directives
- Active during established London trend hours (10:00 to 12:00 UTC).
- Long Trigger: EMA 20 > EMA 50, price pulls back to test EMA 20, and closes bullish.
- Short Trigger: EMA 20 < EMA 50, price pulls back to test EMA 20, and closes bearish.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50 during European midday.
- Invalidate before high-impact UK/European inflation or rate decisions.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 18 bars.
