---
name: xtiusd_ema_ribbon_touch_playbook
description: Dynamic EMA ribbon pullback & touch playbook for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.8
status: active
sharpe_ratio: null
legacy_t_statistic: 6.74
profit_factor: 1.2
max_drawdown_pct: 15.0
win_rate: 0.42
---

# XTIUSD Empirical Playbook: Dynamic EMA Ribbon Pullback & Touch

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 6.74 (Zero-Lookahead simulation)
- **Profit Factor**: 1.20 (238 verified trade executions)
- **Max Drawdown**: 15.0% (Institutional risk profile)
- **Total PnL Return**: +30.9%
- **Win Rate**: 42.0% (Normalized at minimum 1:1.8 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.8x ATR, Max Holding = 16 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Trend filter: EMA 20 > EMA 50 (Bull) or EMA 20 < EMA 50 (Bear).
- Long Trigger: Low touches EMA 20, rejects, and candle closes higher than open.
- Short Trigger: High touches EMA 20, rejects, and candle closes lower than open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.8 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes beyond EMA 50.
- Invalidate if EMA 20 slope flattens.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
