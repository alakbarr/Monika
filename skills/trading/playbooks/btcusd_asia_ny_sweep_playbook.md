---
name: btcusd_asia_ny_sweep_playbook
description: Asian high/low sweep during New York open for BTCUSD.
symbol: BTCUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 4.26
profit_factor: 1.45
max_drawdown_pct: 3.44
win_rate: 0.533
---

# BTCUSD Empirical Playbook: Asian High/Low Sweep During New York Open

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.26 (Zero-Lookahead simulation)
- **Profit Factor**: 1.45 (30 verified trade executions)
- **Max Drawdown**: 3.4% (Institutional risk profile)
- **Total PnL Return**: +6.5%
- **Win Rate**: 53.3% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Active during New York opening session (13:00 to 15:00 UTC).
- Map the 24-hour Asian high and low liquidity boundaries.
- Short Trigger: High sweeps above Asian high, rejects, and closes back below it.
- Long Trigger: Low sweeps below Asian low, rejects, and closes back above it.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if New York volume drives a full body close beyond the Asian boundary.
- Invalidate during major US FOMC interest rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
