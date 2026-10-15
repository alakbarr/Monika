---
name: xbrusd_donchian_breakout_playbook
description: Volume-expanded Donchian channel breakout playbook for XBRUSD.
symbol: XBRUSD
regime: breakout
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 1.29
profit_factor: 1.14
max_drawdown_pct: 10.25
win_rate: 0.354
---

# XBRUSD Empirical Playbook: Volume-Expanded Donchian Channel Breakout

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.29 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (127 verified trade executions)
- **Max Drawdown**: 10.2% (Institutional risk profile)
- **Total PnL Return**: +10.8%
- **Win Rate**: 35.4% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Calculate 24-period Donchian Channel on H1 shifted by 1 bar to prevent lookahead.
- Long Trigger: H1 Close breaks above upper channel, Close > EMA 50, with volume >= 1.15x MA.
- Short Trigger: H1 Close breaks below lower channel, Close < EMA 50, with volume >= 1.15x MA.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle shows upper or lower rejection wick > 50% of range.
- Invalidate if price re-enters channel midpoint.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
