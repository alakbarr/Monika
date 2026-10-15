---
name: audusd_consecutive_exhaustion_playbook
description: Four-bar momentum exhaustion reversal for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.13
profit_factor: 1.13
max_drawdown_pct: 11.35
win_rate: 0.409
---

# AUDUSD Empirical Playbook: Four-Bar Momentum Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.13 (Zero-Lookahead simulation)
- **Profit Factor**: 1.13 (93 verified trade executions)
- **Max Drawdown**: 11.3% (Institutional risk profile)
- **Total PnL Return**: +6.9%
- **Win Rate**: 40.9% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.6x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Four consecutive bearish bars with RSI <= 40 followed by bullish close.
- Short Trigger: Four consecutive bullish bars with RSI >= 60 followed by bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.6x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a new extreme beyond the 4-bar exhaustion high/low.
- Invalidate during major scheduled central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
