---
name: gbpusd_double_inside_bar_playbook
description: Double inside bar coiling breakout for GBPUSD.
symbol: GBPUSD
regime: breakout
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 4.08
profit_factor: 1.46
max_drawdown_pct: 5.28
win_rate: 0.385
---

# GBPUSD Empirical Playbook: Double Inside Bar Coiling Spring Breakout

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.08 (Zero-Lookahead simulation)
- **Profit Factor**: 1.46 (39 verified trade executions)
- **Max Drawdown**: 5.3% (Institutional risk profile)
- **Total PnL Return**: +11.8%
- **Win Rate**: 38.5% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Detect two consecutive inside bars: Bar[i-1] inside Bar[i-2] inside Bar[i-3].
- Long Trigger: H1 Close breaks above Bar[i-1] high with Close > Open.
- Short Trigger: H1 Close breaks below Bar[i-1] low with Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle fails to close outside the mother bar range.
- Invalidate if volatility contracts below minimum trading threshold.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
