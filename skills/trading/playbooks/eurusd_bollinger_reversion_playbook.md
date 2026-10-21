---
name: eurusd_bollinger_reversion_playbook
description: Bollinger Bands volatility mean reversion playbook for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 5.57
profit_factor: 1.17
max_drawdown_pct: 12.5
win_rate: 0.406
---

# EURUSD Empirical Playbook: Bollinger Bands Volatility Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 5.57 (Zero-Lookahead simulation)
- **Profit Factor**: 1.17 (155 verified trade executions)
- **Max Drawdown**: 12.5% (Institutional risk profile)
- **Total PnL Return**: +15.1%
- **Win Rate**: 40.6% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.4x ATR, Max Holding = 20 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Calculate 20-period Bollinger Bands (2.0 standard deviations) on H1.
- Long Trigger: H1 Low pierces lower band, closes back inside, Close > Open, and RSI <= 42.
- Short Trigger: H1 High pierces upper band, closes back inside, Close < Open, and RSI >= 58.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if band width contracts below 0.25% indicating volatility squeeze rather than range.
- Invalidate if price closes consecutively outside the bands.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
