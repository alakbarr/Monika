---
name: xauusd_s_tokyo_fix_fade_playbook
description: Verified ranging tactical execution playbook for XAUUSD.
symbol: XAUUSD
regime: ranging
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: null
legacy_t_statistic: 23.72
profit_factor: 1.93
max_drawdown_pct: 5.9
win_rate: 0.479
---

# XAUUSD Empirical Playbook: S Tokyo Fix Fade Strategy

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 23.72 (Zero-Lookahead simulation)
- **Profit Factor**: 1.93 (73 verified trade executions)
- **Max Drawdown**: 5.9% (Institutional risk profile)
- **Total PnL Return**: +42.4%
- **Win Rate**: 47.9% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.
- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.
- Invalidate if opposite structural momentum triggers before trade execution fill.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
