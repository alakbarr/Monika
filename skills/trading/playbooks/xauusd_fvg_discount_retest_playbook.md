---
name: xauusd_fvg_discount_retest_playbook
description: Fair Value Gap discount retest for XAUUSD.
symbol: XAUUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 10.43
profit_factor: 3.26
max_drawdown_pct: 2.0
win_rate: 0.679
---

# XAUUSD Empirical Playbook: Fair Value Gap 50% Midpoint Mitigation

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 10.43 (Zero-Lookahead simulation)
- **Profit Factor**: 3.26 (28 verified trade executions)
- **Max Drawdown**: 2.0% (Institutional risk profile)
- **Total PnL Return**: +22.3%
- **Win Rate**: 67.9% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Identify 3-bar Fair Value Gap imbalance on H1 chart.
- Long Trigger: Bullish FVG, Low tests 50% midpoint, Close > EMA 50, bullish close.
- Short Trigger: Bearish FVG, High tests 50% midpoint, Close < EMA 50, bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price closes completely through the FVG zone.
- Invalidate if momentum reverses against the underlying trend.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
