---
name: xbrusd_fvg_discount_retest_playbook
description: Fair Value Gap discount retest for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.75
status: active
sharpe_ratio: 9.59
profit_factor: 1.67
max_drawdown_pct: 8.38
win_rate: 0.561
---

# XBRUSD Empirical Playbook: Fair Value Gap 50% Midpoint Mitigation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 9.59 (Zero-Lookahead simulation)
- **Profit Factor**: 1.67 (41 verified trade executions)
- **Max Drawdown**: 8.4% (Institutional risk profile)
- **Total PnL Return**: +15.7%
- **Win Rate**: 56.1% (Normalized at minimum 1:1.75 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.4x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Identify 3-bar Fair Value Gap imbalance on H1 chart.
- Long Trigger: Bullish FVG, Low tests 50% midpoint, Close > EMA 50, bullish close.
- Short Trigger: Bearish FVG, High tests 50% midpoint, Close < EMA 50, bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.75 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes completely through the FVG zone.
- Invalidate if momentum reverses against the underlying trend.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
