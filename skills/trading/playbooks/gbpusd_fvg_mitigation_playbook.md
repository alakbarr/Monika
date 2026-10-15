---
name: gbpusd_fvg_mitigation_playbook
description: Institutional Fair Value Gap mitigation playbook for GBPUSD.
symbol: GBPUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.78
profit_factor: 1.33
max_drawdown_pct: 6.42
win_rate: 0.417
---

# GBPUSD Empirical Playbook: Institutional Fair Value Gap Mitigation

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.78 (Zero-Lookahead simulation)
- **Profit Factor**: 1.33 (60 verified trade executions)
- **Max Drawdown**: 6.4% (Institutional risk profile)
- **Total PnL Return**: +11.5%
- **Win Rate**: 41.7% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Identify 3-bar Fair Value Gap (FVG) imbalance on H1.
- Long Trigger: Bullish FVG (Low[i-1] > High[i-3]), Close > EMA 50, retests FVG and bounces.
- Short Trigger: Bearish FVG (High[i-1] < Low[i-3]), Close < EMA 50, retests FVG and rejects.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes completely through the FVG (invalidated imbalance).
- Invalidate if higher timeframe trend flips against the FVG direction.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
