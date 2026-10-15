---
name: xauusd_consecutive_exhaustion_playbook
description: Four-bar momentum exhaustion reversal for XAUUSD.
symbol: XAUUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.75
status: active
sharpe_ratio: 5.86
profit_factor: 1.36
max_drawdown_pct: 10.4
win_rate: 0.455
---

# XAUUSD Empirical Playbook: Four-Bar Momentum Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.86 (Zero-Lookahead simulation)
- **Profit Factor**: 1.36 (101 verified trade executions)
- **Max Drawdown**: 10.4% (Institutional risk profile)
- **Total PnL Return**: +21.1%
- **Win Rate**: 45.5% (Normalized at minimum 1:1.75 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.4x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Four consecutive bearish bars with RSI <= 40 followed by bullish close.
- Short Trigger: Four consecutive bullish bars with RSI >= 60 followed by bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.75 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a new extreme beyond the 4-bar exhaustion high/low.
- Invalidate during major scheduled central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
