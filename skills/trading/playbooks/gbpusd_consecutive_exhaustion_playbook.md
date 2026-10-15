---
name: gbpusd_consecutive_exhaustion_playbook
description: Four-bar momentum exhaustion reversal for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.8
status: active
sharpe_ratio: 4.15
profit_factor: 1.33
max_drawdown_pct: 7.09
win_rate: 0.474
---

# GBPUSD Empirical Playbook: Four-Bar Momentum Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.15 (Zero-Lookahead simulation)
- **Profit Factor**: 1.33 (78 verified trade executions)
- **Max Drawdown**: 7.1% (Institutional risk profile)
- **Total PnL Return**: +13.8%
- **Win Rate**: 47.4% (Normalized at minimum 1:1.8 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.8x ATR, Max Holding = 14 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Four consecutive bearish bars with RSI <= 40 followed by bullish close.
- Short Trigger: Four consecutive bullish bars with RSI >= 60 followed by bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.8 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a new extreme beyond the 4-bar exhaustion high/low.
- Invalidate during major scheduled central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 14 bars.
