---
name: xauusd_asian_range_fade_playbook
description: Asian range boundary mean reversion playbook for XAUUSD.
symbol: XAUUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: null
legacy_t_statistic: 17.67
profit_factor: 1.64
max_drawdown_pct: 5.9
win_rate: 0.445
---

# XAUUSD Empirical Playbook: Asian Range Boundary Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Legacy Risk-Adjusted Statistic (t-statistic, not a Sharpe ratio)**: 17.67 (Zero-Lookahead simulation)
- **Profit Factor**: 1.64 (119 verified trade executions)
- **Max Drawdown**: 5.9% (Institutional risk profile)
- **Total PnL Return**: +51.1%
- **Win Rate**: 44.5% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 2.8x ATR, Max Holding = 24 bars
- **Statistical Reliability**: CAUTION: the legacy risk-adjusted figure above is a t-statistic, not an annualised Sharpe ratio, and it is based on a small in-sample window. Regenerate this playbook on a live terminal before relying on it.

## Trigger Conditions & Tactical Directives
- Active during low-volatility Asian hours (23:00 to 05:00 UTC).
- Compute rolling 8-hour range high and low extremes.
- Short Trigger: Price tests 99.95% of Asian high and prints a bearish rejection candle.
- Long Trigger: Price tests 100.05% of Asian low and prints a bullish rejection candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate immediately if volume spikes > 2.0x volume MA indicating breakout regime.
- Invalidate if trade is held past European open (06:00 UTC).
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
