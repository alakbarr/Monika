---
name: xauusd_donchian_breakout_playbook
description: Volume-expanded Donchian channel breakout playbook for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 5.02
profit_factor: 1.48
max_drawdown_pct: 7.62
win_rate: 0.404
---

# XAUUSD Empirical Playbook: Volume-Expanded Donchian Channel Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.02 (Zero-Lookahead simulation)
- **Profit Factor**: 1.48 (141 verified trade executions)
- **Max Drawdown**: 7.6% (Institutional risk profile)
- **Total PnL Return**: +48.4%
- **Win Rate**: 40.4% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 22 bars

## Trigger Conditions & Tactical Directives
- Calculate 24-period Donchian Channel on H1 shifted by 1 bar to prevent lookahead.
- Long Trigger: H1 Close breaks above upper channel, Close > EMA 50, with volume >= 1.15x MA.
- Short Trigger: H1 Close breaks below lower channel, Close < EMA 50, with volume >= 1.15x MA.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle shows upper or lower rejection wick > 50% of range.
- Invalidate if price re-enters channel midpoint.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 22 bars.
