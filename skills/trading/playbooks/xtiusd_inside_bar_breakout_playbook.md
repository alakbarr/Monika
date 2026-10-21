---
name: xtiusd_inside_bar_breakout_playbook
description: Inside bar compression volatility breakout for XTIUSD.
symbol: XTIUSD
regime: breakout
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: null
legacy_t_statistic: 5.24
profit_factor: 1.15
max_drawdown_pct: 14.3
win_rate: 0.454
---

# XTIUSD Empirical Playbook: Inside Bar Compression Volatility Breakout

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 5.24 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (216 verified trade executions)
- **Max Drawdown**: 14.3% (Institutional risk profile)
- **Total PnL Return**: +17.8%
- **Win Rate**: 45.4% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Identify Inside Bar: High[i-1] <= High[i-2] and Low[i-1] >= Low[i-2].
- Long Trigger: H1 Close breaks strictly above inside bar high and Close > EMA 50.
- Short Trigger: H1 Close breaks strictly below inside bar low and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout bar fails to close beyond the mother bar boundary.
- Invalidate if price chops inside the range for more than 4 bars after signal.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
