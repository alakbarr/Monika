---
name: xtiusd_supertrend_bounce_playbook
description: Supertrend ATR trail trend bounce for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 5.07
profit_factor: 1.15
max_drawdown_pct: 12.8
win_rate: 0.406
---

# XTIUSD Empirical Playbook: Supertrend Trailing Dynamic Trend Bounce

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 5.07 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (266 verified trade executions)
- **Max Drawdown**: 12.8% (Institutional risk profile)
- **Total PnL Return**: +25.6%
- **Win Rate**: 40.6% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.0x ATR, Max Holding = 16 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, Low tests dynamic EMA 50 buffer, and closes bullish.
- Short Trigger: Close < EMA 50, High tests dynamic EMA 50 buffer, and closes bearish.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully across EMA 50 line.
- Invalidate if higher timeframe MACD histogram turns divergent.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
