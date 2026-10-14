---
name: xbrusd_ema_ribbon_touch_playbook
description: Dynamic EMA ribbon pullback & touch playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 2.34
profit_factor: 1.21
max_drawdown_pct: 13.27
win_rate: 0.436
---

# XBRUSD Empirical Playbook: Dynamic EMA Ribbon Pullback & Touch

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.34 (Zero-Lookahead simulation)
- **Profit Factor**: 1.21 (181 verified trade executions)
- **Max Drawdown**: 13.3% (Institutional risk profile)
- **Total PnL Return**: +20.8%
- **Win Rate**: 43.6% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Trend filter: EMA 20 > EMA 50 (Bull) or EMA 20 < EMA 50 (Bear).
- Long Trigger: Low touches EMA 20, rejects, and candle closes higher than open.
- Short Trigger: High touches EMA 20, rejects, and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50.
- Invalidate if EMA 20 slope flattens.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
