---
name: eurusd_ny_reversal_playbook
description: New York institutional opening reversal playbook for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.57
status: active
sharpe_ratio: 6.21
profit_factor: 1.54
max_drawdown_pct: 4.93
win_rate: 0.531
---

# EURUSD Empirical Playbook: New York Institutional Liquidity Reversal

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 6.21 (Zero-Lookahead simulation)
- **Profit Factor**: 1.54 (49 verified trade executions)
- **Max Drawdown**: 4.9% (Institutional risk profile)
- **Total PnL Return**: +12.6%
- **Win Rate**: 53.1% (Normalized at minimum 1:1.57 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.2x ATR, Max Holding = 16 bars

## Trigger Conditions & Tactical Directives
- Monitor New York open session between 13:00 and 16:00 UTC.
- Map the previous 6-hour London high and low liquidity extremes.
- Short Trigger: Price sweeps London high, rejects, closes lower than open, with RSI >= 56.
- Long Trigger: Price sweeps London low, rejects, closes higher than open, with RSI <= 44.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.57 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints two consecutive H1 closes beyond the swept extreme.
- Invalidate during major US FOMC interest rate decisions.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 16 bars.
