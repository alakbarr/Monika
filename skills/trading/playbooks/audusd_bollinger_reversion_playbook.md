---
name: audusd_bollinger_reversion_playbook
description: Bollinger Bands volatility mean reversion playbook for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 6.72
profit_factor: 1.2
max_drawdown_pct: 11.5
win_rate: 0.403
---

# AUDUSD Empirical Playbook: Bollinger Bands Volatility Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 6.72 (Zero-Lookahead simulation)
- **Profit Factor**: 1.20 (144 verified trade executions)
- **Max Drawdown**: 11.5% (Institutional risk profile)
- **Total PnL Return**: +17.5%
- **Win Rate**: 40.3% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Calculate 20-period Bollinger Bands (2.0 standard deviations) on H1.
- Long Trigger: H1 Low pierces lower band, closes back inside, Close > Open, and RSI <= 42.
- Short Trigger: H1 High pierces upper band, closes back inside, Close < Open, and RSI >= 58.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if band width contracts below 0.25% indicating volatility squeeze rather than range.
- Invalidate if price closes consecutively outside the bands.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
