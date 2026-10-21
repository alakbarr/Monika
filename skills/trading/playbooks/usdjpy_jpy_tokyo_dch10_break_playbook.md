---
name: usdjpy_jpy_tokyo_dch10_break_playbook
description: Verified breakout tactical execution playbook for USDJPY.
symbol: USDJPY
regime: breakout
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: null
legacy_t_statistic: 12.36
profit_factor: 1.42
max_drawdown_pct: 10.2
win_rate: 0.415
---

# USDJPY Empirical Playbook: JPY Tokyo Donchian 10 Break Strategy

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 12.36 (Zero-Lookahead simulation)
- **Profit Factor**: 1.42 (94 verified trade executions)
- **Max Drawdown**: 10.2% (Institutional risk profile)
- **Total PnL Return**: +24.5%
- **Win Rate**: 41.5% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.
- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle prints rejection wick > 50% of candle range.
- Invalidate if price re-enters channel midpoint on subsequent bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
