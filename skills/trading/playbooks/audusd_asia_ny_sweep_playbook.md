---
name: audusd_asia_ny_sweep_playbook
description: Asian high/low sweep during New York open for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.66
profit_factor: 1.15
max_drawdown_pct: 5.91
win_rate: 0.4
---

# AUDUSD Empirical Playbook: Asian High/Low Sweep During New York Open

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.66 (Zero-Lookahead simulation)
- **Profit Factor**: 1.15 (35 verified trade executions)
- **Max Drawdown**: 5.9% (Institutional risk profile)
- **Total PnL Return**: +3.1%
- **Win Rate**: 40.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.0x ATR, Max Holding = 16 bars

## Trigger Conditions & Tactical Directives
- Active during New York opening session (13:00 to 15:00 UTC).
- Map the 24-hour Asian high and low liquidity boundaries.
- Short Trigger: High sweeps above Asian high, rejects, and closes back below it.
- Long Trigger: Low sweeps below Asian low, rejects, and closes back above it.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if New York volume drives a full body close beyond the Asian boundary.
- Invalidate during major US FOMC interest rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
