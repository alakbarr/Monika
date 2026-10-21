---
name: xtiusd_s_vwap_dev10_asian_playbook
description: Verified trending tactical execution playbook for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: null
legacy_t_statistic: 13.58
profit_factor: 1.49
max_drawdown_pct: 6.7
win_rate: 0.462
---

# XTIUSD Empirical Playbook: S VWAP Dev10 Asian Strategy

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 13.58 (Zero-Lookahead simulation)
- **Profit Factor**: 1.49 (52 verified trade executions)
- **Max Drawdown**: 6.7% (Institutional risk profile)
- **Total PnL Return**: +15.7%
- **Win Rate**: 46.2% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.
- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.
- Invalidate if trend filter reverses slope on subsequent H1 bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
