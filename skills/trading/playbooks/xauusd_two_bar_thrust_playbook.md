---
name: xauusd_two_bar_thrust_playbook
description: Two-bar consecutive momentum thrust for XAUUSD.
symbol: XAUUSD
regime: trending
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 3.42
profit_factor: 1.32
max_drawdown_pct: 14.08
win_rate: 0.363
---

# XAUUSD Empirical Playbook: Two-Bar Consecutive Momentum Range Thrust

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.42 (Zero-Lookahead simulation)
- **Profit Factor**: 1.32 (171 verified trade executions)
- **Max Drawdown**: 14.1% (Institutional risk profile)
- **Total PnL Return**: +39.4%
- **Win Rate**: 36.3% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Two consecutive directional bars with bodies >= 0.5x 14-period ATR.
- Long Trigger: Bar[i-1] and Bar[i] close higher, and Close breaks Bar[i-1] high.
- Short Trigger: Bar[i-1] and Bar[i] close lower, and Close breaks Bar[i-1] low.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if subsequent bar immediately retraces > 50% of thrust range.
- Invalidate if volume contracts significantly on second bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
