---
name: xbrusd_fvg_mitigation_playbook
description: Institutional Fair Value Gap mitigation playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 3.12
profit_factor: 1.33
max_drawdown_pct: 8.85
win_rate: 0.405
---

# XBRUSD Empirical Playbook: Institutional Fair Value Gap Mitigation

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.12 (Zero-Lookahead simulation)
- **Profit Factor**: 1.33 (74 verified trade executions)
- **Max Drawdown**: 8.8% (Institutional risk profile)
- **Total PnL Return**: +15.7%
- **Win Rate**: 40.5% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Identify 3-bar Fair Value Gap (FVG) imbalance on H1.
- Long Trigger: Bullish FVG (Low[i-1] > High[i-3]), Close > EMA 50, retests FVG and bounces.
- Short Trigger: Bearish FVG (High[i-1] < Low[i-3]), Close < EMA 50, retests FVG and rejects.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes completely through the FVG (invalidated imbalance).
- Invalidate if higher timeframe trend flips against the FVG direction.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
