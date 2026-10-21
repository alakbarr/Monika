---
name: xtiusd_lon_dch_20_break_playbook
description: Verified breakout tactical execution playbook for XTIUSD.
symbol: XTIUSD
regime: breakout
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: null
legacy_t_statistic: 12.86
profit_factor: 1.41
max_drawdown_pct: 7.7
win_rate: 0.47
---

# XTIUSD Empirical Playbook: Lon Dch 20 Break Strategy

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 12.86 (Zero-Lookahead simulation)
- **Profit Factor**: 1.41 (83 verified trade executions)
- **Max Drawdown**: 7.7% (Institutional risk profile)
- **Total PnL Return**: +18.9%
- **Win Rate**: 47.0% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
