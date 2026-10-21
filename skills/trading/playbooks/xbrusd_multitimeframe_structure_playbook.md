---
name: xbrusd_multitimeframe_structure_playbook
description: Multi-timeframe H4 trend & H1 CHoCH structure playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.8
status: active
sharpe_ratio: null
legacy_t_statistic: 5.93
profit_factor: 1.18
max_drawdown_pct: 13.1
win_rate: 0.431
---

# XBRUSD Empirical Playbook: Multi-Timeframe H4 Trend & H1 CHoCH Structure

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 5.93 (Zero-Lookahead simulation)
- **Profit Factor**: 1.18 (267 verified trade executions)
- **Max Drawdown**: 13.1% (Institutional risk profile)
- **Total PnL Return**: +30.9%
- **Win Rate**: 43.1% (Normalized at minimum 1:1.8 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.8x ATR, Max Holding = 16 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Higher timeframe alignment: H4 EMA 50 > H4 EMA 200 (Bull) or H4 EMA 50 < H4 EMA 200 (Bear).
- Long Trigger: In H4 bull trend, H1 breaks above 5-bar swing high with expanding volume.
- Short Trigger: In H4 bear trend, H1 breaks below 5-bar swing low with expanding volume.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.8 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if H1 prints opposing CHoCH breaking structural swing low/high.
- Invalidate if H4 trend structure flattens.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
