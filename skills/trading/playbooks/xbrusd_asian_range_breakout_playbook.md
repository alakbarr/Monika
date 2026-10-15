---
name: xbrusd_asian_range_breakout_playbook
description: Asian session box expansion breakout playbook for XBRUSD.
symbol: XBRUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.75
profit_factor: 1.19
max_drawdown_pct: 8.46
win_rate: 0.4
---

# XBRUSD Empirical Playbook: Asian Session Box Expansion Breakout

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.75 (Zero-Lookahead simulation)
- **Profit Factor**: 1.19 (45 verified trade executions)
- **Max Drawdown**: 8.5% (Institutional risk profile)
- **Total PnL Return**: +5.0%
- **Win Rate**: 40.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Identify the Asian consolidation high and low between 00:00 and 06:00 UTC.
- Long Trigger: H1 Close at 07:00 or 08:00 UTC breaks above Asian high and Close > EMA 50.
- Short Trigger: H1 Close at 07:00 or 08:00 UTC breaks below Asian low and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate setup if price prints an immediate false-break rejection pinbar back inside the range.
- Invalidate if volume fails to expand on the breakout bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
