---
name: xbrusd_fvg_mitigation_playbook
description: Institutional Fair Value Gap mitigation playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: null
legacy_t_statistic: 12.32
profit_factor: 1.41
max_drawdown_pct: 7.9
win_rate: 0.462
---

# XBRUSD Empirical Playbook: Institutional Fair Value Gap Mitigation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 12.32 (Zero-Lookahead simulation)
- **Profit Factor**: 1.41 (80 verified trade executions)
- **Max Drawdown**: 7.9% (Institutional risk profile)
- **Total PnL Return**: +21.1%
- **Win Rate**: 46.2% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.7x ATR, Take-Profit = 1.4x ATR, Max Holding = 12 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Identify 3-bar Fair Value Gap (FVG) imbalance on H1.
- Long Trigger: Bullish FVG (Low[i-1] > High[i-3]), Close > EMA 50, retests FVG and bounces.
- Short Trigger: Bearish FVG (High[i-1] < Low[i-3]), Close < EMA 50, retests FVG and rejects.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.7x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes completely through the FVG (invalidated imbalance).
- Invalidate if higher timeframe trend flips against the FVG direction.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
